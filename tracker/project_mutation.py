"""Project mutation/state-transition helpers shared by core wrappers."""

from __future__ import annotations

from .project_model import (
    _effective_nodes,
    _find_node_in_project,
    _progress_counts,
    _undone_dependencies,
)


def _append_log(project: dict, entry: dict) -> None:
    project.setdefault("log", []).append(entry)


def _node_name(project: dict, node_id: str) -> str:
    node = _find_node_in_project(project, node_id)
    return node.get("name", node_id) if node else node_id


def _undone_dependency_names(project: dict, node: dict) -> list[str]:
    return [_node_name(project, dep_id) for dep_id in _undone_dependencies(project, node)]


def start_task_in_project(
    project: dict,
    task_id: str,
    *,
    now,
    match_subtask_templates=None,
) -> dict:
    node = _find_node_in_project(project, task_id)
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

    undone = _undone_dependencies(project, node)
    if undone:
        raise ValueError(f"依赖未完成: {', '.join(_undone_dependency_names(project, node))}")

    current_time = now()
    node["status"] = "in_progress"
    node["started"] = current_time
    _append_log(project, {"time": current_time, "action": "start", "task": task_id, "detail": node["name"]})

    result = dict(node)
    matched = match_subtask_templates(task_id) if match_subtask_templates else []
    if matched:
        result["_matched_templates"] = matched
    return result


def done_task_in_project(
    project: dict,
    task_id: str,
    *,
    now,
    note: str = "",
    force: bool = False,
    note_file: str = "",
) -> dict:
    node = _find_node_in_project(project, task_id)
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

    deps = node.get("depends", [])
    undone = _undone_dependencies(project, node)
    if deps and not force and undone:
        raise ValueError(f"依赖未完成: {', '.join(_undone_dependency_names(project, node))}。使用 --force 强制完成")

    current_time = now()
    if node.get("status") == "pending" and not node.get("started"):
        node["started"] = current_time
    node["status"] = "done"
    node["completed"] = current_time
    if note:
        node["note"] = note
    if note_file:
        node["note_file"] = note_file
        docs = node.get("docs", [])
        if not any((doc.get("path") or doc.get("file")) == note_file for doc in docs):
            docs.append({"path": note_file, "desc": "完成备注", "added": current_time})
            node["docs"] = docs

    _append_log(project, {
        "time": current_time,
        "action": "done",
        "task": task_id,
        "detail": note or node["name"],
    })

    done_count, total = _progress_counts(project)
    remaining = [
        node_info["name"]
        for node_info in _effective_nodes(project)
        if node_info.get("status") not in ("done", "skipped") and not _undone_dependencies(project, node_info)
    ]
    return {
        "progress": f"{done_count}/{total}",
        "remaining_ready": remaining[:3],
    }


def block_task_in_project(project: dict, task_id: str, reason: str, *, now) -> dict:
    node = _find_node_in_project(project, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")
    if node.get("status") == "done":
        raise ValueError(f"任务已完成，不能阻塞: {task_id}")
    if node.get("status") == "expanded":
        raise ValueError(f"任务已展开为子任务，请阻塞具体子任务: {task_id}")
    if node.get("status") == "blocked":
        raise ValueError(f"任务已阻塞: {task_id}")

    current_time = now()
    node["blocked_from_status"] = node.get("status", "pending")
    node["status"] = "blocked"
    node["blocked_reason"] = reason
    project.setdefault("blockers", []).append({"task_id": task_id, "reason": reason, "date": current_time})
    _append_log(project, {"time": current_time, "action": "block", "task": task_id, "detail": reason})
    return {"task": task_id, "reason": reason}


def unblock_task_in_project(project: dict, task_id: str, *, now) -> dict:
    node = _find_node_in_project(project, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")
    if node.get("status") != "blocked":
        raise ValueError(f"任务未阻塞: {task_id}")

    previous = node.pop("blocked_from_status", "pending")
    if previous == "in_progress" and _undone_dependencies(project, node):
        previous = "pending"
    if previous not in ("pending", "in_progress"):
        previous = "pending"

    current_time = now()
    node["status"] = previous
    node.pop("blocked_reason", None)
    for blocker in project.get("blockers", []):
        if blocker["task_id"] == task_id and not blocker.get("resolved"):
            blocker["resolved"] = current_time
            break
    _append_log(project, {"time": current_time, "action": "unblock", "task": task_id})
    return {"task": task_id}


def add_subtask_to_project(
    project: dict,
    parent_id: str,
    subtask_id: str,
    name: str,
    *,
    now,
    **kwargs,
) -> dict:
    parent = _find_node_in_project(project, parent_id)
    if not parent:
        raise ValueError(f"父任务不存在: {parent_id}")

    full_id = f"{parent_id}.{subtask_id}"
    if _find_node_in_project(project, full_id):
        raise ValueError(f"子任务已存在: {full_id}")

    current_time = now()
    sub_node = {
        "id": full_id,
        "name": name,
        "type": "task",
        "phase": parent.get("phase", ""),
        "parent": parent_id,
        "status": "pending",
        "created": current_time,
    }
    for key in ("owner", "days", "depends", "deliverables", "description"):
        if key in kwargs and kwargs[key]:
            sub_node[key] = kwargs[key]

    project.setdefault("nodes", []).append(sub_node)

    if parent.get("status") == "pending":
        parent["status"] = "in_progress"
        parent["started"] = current_time

    _append_log(project, {"time": current_time, "action": "subtask_add", "task": full_id, "detail": name})
    return sub_node


def done_subtask_in_project(project: dict, full_id: str, *, now, note: str = "") -> dict:
    node = _find_node_in_project(project, full_id)
    if not node:
        raise ValueError(f"子任务不存在: {full_id}")

    current_time = now()
    node["status"] = "done"
    node["completed"] = current_time
    if note:
        node["note"] = note

    _append_log(project, {
        "time": current_time,
        "action": "subtask_done",
        "task": full_id,
        "detail": note or node["name"],
    })

    parent_id = node.get("parent", full_id.rsplit(".", 1)[0])
    siblings = [item for item in project.get("nodes", []) if item.get("parent") == parent_id]
    all_done = all(item.get("status") == "done" for item in siblings)

    result = {"subtask": full_id, "all_subtasks_done": all_done}
    if all_done:
        parent = _find_node_in_project(project, parent_id)
        if parent and parent.get("status") == "expanded":
            result["hint"] = "所有子任务已完成，父任务已由子任务替代。运行: pt next 查看后续任务"
        else:
            result["hint"] = f"所有子任务已完成，可以运行: pt done {parent_id}"
    return result


def block_subtask_in_project(project: dict, full_id: str, reason: str, *, now) -> None:
    node = _find_node_in_project(project, full_id)
    if not node:
        raise ValueError(f"子任务不存在: {full_id}")

    current_time = now()
    node["status"] = "blocked"
    node["blocked_reason"] = reason
    _append_log(project, {"time": current_time, "action": "subtask_block", "task": full_id, "detail": reason})


def attach_doc_to_task(
    project: dict,
    task_id: str,
    file_path: str,
    *,
    now,
    description: str = "",
) -> dict:
    node = _find_node_in_project(project, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")

    docs = node.get("docs", [])
    if any((doc.get("path") or doc.get("file")) == file_path for doc in docs):
        raise ValueError(f"文档已关联: {file_path}")

    current_time = now()
    docs.append({"path": file_path, "desc": description, "added": current_time})
    node["docs"] = docs
    _append_log(project, {
        "time": current_time,
        "action": "doc_attach",
        "task": task_id,
        "detail": f"关联文档: {file_path}",
    })
    return node
