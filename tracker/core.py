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
PROJECT_SCHEMA_VERSION = 2
VALID_NODE_STATUSES = {"pending", "in_progress", "blocked", "done", "expanded", "skipped"}
VALID_DECISION_STATUSES = {"active", "superseded", "reverted", "pending"}
VALID_POC_STATUSES = {"pending", "go", "caution", "no-go"}
VALID_REVIEW_VERDICTS = {"GO", "CAUTION", "NO-GO", "HIGH RISK", "CONDITIONAL GO", "HIGHLY FEASIBLE"}


def _project_file(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.yaml"


def migrate_project_data(project: dict | None) -> tuple[dict | None, bool]:
    """将历史项目数据迁移到当前 schema。"""
    if not isinstance(project, dict):
        return project, False

    changed = False
    migrated = copy.deepcopy(project)

    if migrated.get("schema_version") != PROJECT_SCHEMA_VERSION:
        migrated["schema_version"] = PROJECT_SCHEMA_VERSION
        changed = True

    for key in ("blockers", "log", "nodes", "reviews", "decisions", "pocs"):
        if key not in migrated or migrated[key] is None:
            migrated[key] = []
            changed = True

    for node in migrated.get("nodes", []):
        docs = node.get("docs", []) or []
        normalized_docs = []
        docs_changed = False
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            normalized = dict(doc)
            path = normalized.get("path") or normalized.get("file")
            if path and normalized.get("path") != path:
                normalized["path"] = path
                docs_changed = True
            if "file" in normalized:
                normalized.pop("file", None)
                docs_changed = True
            normalized_docs.append(normalized)
        if docs_changed or normalized_docs != docs:
            node["docs"] = normalized_docs
            changed = True

    normalized_reviews = []
    for review in migrated.get("reviews", []):
        if not isinstance(review, dict):
            continue
        normalized = dict(review)
        verdicts = normalize_verdicts(normalized.get("verdicts", []))
        if normalized.get("verdicts") != verdicts:
            normalized["verdicts"] = verdicts
            changed = True
        normalized_reviews.append(normalized)
    if normalized_reviews != migrated.get("reviews", []):
        migrated["reviews"] = normalized_reviews

    for collection in ("decisions", "pocs"):
        normalized_items = []
        for item in migrated.get(collection, []):
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            if "id" in normalized and isinstance(normalized["id"], str) and normalized["id"].isdigit():
                normalized["id"] = int(normalized["id"])
                changed = True
            normalized_items.append(normalized)
        if normalized_items != migrated.get(collection, []):
            migrated[collection] = normalized_items

    return migrated, changed


def _prepare_for_save(project: dict) -> dict:
    """保存前统一做 schema 归一化。"""
    migrated, _ = migrate_project_data(project)
    return migrated or {}


def _load(project_id: str) -> dict | None:
    f = _project_file(project_id)
    if f.exists():
        with open(f, "r", encoding="utf-8") as fh:
            project = yaml.safe_load(fh)
        project, migrated = migrate_project_data(project)
        # 记录 mtime 用于乐观锁
        project["_mtime"] = f.stat().st_mtime
        if migrated:
            project["_schema_dirty"] = True
        return project
    return None


def _save(project: dict, check_mtime: bool = True):
    """保存项目到 YAML 文件

    Args:
        project: 项目 dict
        check_mtime: 是否检查并发修改 (乐观锁)

    Raises:
        RuntimeError: 文件已被外部修改
    """
    PROJECTS_DIR.mkdir(exist_ok=True)
    f = _project_file(project["id"])

    # 乐观锁检查
    if check_mtime and "_mtime" in project and f.exists():
        current_mtime = f.stat().st_mtime
        if current_mtime != project["_mtime"]:
            raise RuntimeError(
                f"并发冲突：YAML 文件已被外部修改 (mtime: {project['_mtime']} → {current_mtime})。"
                f"请重新加载项目后重试。"
            )

    # 保存时移除内部字段
    normalized = _prepare_for_save(project)
    save_data = {k: v for k, v in normalized.items() if not k.startswith("_")}
    with open(f, "w", encoding="utf-8") as fh:
        yaml.dump(save_data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 更新 mtime
    project["_mtime"] = f.stat().st_mtime
    project.pop("_schema_dirty", None)


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
    Error 级别问题会抛异常，Warning 级别允许写入。
    CPM diff 存储在 project["_mutation_report"] 中。
    """
    from .engine import compute_cpm

    backup = copy.deepcopy(project["nodes"])

    # 记录变更前的 CPM
    try:
        old_cpm = compute_cpm(project, {})
        old_duration = old_cpm.get("total_days", 0)
        old_critical = set(old_cpm.get("critical_path", []))
    except Exception:
        old_duration = 0
        old_critical = set()

    try:
        yield project

        # 退出时验证完整性
        issues = check_integrity(project)

        # 对 error / critical 级别抛异常
        errors = [i for i in issues if isinstance(i, dict)
                  and i.get("severity") in ("error", "critical")]
        if errors:
            msgs = [e.get("message", str(e)) for e in errors[:3]]
            raise ValueError(f"完整性检查失败: {'; '.join(msgs)}")

        # 收集 warnings
        warnings = [i for i in issues if isinstance(i, dict)
                    and i.get("severity") == "warning"]

    except Exception:
        project["nodes"] = backup
        raise
    else:
        # 计算 CPM diff
        try:
            new_cpm = compute_cpm(project, {})
            new_duration = new_cpm.get("total_days", 0)
            new_critical = set(new_cpm.get("critical_path", []))
        except Exception:
            new_duration = old_duration
            new_critical = old_critical

        # 存储变更报告
        project["_mutation_report"] = {
            "duration_diff": new_duration - old_duration,
            "old_duration": old_duration,
            "new_duration": new_duration,
            "new_critical_nodes": list(new_critical - old_critical),
            "removed_critical_nodes": list(old_critical - new_critical),
            "warnings": [w.get("message", str(w)) for w in warnings],
        }

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


def promote(project: dict, parent_id: str, sub_id: str,
            new_node_data: dict = None) -> dict:
    """提拔子任务为一等节点

    将父节点下的子任务提取出来，生成新的一等节点，参与 CPM 计算。

    场景: 原理图节点下的"采购定制接插件"子任务，发现交期 4 周成为瓶颈，
          需要提拔为一等节点阻塞下游。

    Args:
        parent_id: 父节点 ID
        sub_id: 子任务 ID (不含父节点前缀)
        new_node_data: 可选，覆盖新节点的属性 (days, owner 等)

    执行逻辑:
        1. 从父节点的 subtasks 中找到子任务
        2. 创建新的一等节点，继承父节点的上游
        3. 父节点改为依赖新节点
        4. 从父节点的 subtasks 中移除该子任务

    Returns:
        {"new_node": 新节点, "parent": 父节点, "removed_subtask": 被移除的子任务}
    """
    parent = _find_node(project, parent_id)
    if not parent:
        raise ValueError(f"父节点不存在: {parent_id}")

    subtasks = parent.get("subtasks", [])
    sub_idx = None
    sub_task = None
    for i, st in enumerate(subtasks):
        if st.get("id") == sub_id:
            sub_idx = i
            sub_task = st
            break

    if sub_task is None:
        raise ValueError(f"子任务不存在: {parent_id}.{sub_id}")

    # 构建新节点
    new_id = f"{parent_id}.{sub_id}"
    node_ids = {n["id"] for n in project["nodes"]}
    if new_id in node_ids:
        raise ValueError(f"节点 ID 已存在: {new_id}")

    new_node = {
        "id": new_id,
        "name": sub_task.get("name", sub_id),
        "phase": parent.get("phase", "DETAIL"),
        "status": sub_task.get("status", "pending"),
        "depends": list(parent.get("depends", [])),  # 继承父节点上游
    }
    # 可选字段
    if sub_task.get("days"):
        new_node["days"] = sub_task["days"]
    if sub_task.get("owner"):
        new_node["owner"] = sub_task["owner"]
    # 覆盖
    if new_node_data:
        new_node.update(new_node_data)
        new_node["id"] = new_id  # 确保 ID 不被覆盖

    # 添加新节点
    project["nodes"].append(new_node)

    # 父节点改为依赖新节点
    parent_deps = parent.get("depends", [])
    if new_id not in parent_deps:
        parent_deps.append(new_id)
        parent["depends"] = parent_deps

    # 从父节点移除子任务
    subtasks.pop(sub_idx)
    if subtasks:
        parent["subtasks"] = subtasks
    else:
        parent.pop("subtasks", None)

    return {
        "new_node": new_node,
        "parent": parent,
        "removed_subtask": sub_task,
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
        "schema_version": PROJECT_SCHEMA_VERSION,
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
        p = _load(f.stem)
        if not p:
            continue
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


def _effective_nodes(project: dict) -> list[dict]:
    """获取参与统计/调度的有效节点（排除 expanded 父节点）"""
    return [n for n in project.get("nodes", []) if n.get("status") != "expanded"]


def _progress_counts(project: dict) -> tuple[int, int]:
    """返回 (done_count, total) 统计口径。"""
    nodes = _effective_nodes(project)
    total = len(nodes)
    done_count = sum(1 for n in nodes if n.get("status") == "done")
    return done_count, total


def _undone_dependencies(project: dict, node: dict) -> list[str]:
    """返回尚未完成的依赖节点 ID 列表。"""
    undone = []
    for dep_id in node.get("depends", []):
        dep_node = _find_node(project, dep_id)
        if dep_node is None or dep_node.get("status") != "done":
            undone.append(dep_id)
    return undone


def _resolve_repo_file(project: dict, file_path: str) -> Path | None:
    """将相对仓库路径解析为绝对路径；项目未关联仓库时返回 None。"""
    repo = get_repo_path(project)
    if not repo:
        return None
    return repo / file_path


def _validate_repo_file(project: dict, file_path: str, field_name: str = "文件"):
    """校验仓库内文件路径。项目未关联仓库时跳过存在性校验。"""
    if not file_path:
        raise ValueError(f"{field_name}不能为空")
    resolved = _resolve_repo_file(project, file_path)
    if resolved and not resolved.exists():
        raise ValueError(f"{field_name}不存在: {file_path}")


def _fallback_classified(project: dict) -> dict:
    """当图存在结构性错误时，提供保守分类结果。"""
    result = {"ready": [], "in_progress": [], "blocked": [], "waiting": [], "done": []}
    for node in _effective_nodes(project):
        status = node.get("status", "pending")
        if status in ("done", "skipped"):
            result["done"].append(node)
        elif status == "blocked":
            result["blocked"].append(node)
        elif status == "in_progress":
            result["in_progress"].append(node)
        else:
            waiting = dict(node)
            waiting["_waiting_for"] = node.get("depends", [])
            result["waiting"].append(waiting)
    return result


def _fallback_cpm(project: dict) -> dict:
    """当图存在结构性错误时，返回保守的空 CPM 结果。"""
    nodes = {
        n["id"]: {"days": 0, "es": 0, "ef": 0, "ls": 0, "lf": 0,
                  "slack": 0, "critical": False}
        for n in _effective_nodes(project)
    }
    return {
        "nodes": nodes,
        "critical_path": [],
        "total_days": 0,
        "topo_order": [],
    }


# ── 项目验证 ──────────────────────────────────────────

def _validation_issue(issue_type: str, severity: str, message: str, **extra) -> dict:
    issue = {"type": issue_type, "severity": severity, "message": message}
    issue.update(extra)
    return issue



def _validate_named_list_items(items, *, label: str, id_key: str = "id") -> list[dict]:
    issues = []
    if not isinstance(items, list):
        return [
            _validation_issue(
                f"invalid_{label}_collection",
                "warning",
                f"{label} 必须是 list",
            )
        ]

    seen_ids = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(
                _validation_issue(
                    f"invalid_{label}_item",
                    "warning",
                    f"{label}[{index}] 必须是 object/map",
                    index=index,
                )
            )
            continue
        item_id = item.get(id_key)
        if item_id in (None, ""):
            continue
        if item_id in seen_ids:
            issues.append(
                _validation_issue(
                    f"duplicate_{label}_id",
                    "warning",
                    f"{label} 出现重复 ID: {item_id}",
                    item_id=item_id,
                )
            )
            continue
        seen_ids.add(item_id)
    return issues



def validate_project_schema(project: dict | None) -> list[dict]:
    """验证项目 YAML 的结构和关键枚举字段。"""
    issues = []
    if not isinstance(project, dict):
        return [
            _validation_issue(
                "invalid_project_root",
                "error",
                "项目文件顶层必须是 YAML object/map",
            )
        ]

    for key in ("id", "name", "flow"):
        value = project.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                _validation_issue(
                    f"invalid_{key}",
                    "error",
                    f"顶层字段 `{key}` 必须是非空字符串",
                    field=key,
                )
            )

    schema_version = project.get("schema_version")
    if schema_version != PROJECT_SCHEMA_VERSION:
        issues.append(
            _validation_issue(
                "schema_version_mismatch",
                "info",
                f"schema_version={schema_version!r}，当前版本为 {PROJECT_SCHEMA_VERSION}",
            )
        )

    phases = project.get("phases", [])
    phase_ids = set()
    if not isinstance(phases, list):
        issues.append(_validation_issue("invalid_phases", "warning", "顶层字段 `phases` 应为 list"))
    else:
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                issues.append(_validation_issue("invalid_phase_item", "warning", f"phases[{index}] 必须是 object/map", index=index))
                continue
            phase_id = phase.get("id")
            phase_name = phase.get("name")
            if not isinstance(phase_id, str) or not phase_id.strip():
                issues.append(_validation_issue("invalid_phase_id", "warning", f"phases[{index}].id 必须是非空字符串", index=index))
                continue
            if phase_id in phase_ids:
                issues.append(_validation_issue("duplicate_phase_id", "warning", f"阶段 ID 重复: {phase_id}", phase=phase_id))
            phase_ids.add(phase_id)
            if not isinstance(phase_name, str) or not phase_name.strip():
                issues.append(_validation_issue("invalid_phase_name", "warning", f"phases[{index}].name 必须是非空字符串", index=index, phase=phase_id))

    nodes = project.get("nodes", [])
    if not isinstance(nodes, list):
        issues.append(_validation_issue("invalid_nodes", "error", "顶层字段 `nodes` 必须是 list"))
    else:
        seen_node_ids = set()
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                issues.append(_validation_issue("invalid_node_item", "error", f"nodes[{index}] 必须是 object/map", index=index))
                continue

            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                issues.append(_validation_issue("invalid_node_id", "error", f"nodes[{index}].id 必须是非空字符串", index=index))
                continue
            if node_id in seen_node_ids:
                issues.append(_validation_issue("duplicate_node_id", "error", f"节点 ID 重复: {node_id}", node=node_id))
            seen_node_ids.add(node_id)

            name = node.get("name")
            if not isinstance(name, str) or not name.strip():
                issues.append(_validation_issue("invalid_node_name", "error", f"节点 [{node_id}] 缺少有效 name", node=node_id))

            phase = node.get("phase")
            if not isinstance(phase, str) or not phase.strip():
                issues.append(_validation_issue("invalid_node_phase", "error", f"节点 [{node_id}] 缺少有效 phase", node=node_id))
            elif phase_ids and phase not in phase_ids:
                issues.append(_validation_issue("unknown_node_phase", "warning", f"节点 [{node_id}] 引用了未知阶段 `{phase}`", node=node_id, phase=phase))

            status = node.get("status", "pending")
            if status not in VALID_NODE_STATUSES:
                issues.append(_validation_issue("invalid_node_status", "error", f"节点 [{node_id}] status={status!r} 非法", node=node_id, status=status))

            depends = node.get("depends", [])
            if not isinstance(depends, list) or any(not isinstance(dep, str) or not dep.strip() for dep in depends):
                issues.append(_validation_issue("invalid_node_depends", "error", f"节点 [{node_id}] depends 必须是 string list", node=node_id))

            docs = node.get("docs", [])
            if docs is not None:
                if not isinstance(docs, list):
                    issues.append(_validation_issue("invalid_node_docs", "warning", f"节点 [{node_id}] docs 应为 list", node=node_id))
                else:
                    for doc_index, doc in enumerate(docs):
                        if not isinstance(doc, dict):
                            issues.append(_validation_issue("invalid_doc_item", "warning", f"节点 [{node_id}] docs[{doc_index}] 必须是 object/map", node=node_id, index=doc_index))
                            continue
                        doc_path = doc.get("path") or doc.get("file")
                        if not isinstance(doc_path, str) or not doc_path.strip():
                            issues.append(_validation_issue("invalid_doc_path", "warning", f"节点 [{node_id}] docs[{doc_index}] 缺少 path/file", node=node_id, index=doc_index))

    for field_name in ("blockers", "log"):
        items = project.get(field_name, [])
        if not isinstance(items, list):
            issues.append(_validation_issue(f"invalid_{field_name}", "warning", f"顶层字段 `{field_name}` 应为 list"))

    reviews = project.get("reviews", [])
    if not isinstance(reviews, list):
        issues.append(_validation_issue("invalid_reviews", "warning", "顶层字段 `reviews` 应为 list"))
    else:
        for index, review in enumerate(reviews):
            if not isinstance(review, dict):
                issues.append(_validation_issue("invalid_review_item", "warning", f"reviews[{index}] 必须是 object/map", index=index))
                continue
            review_file = review.get("file") or review.get("path")
            if not isinstance(review_file, str) or not review_file.strip():
                issues.append(_validation_issue("invalid_review_file", "warning", f"reviews[{index}] 缺少 file/path", index=index))
            verdicts = normalize_verdicts(review.get("verdicts", []))
            if not isinstance(verdicts, list):
                issues.append(_validation_issue("invalid_review_verdicts", "warning", f"reviews[{index}].verdicts 应为 list 或 legacy dict", index=index))
                continue
            for verdict_index, verdict in enumerate(verdicts):
                if not isinstance(verdict, dict):
                    issues.append(_validation_issue("invalid_review_verdict", "warning", f"reviews[{index}].verdicts[{verdict_index}] 必须是 object/map", index=index))
                    continue
                verdict_name = verdict.get("verdict")
                if not isinstance(verdict_name, str) or not verdict_name.strip():
                    issues.append(_validation_issue("missing_review_verdict", "warning", f"reviews[{index}].verdicts[{verdict_index}] 缺少 verdict", index=index))
                elif verdict_name.upper() not in VALID_REVIEW_VERDICTS:
                    issues.append(_validation_issue("unknown_review_verdict", "info", f"reviews[{index}] 使用了非标准 verdict `{verdict_name}`", index=index))

    decisions = project.get("decisions", [])
    issues.extend(_validate_named_list_items(decisions, label="decisions"))
    if isinstance(decisions, list):
        for index, decision in enumerate(decisions):
            if not isinstance(decision, dict):
                continue
            status = decision.get("status", "active")
            if status not in VALID_DECISION_STATUSES:
                issues.append(_validation_issue("invalid_decision_status", "warning", f"decisions[{index}] status={status!r} 非法", index=index))
            title = decision.get("title")
            if not isinstance(title, str) or not title.strip():
                issues.append(_validation_issue("invalid_decision_title", "warning", f"decisions[{index}] 缺少 title", index=index))

    pocs = project.get("pocs", [])
    issues.extend(_validate_named_list_items(pocs, label="pocs"))
    if isinstance(pocs, list):
        for index, poc in enumerate(pocs):
            if not isinstance(poc, dict):
                continue
            status = poc.get("status", "pending")
            if status not in VALID_POC_STATUSES:
                issues.append(_validation_issue("invalid_poc_status", "warning", f"pocs[{index}] status={status!r} 非法", index=index))
            title = poc.get("title")
            if not isinstance(title, str) or not title.strip():
                issues.append(_validation_issue("invalid_poc_title", "warning", f"pocs[{index}] 缺少 title", index=index))

    return issues



def validate_project(project: dict | None) -> list[dict]:
    issues = validate_project_schema(project)
    hard_errors = [issue for issue in issues if issue.get("severity") in ("error", "critical")]
    if hard_errors or not isinstance(project, dict):
        return issues
    try:
        issues.extend(check_integrity(project))
    except Exception as exc:
        issues.append(_validation_issue("integrity_check_failed", "error", f"完整性检查执行失败: {exc}"))
    return issues



def summarize_validation_issues(issues: list[dict]) -> dict:
    return {
        "critical": sum(1 for issue in issues if issue.get("severity") == "critical"),
        "error": sum(1 for issue in issues if issue.get("severity") == "error"),
        "warning": sum(1 for issue in issues if issue.get("severity") == "warning"),
        "info": sum(1 for issue in issues if issue.get("severity") == "info"),
    }



def validate_project_file(project_file: str | Path) -> dict:
    path = Path(project_file)
    if not path.exists():
        issues = [_validation_issue("missing_project_file", "error", f"项目文件不存在: {path}")]
        return {
            "project_id": path.stem,
            "path": str(path),
            "issues": issues,
            "counts": summarize_validation_issues(issues),
            "valid": False,
            "migrated": False,
        }

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        issues = [_validation_issue("yaml_parse_error", "error", f"YAML 解析失败: {exc}")]
        return {
            "project_id": path.stem,
            "path": str(path),
            "issues": issues,
            "counts": summarize_validation_issues(issues),
            "valid": False,
            "migrated": False,
        }

    migrated_project, migrated = migrate_project_data(raw)
    issues = validate_project(migrated_project)
    if migrated:
        issues.insert(0, _validation_issue("schema_migration_available", "info", "项目文件可自动迁移到当前 schema 版本"))

    counts = summarize_validation_issues(issues)
    project_id = migrated_project.get("id") if isinstance(migrated_project, dict) else path.stem
    return {
        "project_id": project_id or path.stem,
        "path": str(path),
        "issues": issues,
        "counts": counts,
        "valid": counts["critical"] == 0 and counts["error"] == 0,
        "migrated": migrated,
    }



def validate_all_projects() -> list[dict]:
    PROJECTS_DIR.mkdir(exist_ok=True)
    return [validate_project_file(path) for path in sorted(PROJECTS_DIR.glob("*.yaml"))]


# ── 任务操作 ──────────────────────────────────────────

def get_status(project: dict) -> dict:
    """获取项目状态概览"""
    from . import engine
    flow = _project_as_flow(project)
    task_status = _get_task_status(project)
    warnings = check_integrity(project)
    hard_errors = [w for w in warnings if w.get("severity") in ("error", "critical")]

    if hard_errors:
        classified = _fallback_classified(project)
        cpm = _fallback_cpm(project)
    else:
        classified = engine.classify_tasks(flow, task_status)
        cpm = engine.compute_cpm(flow, task_status)
        warnings = check_integrity(project, cpm)

    done_count, total = _progress_counts(project)
    active_blockers = [b for b in project.get("blockers", []) if not b.get("resolved")]

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
    0. 环路检测: DAG 中存在循环依赖 (Fatal Error)
    1. 孤立终点: 非里程碑节点没有后继，且不是项目最终节点
    2. 悬空依赖: depends 引用了不存在的节点 (Fatal Error)
    3. 里程碑缺上游: 里程碑节点没有 depends
    4. 反向跨阶段依赖: 前阶段节点依赖后阶段节点
    5. 重复节点ID (Fatal Error)
    6. 完全孤立节点: 无前驱也无后继（非首阶段）

    Severity 分级:
    - error: 必须修复，阻止写入 (环路、悬空依赖、重复ID)
    - warning: 建议修复，允许写入 (孤立终点、孤立节点)
    - info: 仅供参考 (跨阶段依赖、冗余依赖、粗粒度节点)
    """
    nodes = _effective_nodes(project)
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

    # 0. 环路检测 (Kahn 算法)
    in_degree = {nid: len(predecessors.get(nid, [])) for nid in node_ids}
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    visited_count = 0
    while queue:
        nid = queue.pop(0)
        visited_count += 1
        for succ in successors.get(nid, []):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)
    if visited_count != len(node_ids):
        cycle_nodes = [nid for nid, deg in in_degree.items() if deg > 0]
        warnings.append({
            "type": "cycle_detected",
            "severity": "error",
            "nodes": cycle_nodes[:10],
            "message": f"检测到循环依赖: {', '.join(cycle_nodes[:5])}{'...' if len(cycle_nodes) > 5 else ''}",
        })

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
    if node.get("status") == "blocked":
        raise ValueError(f"任务当前处于阻塞状态: {task_id}")
    if node.get("status") == "expanded":
        raise ValueError(f"任务已展开为子任务，请直接推进子任务: {task_id}")
    if node.get("status") != "pending":
        raise ValueError(f"任务当前状态不允许开始: {task_id} ({node.get('status')})")

    undone = _undone_dependencies(p, node)
    if undone:
        names = [_find_node(p, d).get("name", d) if _find_node(p, d) else d for d in undone]
        raise ValueError(f"依赖未完成: {', '.join(names)}")

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
    if node.get("status") == "blocked":
        raise ValueError(f"任务当前处于阻塞状态，请先解除阻塞: {task_id}")
    if node.get("status") == "expanded":
        raise ValueError(f"任务已展开为子任务，无需再执行 pt done: {task_id}")
    if node.get("status") not in ("pending", "in_progress"):
        raise ValueError(f"任务当前状态不允许完成: {task_id} ({node.get('status')})")

    # 检查依赖是否满足
    deps = node.get("depends", [])
    undone = _undone_dependencies(p, node)
    if deps and not force:
        if undone:
            names = [_find_node(p, d).get("name", d) if _find_node(p, d) else d for d in undone]
            raise ValueError(f"依赖未完成: {', '.join(names)}。使用 --force 强制完成")

    if note_file:
        _validate_repo_file(p, note_file, "备注文件")

    if node.get("status") == "pending" and not node.get("started"):
        node["started"] = _now()
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
    done_count, total = _progress_counts(p)
    remaining = [n["name"] for n in _effective_nodes(p)
                 if n.get("status") not in ("done", "skipped") and
                 not _undone_dependencies(p, n)]
    return {
        "progress": f"{done_count}/{total}",
        "remaining_ready": remaining[:3],
    }


def block_task(project_id: str, task_id: str, reason: str) -> dict:
    p = _load(project_id)
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")
    if node.get("status") == "done":
        raise ValueError(f"任务已完成，不能阻塞: {task_id}")
    if node.get("status") == "expanded":
        raise ValueError(f"任务已展开为子任务，请阻塞具体子任务: {task_id}")
    if node.get("status") == "blocked":
        raise ValueError(f"任务已阻塞: {task_id}")

    node["blocked_from_status"] = node.get("status", "pending")
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

    previous = node.pop("blocked_from_status", "pending")
    if previous == "in_progress" and _undone_dependencies(p, node):
        previous = "pending"
    if previous not in ("pending", "in_progress"):
        previous = "pending"
    node["status"] = previous
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
        parent = _find_node(p, parent_id)
        if parent and parent.get("status") == "expanded":
            result["hint"] = "所有子任务已完成，父任务已由子任务替代。运行: pt next 查看后续任务"
        else:
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

    template_dirs = [
        Path(__file__).resolve().parent / "flows" / "subtasks",
        Path(__file__).resolve().parent.parent / "flows" / "subtasks",
    ]
    template_path = None
    tpl_dir = None
    for candidate in template_dirs:
        candidate_file = candidate / f"{template_id}.yaml"
        if candidate_file.exists():
            template_path = str(candidate_file)
            tpl_dir = str(candidate)
            break
    if not template_path or not os.path.exists(template_path):
        for candidate in template_dirs:
            if candidate.exists():
                tpl_dir = str(candidate)
                break
        available = [f.replace(".yaml", "") for f in os.listdir(tpl_dir) if f.endswith(".yaml")] if tpl_dir else []
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
    tpl_dirs = [
        Path(__file__).resolve().parent / "flows" / "subtasks",
        Path(__file__).resolve().parent.parent / "flows" / "subtasks",
    ]
    tpl_dir = next((str(path) for path in tpl_dirs if path.exists()), None)
    if not tpl_dir:
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
    nodes = _effective_nodes(project)
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

    _validate_repo_file(p, file_path, "文档")

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
            path = doc.get("path") or doc.get("file") or ""
            exists = (repo / path).exists() if repo and path else False
            result.append({
                "task_id": n["id"], "task_name": n.get("name", ""),
                "path": path, "desc": doc.get("desc", ""),
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
    yamls = sorted(pt_dir.glob("*.yaml"))
    if not yamls:
        raise ValueError(f".pt/ 目录中没有项目文件")
    if len(yamls) > 1:
        names = ", ".join(y.name for y in yamls[:5])
        raise ValueError(f".pt/ 目录中有多份项目文件，请保留 1 份后再导入: {names}")

    with open(yamls[0], "r", encoding="utf-8") as f:
        project = yaml.safe_load(f)
    project["repo"] = str(rp)
    _save(project)
    _set_active(project["id"])
    return project
