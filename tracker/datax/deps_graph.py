"""Export a Mermaid dependency graph from project data."""

from __future__ import annotations

from ..engine import compute_cpm, build_graph
from ..project_model import _get_task_status, _project_as_flow


# Status -> fill colour
_STATUS_COLOUR = {
    "done": "#4CAF50",        # green
    "in_progress": "#2196F3", # blue
    "blocked": "#F44336",     # red
    "pending": "#9E9E9E",     # grey
}


def _sanitise_id(node_id: str) -> str:
    """Make *node_id* safe for Mermaid identifiers."""
    return node_id.replace("-", "_")


def export_deps_mermaid(project: dict) -> str:
    """Return a Mermaid ``graph LR`` diagram string for *project*.

    * Edges come from ``depends`` relationships.
    * Nodes are coloured by status.
    * Critical-path nodes receive a bold stroke style.
    * Nodes with ``status == 'expanded'`` are skipped.
    """

    flow = _project_as_flow(project)
    task_status = _get_task_status(project)
    graph = build_graph(flow)
    cpm = compute_cpm(flow, task_status)

    critical_set = set(cpm.get("critical_path", []))

    effective_nodes = {
        n["id"]: n
        for n in project.get("nodes", [])
        if n.get("status") != "expanded"
    }

    lines: list[str] = ["graph LR"]

    # -- edges --
    edge_lines: list[str] = []
    for nid, node in effective_nodes.items():
        safe_nid = _sanitise_id(nid)
        for dep_id in node.get("depends", []):
            if dep_id in effective_nodes:
                safe_dep = _sanitise_id(dep_id)
                edge_lines.append(f"    {safe_dep} --> {safe_nid}")

    # Nodes without any edge still need to appear explicitly
    mentioned: set[str] = set()
    for nid, node in effective_nodes.items():
        safe_nid = _sanitise_id(nid)
        name = node.get("name", nid)
        has_edge = False
        for dep_id in node.get("depends", []):
            if dep_id in effective_nodes:
                has_edge = True
                break
        if not has_edge:
            # Check if this node is a dependency of someone else
            if graph["rdeps"].get(nid):
                has_edge = True
        if not has_edge:
            # Standalone node -- declare it explicitly
            lines.append(f"    {safe_nid}[{name}]")
            mentioned.add(nid)

    # For nodes that participate in edges, declare with label first
    for nid, node in effective_nodes.items():
        if nid in mentioned:
            continue
        safe_nid = _sanitise_id(nid)
        name = node.get("name", nid)
        # Only declare if the node actually has edges
        deps_in = [d for d in node.get("depends", []) if d in effective_nodes]
        has_successors = bool(graph["rdeps"].get(nid))
        if deps_in or has_successors:
            lines.append(f"    {safe_nid}[{name}]")

    # Add edges
    lines.append("")
    lines.extend(edge_lines)

    # -- styles --
    lines.append("")
    for nid, node in effective_nodes.items():
        safe_nid = _sanitise_id(nid)
        status = node.get("status", "pending")
        colour = _STATUS_COLOUR.get(status, "#9E9E9E")

        if nid in critical_set:
            lines.append(
                f"    style {safe_nid} fill:{colour},stroke:#000,stroke-width:3px"
            )
        else:
            lines.append(f"    style {safe_nid} fill:{colour}")

    return "\n".join(lines) + "\n"
