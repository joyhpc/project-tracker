"""Project read/query helpers and status assembly."""

from __future__ import annotations

from . import engine
from .project_model import _effective_nodes, _get_task_status, _progress_counts, _project_as_flow
from .project_validation import check_integrity



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
        node["id"]: {"days": 0, "es": 0, "ef": 0, "ls": 0, "lf": 0, "slack": 0, "critical": False}
        for node in _effective_nodes(project)
    }
    return {
        "nodes": nodes,
        "critical_path": [],
        "total_days": 0,
        "topo_order": [],
    }



def get_status(project: dict) -> dict:
    """获取项目状态概览。"""
    flow = _project_as_flow(project)
    task_status = _get_task_status(project)
    warnings = check_integrity(project)
    hard_errors = [issue for issue in warnings if issue.get("severity") in ("error", "critical")]

    if hard_errors:
        classified = _fallback_classified(project)
        cpm = _fallback_cpm(project)
    else:
        classified = engine.classify_tasks(flow, task_status)
        cpm = engine.compute_cpm(flow, task_status)
        warnings = check_integrity(project, cpm)

    done_count, total = _progress_counts(project)
    active_blockers = [blocker for blocker in project.get("blockers", []) if not blocker.get("resolved")]

    return {
        "project": project,
        "classified": classified,
        "cpm": cpm,
        "blockers": active_blockers,
        "total": total,
        "done_count": done_count,
        "warnings": warnings,
    }
