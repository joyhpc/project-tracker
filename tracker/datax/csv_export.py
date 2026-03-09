"""CSV export utilities for project data."""

from __future__ import annotations

import csv
import io


def export_nodes_csv(project: dict) -> str:
    """Export all project nodes as CSV.

    Columns: id, name, phase, status, days, owner, depends, started, completed, note
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "name", "phase", "status", "days", "owner", "depends", "started", "completed", "note"])

    for node in project.get("nodes", []):
        depends_raw = node.get("depends", [])
        if isinstance(depends_raw, list):
            depends_str = ",".join(str(d) for d in depends_raw)
        else:
            depends_str = str(depends_raw) if depends_raw else ""

        writer.writerow([
            node.get("id", ""),
            node.get("name", ""),
            node.get("phase", ""),
            node.get("status", ""),
            node.get("days", ""),
            node.get("owner", ""),
            depends_str,
            node.get("started", ""),
            node.get("completed", ""),
            node.get("note", ""),
        ])

    return buf.getvalue()


def export_stats_csv(stats: dict) -> str:
    """Export phase stats as CSV.

    Columns: phase, count, done, avg_days, p50, p90, max
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["phase", "count", "done", "avg_days", "p50", "p90", "max"])

    for phase_id, s in stats.items():
        if phase_id == "overall":
            continue
        writer.writerow([
            phase_id,
            s.get("count", 0),
            s.get("done", 0),
            s.get("avg_days", 0.0),
            s.get("p50", 0.0),
            s.get("p90", 0.0),
            s.get("max", 0.0),
        ])

    return buf.getvalue()


def export_burndown_csv(burndown: list[dict]) -> str:
    """Export burndown data as CSV.

    Columns: date, done, remaining, total
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "done", "remaining", "total"])

    for point in burndown:
        writer.writerow([
            point.get("date", ""),
            point.get("done", 0),
            point.get("remaining", 0),
            point.get("total", 0),
        ])

    return buf.getvalue()
