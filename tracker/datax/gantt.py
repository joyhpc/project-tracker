"""Export a Mermaid Gantt chart from project data."""

from __future__ import annotations

from ..engine import compute_cpm
from ..project_model import _get_task_status, _project_as_flow


# Mermaid status tag mapping
_STATUS_TAG = {
    "done": "done",
    "in_progress": "active",
    "blocked": "crit",
    # pending -> empty (no tag)
}


def _sanitise_id(node_id: str) -> str:
    """Make *node_id* safe for Mermaid identifiers (no hyphens)."""
    return node_id.replace("-", "_")


def export_gantt_mermaid(project: dict) -> str:
    """Return a Mermaid ``gantt`` diagram string for *project*.

    Nodes are grouped by phase.  Dependencies are expressed via
    ``after <dep_id>`` syntax.  Duration comes from ``node.get("days", 3)``.
    """

    flow = _project_as_flow(project)
    task_status = _get_task_status(project)
    cpm = compute_cpm(flow, task_status)

    # Build lookup tables
    nodes_by_id = {
        n["id"]: n
        for n in project.get("nodes", [])
        if n.get("status") != "expanded"
    }

    # Group effective nodes by phase, preserving CPM early-start order
    phases = project.get("phases", [])
    phase_ids = [p["id"] for p in phases]

    nodes_by_phase: dict[str, list[dict]] = {}
    for n in nodes_by_id.values():
        ph = n.get("phase", "UNKNOWN")
        nodes_by_phase.setdefault(ph, []).append(n)

    # Sort nodes within each phase by ES
    for ph in nodes_by_phase:
        nodes_by_phase[ph].sort(
            key=lambda n: (cpm["nodes"].get(n["id"], {}).get("es", 0), n["id"])
        )

    lines: list[str] = [
        "gantt",
        f"    title {project.get('name', project.get('id', 'Project'))}",
        "    dateFormat YYYY-MM-DD",
    ]

    # Iterate phases in declared order, then any remaining
    seen_phases: set[str] = set()
    ordered_phases = list(phase_ids)
    for ph in nodes_by_phase:
        if ph not in seen_phases and ph not in phase_ids:
            ordered_phases.append(ph)
    seen_phases = set()

    for phase_id in ordered_phases:
        if phase_id in seen_phases:
            continue
        seen_phases.add(phase_id)
        phase_nodes = nodes_by_phase.get(phase_id, [])
        if not phase_nodes:
            continue

        # Find the phase display name
        phase_name = phase_id
        for p in phases:
            if p["id"] == phase_id:
                phase_name = p.get("name", phase_id)
                break

        lines.append(f"    section {phase_name}")

        for node in phase_nodes:
            nid = node["id"]
            safe_id = _sanitise_id(nid)
            name = node.get("name", nid)
            status = node.get("status", "pending")
            tag = _STATUS_TAG.get(status, "")
            days = node.get("days", 3)

            # Dependency: pick the first valid dependency for ``after``
            deps = [d for d in node.get("depends", []) if d in nodes_by_id]
            if deps:
                after_clause = f"after {_sanitise_id(deps[0])}"
            else:
                after_clause = ""

            # Build the task line parts
            parts = [name]
            # status tag and id
            tag_parts: list[str] = []
            if tag:
                tag_parts.append(tag)
            tag_parts.append(safe_id)
            if after_clause:
                tag_parts.append(after_clause)
            tag_parts.append(f"{days}d")

            parts.append(", ".join(tag_parts))
            line = "    " + "      :".join(parts)
            lines.append(line)

    return "\n".join(lines) + "\n"
