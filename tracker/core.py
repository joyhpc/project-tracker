"""核心逻辑 v2 — 单文件自包含 + 扁平 DAG"""
import yaml
import copy
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

def init_project(project_id: str, name: str, flow_name: str = "duxin") -> dict:
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

    return {
        "project": project,
        "classified": classified,
        "cpm": cpm,
        "blockers": active_blockers,
        "total": total,
        "done_count": done_count,
    }


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
    return node


def done_task(project_id: str, task_id: str, note: str = "", force: bool = False) -> dict:
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

            p["nodes"].append(sub_node)
            count += 1

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
            "template_name": template.get("name", template_id)}


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


# ── 阶段/里程碑 ──────────────────────────────────────

def check_phase(project_id: str, phase_id: str = None) -> dict:
    """检查某阶段的完成情况"""
    p = _load(project_id)
    nodes = p.get("nodes", [])

    if phase_id:
        phase_nodes = [n for n in nodes if n.get("phase") == phase_id]
    else:
        phase_nodes = nodes

    done = [n for n in phase_nodes if n.get("status") == "done"]
    remaining = [n for n in phase_nodes if n.get("status") != "done"]

    return {
        "complete": len(remaining) == 0,
        "progress": f"{len(done)}/{len(phase_nodes)}",
        "remaining": [n["name"] for n in remaining[:5]],
        "phase": phase_id,
    }


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
