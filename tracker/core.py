"""核心逻辑 v2 — 兼容 façade + 扁平 DAG"""
import yaml
import copy
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import flow as flowmod
from . import project_storage as _storage
from .project_migration import (
    normalize_verdicts,
    migrate_project_data,
    prepare_for_save as _prepare_for_save,
)
from .project_constants import (
    PROJECT_SCHEMA_VERSION,
    VALID_DECISION_STATUSES,
    VALID_NODE_STATUSES,
    VALID_POC_STATUSES,
    VALID_REVIEW_VERDICTS,
)
from .project_model import (
    _effective_nodes as _project_model_effective_nodes,
    _get_task_status as _project_model_get_task_status,
    _progress_counts as _project_model_progress_counts,
    _project_as_flow as _project_model_project_as_flow,
    _undone_dependencies as _project_model_undone_dependencies,
)
from .project_mutation import (
    add_subtask_to_project as _project_mutation_add_subtask_to_project,
    attach_doc_to_task as _project_mutation_attach_doc_to_task,
    block_subtask_in_project as _project_mutation_block_subtask_in_project,
    block_task_in_project as _project_mutation_block_task_in_project,
    done_subtask_in_project as _project_mutation_done_subtask_in_project,
    done_task_in_project as _project_mutation_done_task_in_project,
    start_task_in_project as _project_mutation_start_task_in_project,
    unblock_task_in_project as _project_mutation_unblock_task_in_project,
)
from .project_query import get_status as _project_query_get_status
from .subtask_templates import (
    apply_subtask_template_to_project as _subtask_templates_apply_to_project,
    candidate_subtask_template_dirs as _subtask_template_candidate_dirs,
    list_subtask_templates as _subtask_templates_list,
    list_subtasks_in_project as _subtask_templates_list_subtasks_in_project,
    load_subtask_template_definition as _subtask_templates_load_definition,
    match_subtask_templates as _subtask_templates_match,
)
from .project_validation import (
    _validation_issue,
    check_integrity as _project_validation_check_integrity,
    summarize_validation_issues as _project_validation_summarize_validation_issues,
    validate_project as _project_validation_validate_project,
    validate_project_schema as _project_validation_validate_project_schema,
)
from . import requirements as _requirements
from . import close_gate as _close_gate


PROJECTS_DIR = Path(__file__).parent.parent / "projects"
CONFIG_FILE = PROJECTS_DIR / ".active"


def _project_file(project_id: str) -> Path:
    return _storage.project_file(PROJECTS_DIR, project_id)


def _load(project_id: str) -> dict | None:
    return _storage.load_project(PROJECTS_DIR, project_id, migrate_project_data)


def _save(project: dict, check_mtime: bool = True):
    """保存项目到 YAML 文件

    Args:
        project: 项目 dict
        check_mtime: 是否检查并发修改 (乐观锁)

    Raises:
        RuntimeError: 文件已被外部修改
    """
    _storage.save_project(PROJECTS_DIR, project, _prepare_for_save, check_mtime=check_mtime)

    # post-save hooks (best-effort, never break main flow)
    try:
        from .post_save import run_post_save_hooks
        run_post_save_hooks(project)
    except Exception:
        pass


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ── 历史快照 ──────────────────────────────────────────

HISTORY_DIR = PROJECTS_DIR / ".pt_history"
MAX_HISTORY = 10


def _snapshot(project: dict):
    """保存当前 YAML 到历史目录（保留最近 MAX_HISTORY 次）"""
    pid = project["id"]
    _storage.snapshot(HISTORY_DIR, _project_file(pid), pid, max_history=MAX_HISTORY)


def undo(project_id: str) -> str:
    """恢复到上一个快照"""
    latest = _storage.restore_latest_snapshot(HISTORY_DIR, _project_file(project_id), project_id)
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
            # 通知 hook (无侵入)
            try:
                from .notify import fire_event as _fire_event
                _fire_event("mutation", {"project_id": project["id"], "report": project.get("_mutation_report", {})})
            except Exception:
                pass


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
    return _storage.get_active(CONFIG_FILE)


def _set_active(project_id: str):
    _storage.set_active(PROJECTS_DIR, CONFIG_FILE, project_id)


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
    result = []
    active = _get_active()
    for f in _storage.list_project_files(PROJECTS_DIR):
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
    return [validate_project_file(path) for path in _storage.list_project_files(PROJECTS_DIR)]


# ── 任务操作 ──────────────────────────────────────────

def start_task(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    result = _project_mutation_start_task_in_project(
        p,
        task_id,
        now=_now,
        match_subtask_templates=match_subtask_templates,
    )
    _save(p)
    try:
        from .notify import fire_event as _fe; _fe("start", {"project_id": project_id, "task_id": task_id})
    except Exception:
        pass
    return result


def done_task(project_id: str, task_id: str, note: str = "", force: bool = False, note_file: str = "") -> dict:
    p = _load(project_id)
    if note_file:
        _validate_repo_file(p, note_file, "备注文件")
    result = _project_mutation_done_task_in_project(
        p,
        task_id,
        now=_now,
        note=note,
        force=force,
        note_file=note_file,
    )
    _save(p)
    try:
        from .notify import fire_event as _fe; _fe("done", {"project_id": project_id, "task_id": task_id})
    except Exception:
        pass
    return result


def quick_done(project_id: str, task_id: str, note: str = "") -> dict:
    """直接将 pending 任务标记为 done（跳过 in_progress）"""
    p = _load(project_id)
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")
    if node.get("status") == "done":
        raise ValueError(f"任务已完成: {task_id}")
    # 如果是 pending，先自动 start
    if node.get("status") == "pending":
        # 检查依赖
        undone = _project_model_undone_dependencies(p, node)
        if undone:
            raise ValueError(f"依赖未完成: {', '.join(undone)}")
        node["status"] = "in_progress"
        node["started"] = _now()
        p.setdefault("log", []).append({"time": _now(), "action": "start", "task": task_id, "detail": node["name"]})
    # 然后 done
    result = _project_mutation_done_task_in_project(p, task_id, now=_now, note=note, force=False)
    _snapshot(p)
    _save(p)
    try:
        from .notify import fire_event as _fe; _fe("done", {"project_id": project_id, "task_id": task_id})
    except Exception:
        pass
    return result


def block_task(project_id: str, task_id: str, reason: str) -> dict:
    p = _load(project_id)
    result = _project_mutation_block_task_in_project(p, task_id, reason, now=_now)
    _save(p)
    try:
        from .notify import fire_event as _fe; _fe("block", {"project_id": project_id, "task_id": task_id, "reason": reason})
    except Exception:
        pass
    return result


def unblock_task(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    result = _project_mutation_unblock_task_in_project(p, task_id, now=_now)
    _save(p)
    try:
        from .notify import fire_event as _fe; _fe("unblock", {"project_id": project_id, "task_id": task_id})
    except Exception:
        pass
    return result


def add_note(project_id: str, text: str):
    p = _load(project_id)
    p["log"].append({"time": _now(), "action": "note", "detail": text})
    _save(p)


def _subtask_template_dirs() -> list[Path]:
    return _subtask_template_candidate_dirs(Path(__file__).resolve().parent)


# ── 子任务（兼容旧接口，但数据存在节点里） ────────────

def add_subtask(project_id: str, parent_id: str, subtask_id: str, name: str, **kwargs) -> dict:
    """添加子任务 — 作为一等节点插入"""
    p = _load(project_id)
    result = _project_mutation_add_subtask_to_project(
        p,
        parent_id,
        subtask_id,
        name,
        now=_now,
        **kwargs,
    )
    _save(p)
    return result


def done_subtask(project_id: str, full_id: str, note: str = "") -> dict:
    """完成子任务"""
    p = _load(project_id)
    result = _project_mutation_done_subtask_in_project(p, full_id, now=_now, note=note)
    _save(p)
    return result


def block_subtask(project_id: str, full_id: str, reason: str):
    p = _load(project_id)
    _project_mutation_block_subtask_in_project(p, full_id, reason, now=_now)
    _save(p)


def list_subtasks(project_id: str, parent_id: str) -> list[dict]:
    """列出某个父任务的所有子任务"""
    p = _load(project_id)
    return _subtask_templates_list_subtasks_in_project(p, parent_id)


def load_subtask_template(project_id: str, parent_id: str, template_id: str) -> dict:
    """从模板批量导入子任务 — 作为一等节点插入"""
    p = _load(project_id)
    template = _subtask_templates_load_definition(template_id, template_dirs=_subtask_template_dirs())
    result = _subtask_templates_apply_to_project(
        p,
        parent_id,
        template_id,
        template,
        now=_now,
    )
    _save(p)
    return result


def list_subtask_templates() -> list[dict]:
    """列出所有可用的子任务模板"""
    return _subtask_templates_list(template_dirs=_subtask_template_dirs())


def match_subtask_templates(task_id: str) -> list[dict]:
    """查找与任务 ID 匹配的子任务模板。"""
    return _subtask_templates_match(task_id, template_dirs=_subtask_template_dirs())


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


def init_requirements(
    project_id: str,
    *,
    profile: str = _requirements.DEFAULT_PROFILE,
    root: str = _requirements.DEFAULT_ROOT,
    subprojects: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    repo = get_repo_path(p)
    if not repo:
        raise ValueError("项目未关联仓库。使用: pt docs --link <path>")

    existing = (p.get("requirements", {}) or {}).get("subprojects", [])
    normalized_subprojects = _requirements.normalize_subprojects(subprojects, existing=existing)
    result = _requirements.init_requirements(
        p,
        repo,
        profile=profile,
        root=root,
        subprojects=normalized_subprojects,
        dry_run=dry_run,
    )

    if not dry_run:
        p["requirements"] = {
            "profile": profile,
            "root": root,
            "manifest": _requirements.MANIFEST_REL_PATH.as_posix(),
            "subprojects": result["subprojects"],
            "bindings_count": len(result.get("bindings", {})),
            "generated_at": _now(),
        }
        p["log"].append({
            "time": _now(),
            "action": "requirements_init",
            "detail": f"requirements init: profile={profile}, root={root}, created={len(result['created'])}",
        })
        _save(p)
    return result


def rebuild_requirements_indexes(project_id: str, *, dry_run: bool = False) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    repo = get_repo_path(p)
    if not repo:
        raise ValueError("项目未关联仓库。使用: pt docs --link <path>")

    req_state = p.get("requirements", {}) or {}
    root = req_state.get("root", _requirements.DEFAULT_ROOT)
    subprojects = _requirements.normalize_subprojects(None, req_state.get("subprojects", []))
    result = _requirements.rebuild_indexes(p, repo, root=root, subprojects=subprojects, dry_run=dry_run)

    if not dry_run:
        repo_manifest = _requirements.load_repo_manifest(repo)
        req_state["root"] = root
        req_state["profile"] = repo_manifest.get("profile", req_state.get("profile", _requirements.DEFAULT_PROFILE))
        req_state["manifest"] = _requirements.MANIFEST_REL_PATH.as_posix()
        req_state["subprojects"] = repo_manifest.get("subprojects", subprojects)
        req_state["bindings_count"] = len(repo_manifest.get("bindings", {}))
        req_state["indexed_at"] = _now()
        p["requirements"] = req_state
        p["log"].append({
            "time": _now(),
            "action": "requirements_index",
            "detail": f"requirements index: root={root}, written={len(result['created']) + len(result['updated'])}",
        })
        _save(p)
    return result


def check_requirements(project_id: str, *, strict: bool = False, save: bool = True) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    repo = get_repo_path(p)
    if not repo:
        raise ValueError("项目未关联仓库。使用: pt docs --link <path>")

    result = _requirements.check_requirements(p, repo, strict=strict)
    if save:
        repo_manifest = _requirements.load_repo_manifest(repo)
        req_state = p.get("requirements", {}) or {}
        req_state["profile"] = repo_manifest.get("profile", _requirements.DEFAULT_PROFILE)
        req_state["root"] = repo_manifest.get("root", _requirements.DEFAULT_ROOT)
        req_state["manifest"] = _requirements.MANIFEST_REL_PATH.as_posix()
        req_state["subprojects"] = repo_manifest.get("subprojects", req_state.get("subprojects", []))
        req_state["bindings_count"] = len(repo_manifest.get("bindings", {}))
        req_state["last_checked_at"] = _now()
        req_state["last_check_status"] = "pass" if result["valid"] else "fail"
        p["requirements"] = req_state
        p["log"].append({
            "time": _now(),
            "action": "requirements_check",
            "detail": f"requirements check: status={req_state['last_check_status']}, strict={strict}",
        })
        _save(p)
    return result


def trace_requirements(project_id: str, *, dry_run: bool = False, save: bool = True) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    repo = get_repo_path(p)
    if not repo:
        raise ValueError("项目未关联仓库。使用: pt docs --link <path>")

    result = _requirements.trace_requirements(p, repo, dry_run=dry_run)
    if save and not dry_run:
        repo_manifest = _requirements.load_repo_manifest(repo)
        req_state = p.get("requirements", {}) or {}
        req_state["profile"] = repo_manifest.get("profile", _requirements.DEFAULT_PROFILE)
        req_state["root"] = repo_manifest.get("root", _requirements.DEFAULT_ROOT)
        req_state["manifest"] = _requirements.MANIFEST_REL_PATH.as_posix()
        req_state["subprojects"] = repo_manifest.get("subprojects", req_state.get("subprojects", []))
        req_state["bindings_count"] = len(repo_manifest.get("bindings", {}))
        req_state["last_traced_at"] = _now()
        req_state["last_trace_status"] = "pass" if result["valid"] else "fail"
        req_state["last_trace_rows"] = result.get("summary", {}).get("rows", 0)
        p["requirements"] = req_state
        p["log"].append({
            "time": _now(),
            "action": "requirements_trace",
            "detail": (
                "requirements trace: "
                f"status={req_state['last_trace_status']}, "
                f"rows={result.get('summary', {}).get('rows', 0)}, "
                f"output={result.get('path', '-')}"
            ),
        })
        _save(p)
    return result


def check_close_gate(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    return _close_gate.check_close_gate(p, task_id)


def get_task_closure(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")
    result = _close_gate.check_close_gate(p, task_id)
    return {
        "task_id": task_id,
        "name": node.get("name", task_id),
        "required": _close_gate.node_requires_close_gate(node),
        "closure": node.get("closure", {}) or {},
        "check": result,
    }


def list_close_gates(project_id: str) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    return _close_gate.summarize_close_gates(p)


def get_close_human_template(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    return _close_gate.build_human_closure_template(p, task_id)


def update_task_closure(
    project_id: str,
    task_id: str,
    *,
    updates: dict | None = None,
    clear_fields: list[str] | None = None,
    require: bool | None = None,
) -> dict:
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")
    node = _find_node(p, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")

    closure = dict(node.get("closure", {}) or {})
    for field in clear_fields or []:
        closure.pop(field, None)
    for key, value in (updates or {}).items():
        if key == "evidence":
            closure[key] = list(value)
        else:
            closure[key] = value

    if closure:
        node["closure"] = closure
    else:
        node.pop("closure", None)

    if require is not None:
        if require:
            node["close_required"] = True
        else:
            node.pop("close_required", None)

    p.setdefault("log", []).append({
        "time": _now(),
        "action": "close_update",
        "task": task_id,
        "detail": f"close gate updated: fields={','.join(sorted((updates or {}).keys())) or '-'}",
    })
    _save(p)
    return get_task_closure(project_id, task_id)


def attach_doc(project_id: str, task_id: str, file_path: str, description: str = ""):
    """给任务关联文档文件（相对于仓库根目录的路径）"""
    p = _load(project_id)
    if not p:
        raise ValueError(f"项目不存在: {project_id}")

    _validate_repo_file(p, file_path, "文档")

    node = _project_mutation_attach_doc_to_task(
        p,
        task_id,
        file_path,
        now=_now,
        description=description,
    )
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


_get_task_status = _project_model_get_task_status
_project_as_flow = _project_model_project_as_flow
_effective_nodes = _project_model_effective_nodes
_progress_counts = _project_model_progress_counts
_undone_dependencies = _project_model_undone_dependencies

validate_project_schema = _project_validation_validate_project_schema
validate_project = _project_validation_validate_project
summarize_validation_issues = _project_validation_summarize_validation_issues
check_integrity = _project_validation_check_integrity
get_status = _project_query_get_status
