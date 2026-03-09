"""Data layer -- read-only access to project YAML files and engine results."""

from __future__ import annotations

from pathlib import Path

from tracker.core import _load, PROJECTS_DIR
from tracker.engine import compute_cpm
from tracker.project_model import (
    _progress_counts,
    _get_task_status,
    _project_as_flow,
    _effective_nodes,
)


def load_all_projects() -> list[dict]:
    """Load summary information for every project in *projects/*.yaml*."""
    PROJECTS_DIR.mkdir(exist_ok=True)
    results: list[dict] = []
    for path in sorted(PROJECTS_DIR.glob("*.yaml")):
        project = _load(path.stem)
        if project is None:
            continue
        done, total = _progress_counts(project)
        results.append(
            {
                "id": project.get("id", path.stem),
                "name": project.get("name", path.stem),
                "done": done,
                "total": total,
                "percent": round(done / total * 100, 1) if total else 0.0,
                "created": str(project.get("created", "")),
                "flow": project.get("flow", ""),
            }
        )
    return results


def load_project_detail(project_id: str) -> dict | None:
    """Load a single project with full node data and CPM analysis.

    Returns *None* when the project does not exist.
    """
    project = _load(project_id)
    if project is None:
        return None

    flow = _project_as_flow(project)
    task_status = _get_task_status(project)

    try:
        cpm = compute_cpm(flow, task_status)
    except (ValueError, KeyError):
        cpm = {"nodes": {}, "critical_path": [], "total_days": 0, "topo_order": []}

    nodes = _effective_nodes(project)
    done, total = _progress_counts(project)

    # Build per-status counts
    status_counts: dict[str, int] = {}
    for node in nodes:
        s = node.get("status", "pending")
        status_counts[s] = status_counts.get(s, 0) + 1

    # Last 10 log entries (most recent first)
    log_entries = list(reversed(project.get("log", [])[-10:]))

    # Prepare node list enriched with CPM data
    enriched_nodes: list[dict] = []
    for node in nodes:
        nid = node["id"]
        cpm_info = cpm["nodes"].get(nid, {})
        enriched_nodes.append(
            {
                "id": nid,
                "name": node.get("name", nid),
                "status": node.get("status", "pending"),
                "phase": node.get("phase", ""),
                "type": node.get("type", "task"),
                "owner": node.get("owner", ""),
                "depends": node.get("depends", []),
                "critical": cpm_info.get("critical", False),
                "slack": cpm_info.get("slack", 0),
                "es": cpm_info.get("es", 0),
                "ef": cpm_info.get("ef", 0),
                "days": cpm_info.get("days", 0),
                "deliverables": node.get("deliverables", []),
                "gate": node.get("gate", ""),
                "note": node.get("note", ""),
            }
        )

    return {
        "id": project.get("id", project_id),
        "name": project.get("name", project_id),
        "created": str(project.get("created", "")),
        "flow": project.get("flow", ""),
        "done": done,
        "total": total,
        "percent": round(done / total * 100, 1) if total else 0.0,
        "status_counts": status_counts,
        "phases": project.get("phases", []),
        "nodes": enriched_nodes,
        "critical_path": cpm.get("critical_path", []),
        "total_days": cpm.get("total_days", 0),
        "log": log_entries,
    }
