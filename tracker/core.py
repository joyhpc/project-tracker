"""核心逻辑"""
import yaml
from datetime import datetime
from pathlib import Path
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


def _get_active() -> str | None:
    if CONFIG_FILE.exists():
        return CONFIG_FILE.read_text().strip()
    return None


def _set_active(project_id: str):
    PROJECTS_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(project_id)


# ── 项目管理 ──────────────────────────────────────────

def init_project(project_id: str, name: str, phase: str = "REQ", flow_name: str = "duxin") -> dict:
    if _load(project_id):
        raise ValueError(f"项目已存在: {project_id}")
    fl = flowmod.load_flow(flow_name)
    phases = flowmod.get_phases(fl)
    if phase not in phases:
        raise ValueError(f"无效阶段: {phase}，可选: {list(phases.keys())}")
    project = {
        "id": project_id,
        "name": name,
        "flow": flow_name,
        "current_phase": phase,
        "created": _now(),
        "milestones": {},
        "tasks": {},  # task_id -> {status, started, completed, notes}
        "blockers": [],
        "log": [{"time": _now(), "action": "init", "detail": f"项目创建，起始阶段: {phase}"}],
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


# ── 任务操作 ──────────────────────────────────────────

def _task_entry(project: dict, task_id: str) -> dict:
    """获取或创建任务状态条目"""
    if task_id not in project["tasks"]:
        project["tasks"][task_id] = {"status": "pending"}
    return project["tasks"][task_id]


def get_status(project: dict) -> dict:
    fl = flowmod.load_flow(project.get("flow", "duxin"))
    phases = flowmod.get_phases(fl)
    phase = phases.get(project["current_phase"], {})
    tasks = phase.get("tasks", [])
    task_status = project.get("tasks", {})

    categorized = {"done": [], "in_progress": [], "blocked": [], "pending": []}
    for t in tasks:
        s = task_status.get(t["id"], {}).get("status", "pending")
        categorized[s].append(t)

    active_blockers = [b for b in project.get("blockers", []) if not b.get("resolved")]

    return {
        "project": project,
        "phase": phase,
        "categorized": categorized,
        "blockers": active_blockers,
        "total": len(tasks),
        "done_count": len(categorized["done"]),
    }


def start_task(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    phase, task = flowmod.find_task(fl, task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    entry = _task_entry(p, task_id)
    if entry["status"] == "done":
        raise ValueError(f"任务已完成: {task_id}")
    entry["status"] = "in_progress"
    entry["started"] = _now()
    p["log"].append({"time": _now(), "action": "start", "task": task_id, "detail": task["name"]})
    _save(p)
    return task


def done_task(project_id: str, task_id: str, note: str = "") -> dict:
    p = _load(project_id)
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    phase, task = flowmod.find_task(fl, task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    entry = _task_entry(p, task_id)
    entry["status"] = "done"
    entry["completed"] = _now()
    if note:
        entry["note"] = note
    p["log"].append({"time": _now(), "action": "done", "task": task_id, "detail": note or task["name"]})
    _save(p)
    return check_phase(project_id)


def block_task(project_id: str, task_id: str, reason: str) -> dict:
    p = _load(project_id)
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    _, task = flowmod.find_task(fl, task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    entry = _task_entry(p, task_id)
    entry["status"] = "blocked"
    entry["blocked_reason"] = reason
    p["blockers"].append({"task_id": task_id, "reason": reason, "date": _now()})
    p["log"].append({"time": _now(), "action": "block", "task": task_id, "detail": reason})
    _save(p)
    return {"task": task_id, "reason": reason}


def unblock_task(project_id: str, task_id: str) -> dict:
    p = _load(project_id)
    entry = _task_entry(p, task_id)
    if entry["status"] != "blocked":
        raise ValueError(f"任务未阻塞: {task_id}")
    entry["status"] = "in_progress"
    entry.pop("blocked_reason", None)
    # 标记 blocker 已解决
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


# ── 子任务 ────────────────────────────────────────────

def add_subtask(project_id: str, parent_id: str, subtask_id: str, name: str, **kwargs) -> dict:
    """给流程任务添加自定义子任务"""
    p = _load(project_id)
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    _, parent = flowmod.find_task(fl, parent_id)
    if not parent:
        raise ValueError(f"父任务不存在: {parent_id}")

    entry = _task_entry(p, parent_id)
    if "subtasks" not in entry:
        entry["subtasks"] = {}

    full_id = f"{parent_id}.{subtask_id}"
    if subtask_id in entry["subtasks"]:
        raise ValueError(f"子任务已存在: {full_id}")

    sub = {"name": name, "status": "pending", "created": _now()}
    for k in ("owner", "note", "depends"):
        if k in kwargs and kwargs[k]:
            sub[k] = kwargs[k]
    entry["subtasks"][subtask_id] = sub

    # 父任务自动变为 in_progress
    if entry["status"] == "pending":
        entry["status"] = "in_progress"
        entry["started"] = _now()

    p["log"].append({"time": _now(), "action": "subtask_add", "task": full_id, "detail": name})
    _save(p)
    return sub


def done_subtask(project_id: str, full_id: str, note: str = "") -> dict:
    """完成子任务。full_id 格式: parent_id.subtask_id"""
    parent_id, sub_id = _split_subtask_id(full_id)
    p = _load(project_id)
    entry = _task_entry(p, parent_id)
    subs = entry.get("subtasks", {})
    if sub_id not in subs:
        raise ValueError(f"子任务不存在: {full_id}")

    subs[sub_id]["status"] = "done"
    subs[sub_id]["completed"] = _now()
    if note:
        subs[sub_id]["note"] = note

    p["log"].append({"time": _now(), "action": "subtask_done", "task": full_id, "detail": note or subs[sub_id]["name"]})

    # 检查所有子任务是否完成
    all_done = all(s["status"] == "done" for s in subs.values())
    result = {"subtask": full_id, "all_subtasks_done": all_done}
    if all_done:
        result["hint"] = f"所有子任务已完成，可以运行: pt done {parent_id}"

    _save(p)
    return result


def block_subtask(project_id: str, full_id: str, reason: str):
    parent_id, sub_id = _split_subtask_id(full_id)
    p = _load(project_id)
    entry = _task_entry(p, parent_id)
    subs = entry.get("subtasks", {})
    if sub_id not in subs:
        raise ValueError(f"子任务不存在: {full_id}")
    subs[sub_id]["status"] = "blocked"
    subs[sub_id]["blocked_reason"] = reason
    p["log"].append({"time": _now(), "action": "subtask_block", "task": full_id, "detail": reason})
    _save(p)


def list_subtasks(project_id: str, parent_id: str) -> list[dict]:
    p = _load(project_id)
    entry = p.get("tasks", {}).get(parent_id, {})
    subs = entry.get("subtasks", {})
    result = []
    for sid, s in subs.items():
        result.append({"id": f"{parent_id}.{sid}", **s})
    return result


def _split_subtask_id(full_id: str) -> tuple[str, str]:
    parts = full_id.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(f"子任务ID格式错误，应为 parent.sub: {full_id}")
    return parts[0], parts[1]


# ── 阶段推进 ──────────────────────────────────────────

def check_phase(project_id: str) -> dict:
    p = _load(project_id)
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    phases = flowmod.get_phases(fl)
    order = flowmod.get_phase_order(fl)
    phase = phases.get(p["current_phase"], {})
    tasks = phase.get("tasks", [])
    task_status = p.get("tasks", {})

    done = [t for t in tasks if task_status.get(t["id"], {}).get("status") == "done"]
    remaining = [t for t in tasks if task_status.get(t["id"], {}).get("status") != "done"]

    idx = order.index(p["current_phase"])
    next_phase = order[idx + 1] if idx + 1 < len(order) else None

    return {
        "complete": len(remaining) == 0,
        "progress": f"{len(done)}/{len(tasks)}",
        "remaining": [t["name"] for t in remaining],
        "next_phase": next_phase,
        "milestone": phase.get("milestone", ""),
    }


def advance(project_id: str, force: bool = False) -> dict:
    p = _load(project_id)
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    order = flowmod.get_phase_order(fl)
    phases = flowmod.get_phases(fl)

    idx = order.index(p["current_phase"])
    if idx + 1 >= len(order):
        raise ValueError("已是最后阶段")

    if not force:
        result = check_phase(project_id)
        if not result["complete"]:
            raise ValueError(f"当前阶段未完成 ({result['progress']})，剩余: {', '.join(result['remaining'][:3])}... 使用 --force 强制推进")

    old = p["current_phase"]
    new = order[idx + 1]
    phase = phases.get(old, {})
    if phase.get("milestone"):
        p["milestones"][phase["milestone"]] = _now()

    p["current_phase"] = new
    p["log"].append({"time": _now(), "action": "advance", "detail": f"{old} → {new}"})
    _save(p)
    return {"from": old, "to": new, "milestone": phase.get("milestone", "")}
