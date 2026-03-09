"""Phase statistics: duration distribution per phase."""

from __future__ import annotations

from datetime import datetime


_TIME_FMT = "%Y-%m-%d %H:%M"


def _parse_dt(s: str) -> datetime | None:
    """Parse a datetime string produced by core._now()."""
    if not s:
        return None
    try:
        return datetime.strptime(s, _TIME_FMT)
    except (ValueError, TypeError):
        return None


def _percentile(sorted_vals: list[float], pct: int) -> float:
    """Return the *pct*-th percentile using nearest-rank (ceiling index).

    ``sorted_vals`` must already be sorted ascending.
    """
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    # nearest-rank: index = ceil(pct/100 * n) - 1, clamped
    idx = -(-pct * n // 100) - 1  # equivalent to math.ceil without import
    idx = max(0, min(idx, n - 1))
    return sorted_vals[idx]


def _node_actual_days(node: dict) -> float | None:
    """Compute actual elapsed days from ``started`` / ``completed``.

    Returns *None* when timestamps are missing or unparseable.
    """
    started = _parse_dt(node.get("started", ""))
    completed = _parse_dt(node.get("completed", ""))
    if started and completed and completed >= started:
        delta = completed - started
        # At least count partial days as 1
        days = delta.total_seconds() / 86400.0
        return round(days, 2) if days > 0 else 0.0
    return None


def compute_phase_stats(project: dict) -> dict:
    """Compute per-phase duration statistics.

    Only *effective* nodes (status != 'expanded') are considered.

    Returns::

        {
            "<phase_id>": {
                "count": int,
                "done": int,
                "avg_days": float,
                "p50": float,
                "p90": float,
                "max": float,
            },
            ...
            "overall": {
                "total_nodes": int,
                "done": int,
                "in_progress": int,
                "pending": int,
                "blocked": int,
            },
        }
    """

    nodes = [n for n in project.get("nodes", []) if n.get("status") != "expanded"]

    # -- per-phase buckets --
    phase_buckets: dict[str, list[dict]] = {}
    for node in nodes:
        phase = node.get("phase", "UNKNOWN")
        phase_buckets.setdefault(phase, []).append(node)

    result: dict[str, dict] = {}

    for phase_id, phase_nodes in phase_buckets.items():
        count = len(phase_nodes)
        done_nodes = [n for n in phase_nodes if n.get("status") == "done"]
        done_count = len(done_nodes)

        # Gather durations for done nodes
        durations: list[float] = []
        for n in done_nodes:
            actual = _node_actual_days(n)
            if actual is not None:
                durations.append(actual)
            else:
                # Fallback to estimated days
                durations.append(float(n.get("days", 3)))

        durations.sort()

        if durations:
            avg_days = round(sum(durations) / len(durations), 2)
            p50 = round(_percentile(durations, 50), 2)
            p90 = round(_percentile(durations, 90), 2)
            max_days = round(max(durations), 2)
        else:
            avg_days = 0.0
            p50 = 0.0
            p90 = 0.0
            max_days = 0.0

        result[phase_id] = {
            "count": count,
            "done": done_count,
            "avg_days": avg_days,
            "p50": p50,
            "p90": p90,
            "max": max_days,
        }

    # -- overall summary --
    total = len(nodes)
    done = sum(1 for n in nodes if n.get("status") == "done")
    in_progress = sum(1 for n in nodes if n.get("status") == "in_progress")
    blocked = sum(1 for n in nodes if n.get("status") == "blocked")
    pending = total - done - in_progress - blocked

    result["overall"] = {
        "total_nodes": total,
        "done": done,
        "in_progress": in_progress,
        "pending": pending,
        "blocked": blocked,
    }

    return result
