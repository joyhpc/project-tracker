"""核心逻辑 v2 — 单文件自包含 + 扁平 DAG"""
import yaml
import copy
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


# ── 数据格式工具 ──────────────────────────────────────

def normalize_verdicts(raw) -> list[dict]:
    """统一 verdicts 格式为 list[{verdict, topic}]

    兼容两种来源：
    - 标准格式: list[{"verdict": "GO", "topic": "..."}]
    - 旧版 scan 格式: dict{"GO": 1, "CAUTION": 2}

    所有消费 verdicts 的代码应通过此函数获取数据。
    """
    if isinstance(raw, dict):
        return [{"verdict": k, "topic": f"(legacy, {cnt}次)"}
                for k, cnt in raw.items() for _ in range(cnt)]
    return raw or []
from . import flow as flowmod

PROJECTS_DIR = Path(__file__).parent.parent / "projects"
CONFIG_FILE = PROJECTS_DIR / ".active"


def _project_file(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.yaml"


def _load(project_id: str) -> dict | None:
    f = _project_file(project_id)
    if f.exists():
        with open(f, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    return None


def _save(project: dict):
    PROJECTS_DIR.mkdir(exist_ok=True)
    f = _project_file(project["id"])
    with open(f, "w", encoding="utf-8") as fh:
        yaml.dump(project, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ── 历史快照 ──────────────────────────────────────────

HISTORY_DIR = PROJECTS_DIR / ".pt_history"
MAX_HISTORY = 10


def _snapshot(project: dict):
    """保存当前 YAML 到历史目录（保留最近 MAX_HISTORY 次）"""
    HISTORY_DIR.mkdir(exist_ok=True)
    pid = project["id"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    src = _project_file(pid)
    if src.exists():
        dst = HISTORY_DIR / f"{pid}_{ts}.yaml"
        shutil.copy2(src, dst)
        # 清理旧快照
        snaps = sorted(HISTORY_DIR.glob(f"{pid}_*.yaml"))
        for old in snaps[:-MAX_HISTORY]:
            old.unlink()


def undo(project_id: str) -> str:
    """恢复到上一个快照"""
    snaps = sorted(HISTORY_DIR.glob(f"{project_id}_*.yaml"))
    if not snaps:
        raise ValueError(f"没有可恢复的历史快照: {project_id}")
    latest = snaps[-1]
    shutil.copy2(latest, _project_file(project_id))
    latest.unlink()
    return f"已恢复到 {latest.name}"


# ── DAG 事务 ──────────────────────────────────────────

@contextmanager
def mutate(project: dict, dry_run: bool = False):
    """原子化 DAG 修改的上下文管理器

    用法:
        with mutate(project, dry_run=True) as p:
            add_node(p, {...}, leads_to=[...])
            remove_node(p, "old_node", stitch=True)
        # 退出时自动: check_integrity → 快照 → 保存 (dry_run 时跳过保存)

    Args:
        project: 项目 dict
        dry_run: True=试运行(不保存文件), False=正常执行

    失败时自动回滚内存，不写入文件。
    """
    backup = copy.deepcopy(project["nodes"])
    try:
        yield project
        # 退出时验证完整性
        issues = check_integrity(project)
        errors = [i for i in issues if isinstance(i, dict)
                  and i.get("severity") == "critical"]
        if not errors:
            errors = [i for i in issues if isinstance(i, str)
                      and "没有后继" in i and "孤立" in i]
        if errors:
            msgs = [e.get("message", str(e)) if isinstance(e, dict) else str(e)
                    for e in errors[:3]]
            raise ValueError(f"完整性检查失败: {'; '.join(msgs)}")
    except Exception:
        project["nodes"] = backup
        raise
    else:
        if not dry_run:
            _snapshot(project)
            _save(project)


# ── 节点 CRUD ─────────────────────────────────────────

def add_node(project: dict, node_data: dict,
             depends: list = None, leads_to: list = None) -> dict:
    """添加一等节点到 DAG

    Args:
        project: 项目 dict
        node_data: 节点数据 (必须含 id, name, phase)
        depends: 上游依赖节点 ID 列表
        leads_to: 下游节点 ID 列表 (自动将新节点插入为这些节点的依赖,
                  并执行 Auto-Splice: 如果下游原本直接依赖了新节点的上游,
                  自动移除该冗余边)

    Returns:
        新增的节点 dict
    """
    nid = node_data.get("id")
    if not nid:
        raise ValueError("节点必须有 id")

    node_ids = {n["id"] for n in project["nodes"]}
    if nid in node_ids:
        raise ValueError(f"节点 ID 已存在: {nid}")

    # 构建节点
    node = {
        "id": nid,
        "name": node_data.get("name", nid),
        "phase": node_data.get("phase", "DETAIL"),
        "status": node_data.get("status", "pending"),
        "depends": list(depends or node_data.get("depends", [])),
    }
    # 可选字段
    for key in ("days", "owner", "note", "deliverables", "description",
                "type", "gate", "reviewer", "critical"):
        if key in node_data:
            node[key] = node_data[key]

    # 验证 depends 存在
    for dep in node["depends"]:
        if dep not in node_ids:
            raise ValueError(f"依赖节点不存在: {dep}")

    project["nodes"].append(node)

    # leads_to: 接入下游 + Auto-Splice
    if leads_to:
        upstream_set = set(node["depends"])
        for downstream_id in leads_to:
            dn = _find_node(project, downstream_id)
            if not dn:
                raise ValueError(f"下游节点不存在: {downstream_id}")
            dn_deps = dn.get("depends", [])
            # 添加新节点为下游的依赖
            if nid not in dn_deps:
                dn_deps.append(nid)
                dn["depends"] = dn_deps
            # Auto-Splice: 移除下游对新节点上游的直接依赖（冗余边）
            for up in upstream_set:
                if up in dn_deps:
                    dn_deps.remove(up)

    return node


def remove_node(project: dict, node_id: str,
                stitch: bool = False) -> dict:
    """从 DAG 移除节点

    Args:
        node_id: 要移除的节点 ID
        stitch: True=自动缝合依赖链, False=有下游时拒绝删除

    Returns:
        被移除的节点 dict
    """
    node = _find_node(project, node_id)
    if not node:
        raise ValueError(f"节点不存在: {node_id}")

    # 找到所有依赖此节点的下游
    downstream = [n for n in project["nodes"]
                  if node_id in n.get("depends", [])]

    if downstream and not stitch:
        names = [f"{n['id']}" for n in downstream[:5]]
        raise ValueError(
            f"节点 {node_id} 有 {len(downstream)} 个下游依赖: {', '.join(names)}。"
            f"使用 stitch=True 自动缝合，或先用 skip 软删除。"
        )

    # 缝合: 下游的 depends 中用被删节点的上游替换
    if stitch:
        node_upstreams = set(node.get("depends", []))
        for dn in downstream:
            dn_deps = dn.get("depends", [])
            dn_deps.remove(node_id)
            for up in node_upstreams:
                if up not in dn_deps:
                    dn_deps.append(up)
            dn["depends"] = dn_deps

    # 移除节点
    project["nodes"] = [n for n in project["nodes"] if n["id"] != node_id]
    return node


def skip_node(project: dict, node_id: str, reason: str = "") -> dict:
    """软删除: 标记节点为 skipped (0工时穿透, 保留拓扑)"""
    node = _find_node(project, node_id)
    if not node:
        raise ValueError(f"节点不存在: {node_id}")
    node["status"] = "skipped"
    if reason:
        node["skip_reason"] = reason
    node["skipped_at"] = _now()
    return node


def rewire(project: dict, target_id: str,
           add_deps: list = None, rm_deps: list = None) -> dict:
    """底层拓扑原语: 修改单个节点的 depends 数组

    Args:
        target_id: 要修改的节点 ID
        add_deps: 要添加的上游依赖
        rm_deps: 要移除的上游依赖

    Returns:
        修改后的节点 dict
    """
    node = _find_node(project, target_id)
    if not node:
        raise ValueError(f"节点不存在: {target_id}")

    node_ids = {n["id"] for n in project["nodes"]}
    deps = node.get("depends", [])

    if rm_deps:
        for d in rm_deps:
            if d in deps:
                deps.remove(d)

    if add_deps:
        for d in add_deps:
            if d not in node_ids:
                raise ValueError(f"依赖节点不存在: {d}")
            if d not in deps:
                deps.append(d)

    node["depends"] = deps
    return node


def replace(project: dict, old_id: str,
            entry: str, exit: str = None) -> dict:
    """高阶业务宏: 方案交接棒

    将 old_id 的上下游关系转移给新节点链，old_id 归档为历史枯枝。

    场景: JW7221 → LM5060
      replace(p, "jw7221_verify", entry="lm5060_buy", exit="lm5060_verify")

    执行逻辑:
      1. 入口接管: old_id 的上游(depends) 合并给 entry
      2. 出口交接: 所有依赖 old_id 的下游节点, 将 old_id 替换为 exit
      3. 历史归档: old_id 标记 skipped, 切断下游连线(退化为孤立枯枝)

    Args:
        old_id: 被替换的旧节点
        entry: 新方案链的入口节点 (接管旧节点的上游)
        exit: 新方案链的出口节点 (接管旧节点的下游), 默认=entry (1:1替换)

    Returns:
        {"old": 旧节点, "entry": 入口节点, "exit": 出口节点,
         "transferred_upstream": [...], "transferred_downstream": [...]}
    """
    if exit is None:
        exit = entry

    old_node = _find_node(project, old_id)
    if not old_node:
        raise ValueError(f"旧节点不存在: {old_id}")
    entry_node = _find_node(project, entry)
    if not entry_node:
        raise ValueError(f"入口节点不存在: {entry}")
    exit_node = _find_node(project, exit)
    if not exit_node:
        raise ValueError(f"出口节点不存在: {exit}")

    # Step 1: 入口接管 — old 的上游合并给 entry
    old_upstreams = list(old_node.get("depends", []))
    entry_deps = entry_node.get("depends", [])
    transferred_up = []
    for up in old_upstreams:
        if up not in entry_deps:
            entry_deps.append(up)
            transferred_up.append(up)
    entry_node["depends"] = entry_deps

    # Step 2: 出口交接 — 所有依赖 old 的下游, 替换为 exit
    transferred_down = []
    for n in project["nodes"]:
        deps = n.get("depends", [])
        if old_id in deps:
            deps.remove(old_id)
            if exit not in deps:
                deps.append(exit)
            n["depends"] = deps
            transferred_down.append(n["id"])

    # Step 3: 历史归档 — skipped + 切断下游(下游已在 Step 2 中移除了对 old 的引用)
    old_node["status"] = "skipped"
    old_node["skip_reason"] = f"方案替换: {old_id} → {entry}" + (f" → {exit}" if exit != entry else "")
    old_node["skipped_at"] = _now()
    # old_node 的 depends 保留(保留起因), 下游已切断(Step 2)

    return {
        "old": old_node,
        "entry": entry_node,
        "exit": exit_node,
        "transferred_upstream": transferred_up,
        "transferred_downstream": transferred_down,
    }


def _get_active() -> str | None:
    if CONFIG_FILE.exists():
        return CONFIG_FILE.read_text().strip()
    return None


def _set_active(project_id: str):
    PROJECTS_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(project_id)


# ── 项目管理 ──────────────────────────────────────────

def init_project(project_id: str, name: str, flow_name: str = "duxin", repo: str = "") -> dict:
    """创建项目 — 从模板 deep copy 完整图"""
    if _load(project_id):
        raise ValueError(f"项目已存在: {project_id}")

    fl = flowmod.load_flow(flow_name)

    # Deep copy 节点到项目（单文件自包含）
    nodes = copy.deepcopy(fl.get("nodes", []))
    phases = copy.deepcopy(fl.get("phases", []))

    # 给每个节点初始化运行时状态
    for node in nodes:
        node["status"] = "pending"

    project = {
        "id": project_id,
        "name": name,
        "flow": flow_name,
        "created": _now(),
        "repo": repo,
        "phases": phases,
        "nodes": nodes,
        "blockers": [],
        "log": [{"time": _now(), "action": "init", "detail": f"项目创建，流程: {flow_name}"}],
    }
    _save(project)
    _set_active(project_id)
    return project


def list_projects() -> list[dict]:
    PROJECTS_DIR.mkdir(exist_ok=True)
    result = []
    active = _get_active()
    for f in sorted(PROJECTS_DIR.glob("*.yaml")):
        with open(f, "r", encoding="utf-8") as fh:
            p = yaml.safe_load(fh)
        p["_active"] = (p["id"] == active)
        result.append(p)
    return result


def switch_project(project_id: str):
    if not _load(project_id):
        raise ValueError(f"项目不存在: {project_id}")
    _set_active(project_id)


def require_active() -> dict:
    pid = _get_active()
    if not pid:
        raise RuntimeError("没有活跃项目。先运行: pt init <id> --name <name>")
    p = _load(pid)
    if not p:
        raise RuntimeError(f"活跃项目 {pid} 数据丢失")
    return p


# ── 节点访问（项目内） ────────────────────────────────

def _find_node(project: dict, node_id: str) -> dict | None:
    """在项目节点列表中查找节点"""
    for n in project.get("nodes", []):
        if n["id"] == node_id:
            return n
    return None


def _get_task_status(project: dict) -> dict:
    """构建 {node_id: {status, ...}} 映射，兼容引擎接口"""
    result = {}
    for n in project.get("nodes", []):
        result[n["id"]] = {"status": n.get("status", "pending")}
        if n.get("started"):
            result[n["id"]]["started"] = n["started"]
        if n.get("completed"):
            result[n["id"]]["completed"] = n["completed"]
    return result


def _project_as_flow(project: dict) -> dict:
    """将项目数据转为引擎可用的 flow 格式"""
    return {
        "phases": project.get("phases", []),
        "nodes": project.get("nodes", []),
    }


# ── 任务操作 ──────────────────────────────────────────

def get_status(project: dict) -> dict:
    """获取项目状态概览"""
    from . import engine
    flow = _project_as_flow(project)
    task_status = _get_task_status(project)
    classified = engine.classify_tasks(flow, task_status)
    cpm = engine.compute_cpm(flow, task_status)

    nodes = project.get("nodes", [])
    total = len(nodes)
    done_count = sum(1 for n in nodes if n.get("status") == "done")
    active_blockers = [b for b in project.get("blockers", []) if not b.get("resolved")]

    # 完整性检查
    warnings = check_integrity(project, cpm)

    return {
        "project": project,
        "classified": classified,
        "cpm": cpm,
        "blockers": active_blockers,
        "total": total,
        "done_count": done_count,
        "warnings": warnings,
    }


def check_integrity(project: dict, cpm: dict = None) -> list[dict]:
    """项目完整性检查 — 检测结构性问题

    检查项:
    1. 孤立终点: 非里程碑节点没有后继，且不是项目最终节点
    2. 悬空依赖: depends 引用了不存在的节点
    3. 里程碑缺上游: 里程碑节点没有 depends
    4. 反向跨阶段依赖: 前阶段节点依赖后阶段节点
    5. 重复节点ID
    6. 完全孤立节点: 无前驱也无后继（非首阶段）
    """
    nodes = project.get("nodes", [])
    node_ids = {n["id"] for n in nodes}
    nodes_map = {n["id"]: n for n in nodes}
    phases = project.get("phases", [])
    phase_order = {ph["id"]: i for i, ph in enumerate(phases)}
    last_phase_id = phases[-1]["id"] if phases else None
    first_phase_id = phases[0]["id"] if phases else None

    # 构建前驱/后继表
    successors = {n["id"]: [] for n in nodes}
    predecessors = {n["id"]: [] for n in nodes}
    for n in nodes:
        for dep in n.get("depends", []):
            if dep in successors:
                successors[dep].append(n["id"])
            if dep in predecessors:
                predecessors[n["id"]].append(dep)

    final_milestones = {n["id"] for n in nodes
                        if n.get("type") == "milestone"
                        and n.get("phase") == last_phase_id}
    # 最后阶段的所有节点都是合法终点
    final_phase_nodes = {n["id"] for n in nodes
                         if n.get("phase") == last_phase_id}

    warnings = []

    # 1. 孤立终点检测
    for n in nodes:
        nid = n["id"]
        if not successors[nid] and nid not in final_milestones and nid not in final_phase_nodes:
            if n.get("type") == "milestone":
                continue
            if n.get("status") == "done":
                continue
            if n.get("status") == "skipped":
                continue
            severity = "critical" if (cpm and cpm.get("nodes", {}).get(nid, {}).get("critical")) else "warning"
            warnings.append({
                "type": "orphan_terminal",
                "severity": severity,
                "node": nid,
                "name": n.get("name", ""),
                "message": f"[{nid}] {n.get('name','')} 没有后继节点 — 可能未接入下游流程",
            })

    # 2. 悬空依赖检测
    for n in nodes:
        for dep in n.get("depends", []):
            if dep not in node_ids:
                warnings.append({
                    "type": "dangling_dep",
                    "severity": "error",
                    "node": n["id"],
                    "dep": dep,
                    "message": f"[{n['id']}] 依赖 [{dep}] 不存在",
                })

    # 3. 里程碑缺上游
    for n in nodes:
        if n.get("type") == "milestone" and not n.get("depends"):
            warnings.append({
                "type": "milestone_no_deps",
                "severity": "warning",
                "node": n["id"],
                "message": f"里程碑 [{n['id']}] 没有上游依赖",
            })

    # 4. 反向跨阶段依赖（前阶段节点依赖后阶段节点）
    #    注意：阶段是管理视角的线性排列，实际工程中并行阶段（如制样+软件开发）
    #    的跨阶段依赖是合理的。标记为 info 供人工判断，不作为 error。
    for n in nodes:
        n_order = phase_order.get(n.get("phase", ""), -1)
        if n_order < 0:
            continue
        for dep in n.get("depends", []):
            dep_node = nodes_map.get(dep)
            if dep_node:
                dep_order = phase_order.get(dep_node.get("phase", ""), -1)
                if dep_order > n_order:
                    warnings.append({
                        "type": "reverse_phase_dep",
                        "severity": "info",
                        "node": n["id"],
                        "dep": dep,
                        "message": f"[{n['id']}]({n.get('phase','')}) 依赖后阶段 [{dep}]({dep_node.get('phase','')})",
                    })

    # 5. 重复节点ID
    from collections import Counter
    id_counts = Counter(n["id"] for n in nodes)
    for nid, cnt in id_counts.items():
        if cnt > 1:
            warnings.append({
                "type": "duplicate_id",
                "severity": "error",
                "node": nid,
                "message": f"[{nid}] 节点ID重复 ({cnt}次)",
            })

    # 6. 完全孤立节点（无前驱也无后继，非首阶段）
    for n in nodes:
        nid = n["id"]
        if (not predecessors[nid] and not successors[nid]
                and n.get("phase") != first_phase_id
                and n.get("status") != "done"
                and n.get("status") != "skipped"):
            warnings.append({
                "type": "isolated_node",
                "severity": "warning",
                "node": nid,
                "message": f"[{nid}] {n.get('name','')} 完全孤立（无前驱无后继）",
            })

    # 7. 冗余依赖（A 依赖 B 和 C，但 C 已经依赖 B，则 A→B 冗余）
    for n in nodes:
        deps = n.get("depends", [])
        if len(deps) < 2:
            continue
        dep_set = set(deps)
        # 对每个依赖，检查是否被其他依赖的传递闭包覆盖
        for d in deps:
            # BFS: 从其他依赖出发，看能否到达 d
            other_deps = dep_set - {d}
            visited = set()
            queue = list(other_deps)
            reachable = False
            while queue:
                cur = queue.pop(0)
                if cur == d:
                    reachable = True
                    break
                if cur in visited:
                    continue
                visited.add(cur)
                cur_node = nodes_map.get(cur)
                if cur_node:
                    for cd in cur_node.get("depends", []):
                        if cd not in visited:
                            queue.append(cd)
            if reachable:
                warnings.append({
                    "type": "redundant_dep",
                    "severity": "info",
                    "node": n["id"],
                    "dep": d,
                    "message": f"[{n['id']}] → [{d}] 冗余依赖（已被其他依赖路径覆盖）",
                })

    # 8. 粗粒度调试节点提示（可展开为分层子任务）
    #    调试/bringup 类节点如果没有子任务展开，提示可以细化
    bringup_keywords = ["调试", "bringup", "bring-up", "bring_up"]
    for n in nodes:
        if n.get("status") == "done":
            continue
        nid = n["id"]
        name_lower = (n.get("name", "") + " " + nid).lower()
        is_bringup = any(k in name_lower for k in bringup_keywords)
        if not is_bringup:
            continue
        # 检查是否已有子任务展开
        has_children = any(
            cn["id"].startswith(nid + ".") for cn in nodes if cn["id"] != nid
        )
        if not has_children:
            warnings.append({
                "type": "coarse_bringup",
                "severity": "info",
                "node": nid,
                "message": f"[{nid}] {n.get('name','')} 是粗粒度调试节点 — 可用 pt sub-load {nid} board_bringup 展开为分层调试",
            })

    return warnings


def start_task(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")
    if node.get("status") == "done":
        raise ValueError(f"任务已完成: {task_id}")
    if node.get("status") == "in_progress":
        raise ValueError(f"任务已在进行中: {task_id}")

    node["status"] = "in_progress"
    node["started"] = _now()
    p["log"].append({"time": _now(), "action": "start", "task": task_id, "detail": node["name"]})
    _save(p)

    # 检查是否有匹配的子任务模板（不自动加载，返回提示信息）
    matched = match_subtask_templates(task_id)
    result = dict(node)
    if matched:
        result["_matched_templates"] = matched
    return result


def done_task(project_id: str, task_id: str, note: str = "", force: bool = False, note_file: str = "") -> dict:
    p = _load(project_id)
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")
    if node.get("status") == "done":
        raise ValueError(f"任务已完成: {task_id}")

    # 检查依赖是否满足
    deps = node.get("depends", [])
    if deps and not force:
        undone = [d for d in deps if _find_node(p, d) and
                  _find_node(p, d).get("status") != "done"]
        if undone:
            names = [_find_node(p, d).get("name", d) for d in undone]
            raise ValueError(f"依赖未完成: {', '.join(names)}。使用 --force 强制完成")

    node["status"] = "done"
    node["completed"] = _now()
    if note:
        node["note"] = note
    if note_file:
        # 多行备注：关联文件路径，同时自动 attach 为文档
        node["note_file"] = note_file
        docs = node.get("docs", [])
        if not any(d["path"] == note_file for d in docs):
            docs.append({"path": note_file, "desc": "完成备注", "added": _now()})
            node["docs"] = docs
    p["log"].append({"time": _now(), "action": "done", "task": task_id,
                     "detail": note or node["name"]})
    _save(p)

    # 返回进度信息
    total = len(p["nodes"])
    done_count = sum(1 for n in p["nodes"] if n.get("status") == "done")
    remaining = [n["name"] for n in p["nodes"]
                 if n.get("status") != "done" and
                 all(_find_node(p, d) is None or _find_node(p, d).get("status") == "done"
                     for d in n.get("depends", []))]
    return {
        "progress": f"{done_count}/{total}",
        "remaining_ready": remaining[:3],
    }


def block_task(project_id: str, task_id: str, reason: str) -> dict:
    p = _load(project_id)
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")

    node["status"] = "blocked"
    node["blocked_reason"] = reason
    p["blockers"].append({"task_id": task_id, "reason": reason, "date": _now()})
    p["log"].append({"time": _now(), "action": "block", "task": task_id, "detail": reason})
    _save(p)
    return {"task": task_id, "reason": reason}


def unblock_task(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")
    if node.get("status") != "blocked":
        raise ValueError(f"任务未阻塞: {task_id}")

    node["status"] = "in_progress"
    node.pop("blocked_reason", None)
    for b in p.get("blockers", []):
        if b["task_id"] == task_id and not b.get("resolved"):
            b["resolved"] = _now()
            break
    p["log"].append({"time": _now(), "action": "unblock", "task": task_id})
    _save(p)
    return {"task": task_id}


def add_note(project_id: str, text: str):
    p = _load(project_id)
    p["log"].append({"time": _now(), "action": "note", "detail": text})
    _save(p)


# ── 子任务（兼容旧接口，但数据存在节点里） ────────────

def add_subtask(project_id: str, parent_id: str, subtask_id: str, name: str, **kwargs) -> dict:
    """添加子任务 — 作为一等节点插入"""
    p = _load(project_id)
    parent = _find_node(p, parent_id)
    if not parent:
        raise ValueError(f"父任务不存在: {parent_id}")

    full_id = f"{parent_id}.{subtask_id}"
    if _find_node(p, full_id):
        raise ValueError(f"子任务已存在: {full_id}")

    sub_node = {
        "id": full_id,
        "name": name,
        "type": "task",
        "phase": parent.get("phase", ""),
        "parent": parent_id,
        "status": "pending",
        "created": _now(),
    }
    for k in ("owner", "days", "depends", "deliverables", "description"):
        if k in kwargs and kwargs[k]:
            sub_node[k] = kwargs[k]

    p["nodes"].append(sub_node)

    # 父任务自动变为 in_progress
    if parent.get("status") == "pending":
        parent["status"] = "in_progress"
        parent["started"] = _now()

    p["log"].append({"time": _now(), "action": "subtask_add", "task": full_id, "detail": name})
    _save(p)
    return sub_node


def done_subtask(project_id: str, full_id: str, note: str = "") -> dict:
    """完成子任务"""
    p = _load(project_id)
    node = _find_node(p, full_id)
    if not node:
        raise ValueError(f"子任务不存在: {full_id}")

    node["status"] = "done"
    node["completed"] = _now()
    if note:
        node["note"] = note

    p["log"].append({"time": _now(), "action": "subtask_done", "task": full_id,
                     "detail": note or node["name"]})

    # 检查同父的所有子任务是否完成
    parent_id = node.get("parent", full_id.rsplit(".", 1)[0])
    siblings = [n for n in p["nodes"] if n.get("parent") == parent_id]
    all_done = all(s.get("status") == "done" for s in siblings)

    result = {"subtask": full_id, "all_subtasks_done": all_done}
    if all_done:
        result["hint"] = f"所有子任务已完成，可以运行: pt done {parent_id}"

    _save(p)
    return result


def block_subtask(project_id: str, full_id: str, reason: str):
    p = _load(project_id)
    node = _find_node(p, full_id)
    if not node:
        raise ValueError(f"子任务不存在: {full_id}")
    node["status"] = "blocked"
    node["blocked_reason"] = reason
    p["log"].append({"time": _now(), "action": "subtask_block", "task": full_id, "detail": reason})
    _save(p)


def list_subtasks(project_id: str, parent_id: str) -> list[dict]:
    """列出某个父任务的所有子任务"""
    p = _load(project_id)
    return [n for n in p.get("nodes", []) if n.get("parent") == parent_id]


def load_subtask_template(project_id: str, parent_id: str, template_id: str) -> dict:
    """从模板批量导入子任务 — 作为一等节点插入"""
    import os
    p = _load(project_id)
    parent = _find_node(p, parent_id)
    if not parent:
        raise ValueError(f"父任务不存在: {parent_id}")

    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                  "flows", "subtasks", f"{template_id}.yaml")
    if not os.path.exists(template_path):
        tpl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flows", "subtasks")
        available = [f.replace(".yaml", "") for f in os.listdir(tpl_dir) if f.endswith(".yaml")]
        raise ValueError(f"模板不存在: {template_id}。可用: {', '.join(available)}")

    with open(template_path, "r", encoding="utf-8") as f:
        template = yaml.safe_load(f)

    count = 0
    for phase in template.get("phases", []):
        for task in phase.get("tasks", []):
            full_id = f"{parent_id}.{task['id']}"
            if _find_node(p, full_id):
                continue  # 跳过已存在

            sub_node = {
                "id": full_id,
                "name": task["name"],
                "type": "task",
                "phase": parent.get("phase", ""),
                "parent": parent_id,
                "status": "pending",
                "created": _now(),
            }
            if task.get("owner"):
                sub_node["owner"] = task["owner"]
            if task.get("days"):
                sub_node["days"] = task["days"]
            if task.get("depends"):
                # 子任务依赖加前缀
                sub_node["depends"] = [f"{parent_id}.{d}" for d in task["depends"]]
            if task.get("deliverables"):
                sub_node["deliverables"] = task["deliverables"]
            if task.get("critical"):
                sub_node["critical"] = True
            if task.get("description"):
                sub_node["description"] = task["description"]

            # 处理外部依赖提示（external_depends_hint）
            hints = task.get("external_depends_hint", [])
            if hints:
                sub_node["_external_hints"] = hints

            p["nodes"].append(sub_node)
            count += 1

    # ── 外部依赖自动匹配 ──
    ext_dep_suggestions = []
    all_node_ids = {n["id"] for n in p["nodes"]}
    for n in p["nodes"]:
        if n.get("parent") != parent_id:
            continue
        hints = n.pop("_external_hints", [])
        for hint in hints:
            import fnmatch
            pattern = hint["pattern"]
            matched_nodes = [
                nid for nid in all_node_ids
                if fnmatch.fnmatch(nid, pattern)
                and not nid.startswith(parent_id + ".")  # 排除自己的子任务
                and nid != parent_id
            ]
            if matched_nodes and hint.get("required"):
                # 自动添加外部依赖
                existing = set(n.get("depends", []))
                for mn in matched_nodes:
                    if mn not in existing:
                        n.setdefault("depends", []).append(mn)
                        ext_dep_suggestions.append({
                            "subtask": n["id"],
                            "external_dep": mn,
                            "reason": hint["reason"],
                            "auto_added": True,
                        })
            elif matched_nodes and not hint.get("required"):
                for mn in matched_nodes:
                    ext_dep_suggestions.append({
                        "subtask": n["id"],
                        "external_dep": mn,
                        "reason": hint["reason"],
                        "auto_added": False,
                    })

    if count > 0:
        # ── 边重连（Rewire）──
        # 1. 找子图的入口节点（无内部依赖的子任务）
        sub_ids = {n["id"] for n in p["nodes"] if n.get("parent") == parent_id}
        entry_subs = []
        for n in p["nodes"]:
            if n["id"] not in sub_ids:
                continue
            internal_deps = [d for d in n.get("depends", []) if d in sub_ids]
            if not internal_deps:
                entry_subs.append(n["id"])

        # 2. 找子图的出口节点（无内部后继的子任务）
        depended_by = set()
        for n in p["nodes"]:
            if n["id"] not in sub_ids:
                continue
            for d in n.get("depends", []):
                if d in sub_ids:
                    depended_by.add(d)
        exit_subs = [sid for sid in sub_ids if sid not in depended_by]

        # 3. 入口子任务继承父任务的 depends
        parent_deps = parent.get("depends", [])
        if parent_deps:
            for eid in entry_subs:
                entry_node = _find_node(p, eid)
                if entry_node:
                    existing = set(entry_node.get("depends", []))
                    new_deps = [d for d in parent_deps if d not in existing]
                    if new_deps:
                        entry_node.setdefault("depends", []).extend(new_deps)

        # 4. 父任务的后继改为依赖出口子任务（替代依赖父任务）
        if exit_subs:
            for n in p["nodes"]:
                if n["id"] in sub_ids or n["id"] == parent_id:
                    continue
                deps = n.get("depends", [])
                if parent_id in deps:
                    deps.remove(parent_id)
                    deps.extend(exit_subs)
                    n["depends"] = deps

        # 5. 父任务标记为展开状态（不再参与依赖图）
        parent["status"] = "expanded"
        parent["expanded_to"] = sorted(sub_ids)

    if parent.get("status") == "pending" and count > 0:
        parent["status"] = "in_progress"
        parent["started"] = _now()

    p["log"].append({
        "time": _now(), "action": "subtask_template_load",
        "task": parent_id,
        "detail": f"加载模板 {template_id}: {count} 个子任务"
    })
    _save(p)
    return {"loaded": count, "template": template_id, "parent": parent_id,
            "template_name": template.get("name", template_id),
            "external_dep_suggestions": ext_dep_suggestions}


def list_subtask_templates() -> list[dict]:
    """列出所有可用的子任务模板"""
    import os
    tpl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flows", "subtasks")
    if not os.path.exists(tpl_dir):
        return []
    result = []
    for f in sorted(os.listdir(tpl_dir)):
        if not f.endswith(".yaml"):
            continue
        path = os.path.join(tpl_dir, f)
        with open(path, "r", encoding="utf-8") as fh:
            tpl = yaml.safe_load(fh)
        task_count = sum(len(p.get("tasks", [])) for p in tpl.get("phases", []))
        result.append({
            "id": f.replace(".yaml", ""),
            "name": tpl.get("name", ""),
            "description": tpl.get("description", ""),
            "attach_to": tpl.get("attach_to", []),
            "task_count": task_count,
            "phases": [p.get("name", "") for p in tpl.get("phases", [])],
        })
    return result


def match_subtask_templates(task_id: str) -> list[dict]:
    """查找与任务 ID 匹配的子任务模板

    匹配逻辑：task_id 出现在模板的 attach_to 列表中
    Returns: 匹配的模板列表 [{id, name, task_count, ...}]
    """
    templates = list_subtask_templates()
    return [t for t in templates if task_id in t["attach_to"]]


# ── 阶段/里程碑 ──────────────────────────────────────
def get_phase_progress(project: dict) -> list[dict]:
    """获取所有阶段的进度"""
    nodes = project.get("nodes", [])
    phases = project.get("phases", [])
    result = []
    for phase in phases:
        pid = phase["id"]
        phase_nodes = [n for n in nodes if n.get("phase") == pid]
        done = sum(1 for n in phase_nodes if n.get("status") == "done")
        total = len(phase_nodes)
        result.append({
            "id": pid,
            "name": phase.get("name", pid),
            "done": done,
            "total": total,
            "progress": f"{done}/{total}",
            "complete": done == total and total > 0,
        })
    return result


# ── 文档管理 ──────────────────────────────────────────

def get_repo_path(project: dict) -> Path | None:
    """获取项目关联的仓库路径"""
    repo = project.get("repo", "")
    if not repo:
        return None
    p = Path(repo).expanduser()
    if p.exists():
        return p
    return None


def set_repo(project_id: str, repo_path: str):
    """关联项目到本地仓库"""
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    rp = Path(repo_path).expanduser().resolve()
    if not rp.exists():
        raise ValueError(f"路径不存在: {rp}")
    p["repo"] = str(rp)
    p["log"].append({"time": _now(), "action": "repo_link", "detail": f"关联仓库: {rp}"})
    _save(p)
    return str(rp)


def attach_doc(project_id: str, task_id: str, file_path: str, description: str = ""):
    """给任务关联文档文件（相对于仓库根目录的路径）"""
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")

    docs = node.get("docs", [])
    if any(d["path"] == file_path for d in docs):
        raise ValueError(f"文档已关联: {file_path}")

    docs.append({"path": file_path, "desc": description, "added": _now()})
    node["docs"] = docs
    p["log"].append({
        "time": _now(), "action": "doc_attach",
        "task": task_id, "detail": f"关联文档: {file_path}",
    })
    _save(p)
    return node


def list_task_docs(project: dict, task_id: str = None) -> list[dict]:
    """列出任务关联的文档。task_id=None 时列出所有。"""
    result = []
    repo = get_repo_path(project)
    for n in project.get("nodes", []):
        if task_id and n["id"] != task_id:
            continue
        for doc in n.get("docs", []):
            exists = (repo / doc["path"]).exists() if repo else False
            result.append({
                "task_id": n["id"], "task_name": n.get("name", ""),
                "path": doc["path"], "desc": doc.get("desc", ""),
                "exists": exists,
            })
    return result


def sync_project_to_repo(project_id: str, push: bool = False) -> dict:
    """将项目状态文件同步到关联仓库的 .pt/ 目录"""
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    repo = get_repo_path(p)
    if not repo:
        raise ValueError("项目未关联仓库。使用: pt docs --link <path>")

    import shutil
    pt_dir = repo / ".pt"
    pt_dir.mkdir(exist_ok=True)
    src = _project_file(project_id)
    dst = pt_dir / f"{project_id}.yaml"
    shutil.copy2(src, dst)

    _update_readme_status(p, repo)

    result = {"synced": str(dst), "repo": str(repo), "pushed": False}

    if push:
        import subprocess
        try:
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True,
                           capture_output=True, text=True)
            # 生成 commit message
            nodes = p.get("nodes", [])
            done = sum(1 for n in nodes if n.get("status") == "done")
            total = len(nodes)
            msg = f"pt sync: {p['name']} [{done}/{total}]"
            subprocess.run(["git", "commit", "-m", msg], cwd=repo, check=True,
                           capture_output=True, text=True)
            subprocess.run(["git", "push"], cwd=repo, check=True,
                           capture_output=True, text=True)
            result["pushed"] = True
        except subprocess.CalledProcessError as e:
            result["push_error"] = e.stderr.strip() or str(e)

    return result


def _update_readme_status(project: dict, repo: Path):
    """更新仓库 README 中的项目状态表格"""
    import re
    from . import engine
    flow = _project_as_flow(project)
    task_status = _get_task_status(project)
    cpm = engine.compute_cpm(flow, task_status)

    nodes = project.get("nodes", [])
    total = len(nodes)
    done = sum(1 for n in nodes if n.get("status") == "done")

    lines = [
        "## 项目状态", "",
        f"- 进度: {done}/{total}",
        f"- 总工期: {cpm['total_days']:.0f} 天",
        f"- 关键路径: {len(cpm['critical_path'])} 个节点", "",
        "| 阶段 | 进度 | 状态 |",
        "|------|------|------|",
    ]
    for ph in get_phase_progress(project):
        pct = (ph["done"] / ph["total"] * 100) if ph["total"] > 0 else 0
        icon = "✅" if ph["complete"] else ("🔄" if ph["done"] > 0 else "⏳")
        lines.append(f"| {ph['name']} | {ph['progress']} ({pct:.0f}%) | {icon} |")

    status_block = "\n".join(lines)

    readme = repo / "README.md"
    if not readme.exists():
        return
    content = readme.read_text(encoding="utf-8")
    pattern = r"## 项目状态\n.*?(?=\n## |\Z)"
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, status_block, content, flags=re.DOTALL)
    else:
        content = content.rstrip() + "\n\n" + status_block + "\n"
    readme.write_text(content, encoding="utf-8")


def load_from_repo(repo_path: str) -> dict:
    """从仓库的 .pt/ 目录加载项目（换电脑时用）"""
    rp = Path(repo_path).expanduser().resolve()
    pt_dir = rp / ".pt"
    if not pt_dir.exists():
        raise ValueError(f"仓库中没有 .pt/ 目录: {rp}")
    yamls = list(pt_dir.glob("*.yaml"))
    if not yamls:
        raise ValueError(f".pt/ 目录中没有项目文件")

    with open(yamls[0], "r", encoding="utf-8") as f:
        project = yaml.safe_load(f)
    project["repo"] = str(rp)
    _save(project)
    _set_active(project["id"])
    return project
