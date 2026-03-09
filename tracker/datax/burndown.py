"""Burndown chart and velocity analysis."""

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


def compute_burndown(project: dict) -> list[dict]:
    """Extract burndown data points from the project log.

    Iterates over ``project["log"]`` and records a data point each time
    a "done" action is encountered.

    Returns::

        [
            {"date": "2025-01-05", "done": 1, "remaining": 19, "total": 20},
            {"date": "2025-01-08", "done": 2, "remaining": 18, "total": 20},
            ...
        ]
    """
    nodes = [n for n in project.get("nodes", []) if n.get("status") != "expanded"]
    total = len(nodes)

    done_entries = [
        entry for entry in project.get("log", [])
        if entry.get("action") == "done"
    ]

    points: list[dict] = []
    done_count = 0
    for entry in done_entries:
        done_count += 1
        raw_time = entry.get("time", "")
        dt = _parse_dt(raw_time)
        date_str = dt.strftime("%Y-%m-%d") if dt else raw_time[:10] if len(raw_time) >= 10 else raw_time
        points.append({
            "date": date_str,
            "done": done_count,
            "remaining": total - done_count,
            "total": total,
        })

    return points


def compute_velocity(project: dict) -> dict:
    """Compute completion velocity statistics.

    Based on timestamps of "done" events in the log, computes:
    - daily velocity (tasks per day)
    - weekly velocity (tasks per week)
    - estimated remaining days

    Returns::

        {
            "completed_count": int,
            "remaining_count": int,
            "total_count": int,
            "first_done_date": str,
            "last_done_date": str,
            "elapsed_days": float,
            "daily_velocity": float,
            "weekly_velocity": float,
            "estimated_remaining_days": float | None,
        }
    """
    nodes = [n for n in project.get("nodes", []) if n.get("status") != "expanded"]
    total = len(nodes)

    done_entries = [
        entry for entry in project.get("log", [])
        if entry.get("action") == "done"
    ]
    completed = len(done_entries)
    remaining = total - completed

    if not done_entries:
        return {
            "completed_count": 0,
            "remaining_count": remaining,
            "total_count": total,
            "first_done_date": "",
            "last_done_date": "",
            "elapsed_days": 0.0,
            "daily_velocity": 0.0,
            "weekly_velocity": 0.0,
            "estimated_remaining_days": None,
        }

    # Parse dates
    first_dt = _parse_dt(done_entries[0].get("time", ""))
    last_dt = _parse_dt(done_entries[-1].get("time", ""))

    first_date_str = first_dt.strftime("%Y-%m-%d") if first_dt else ""
    last_date_str = last_dt.strftime("%Y-%m-%d") if last_dt else ""

    if first_dt and last_dt and last_dt > first_dt:
        elapsed_days = (last_dt - first_dt).total_seconds() / 86400.0
    else:
        # All done on same day or unparseable — treat as 1 day
        elapsed_days = 1.0

    daily_velocity = completed / elapsed_days if elapsed_days > 0 else 0.0
    weekly_velocity = daily_velocity * 7.0

    estimated_remaining_days: float | None = None
    if daily_velocity > 0 and remaining > 0:
        estimated_remaining_days = round(remaining / daily_velocity, 1)
    elif remaining == 0:
        estimated_remaining_days = 0.0

    return {
        "completed_count": completed,
        "remaining_count": remaining,
        "total_count": total,
        "first_done_date": first_date_str,
        "last_done_date": last_date_str,
        "elapsed_days": round(elapsed_days, 2),
        "daily_velocity": round(daily_velocity, 2),
        "weekly_velocity": round(weekly_velocity, 2),
        "estimated_remaining_days": estimated_remaining_days,
    }


def format_burndown_text(burndown: list[dict]) -> str:
    """Format burndown data as a terminal-friendly ASCII art chart.

    Draws a simple burndown curve using block characters::

        remaining
        20 |████████████████████
        18 |██████████████████
        15 |███████████████
        10 |██████████
         5 |█████
         0 |
           +--------------------
            01/05  01/10  01/15
    """
    if not burndown:
        return "No burndown data available."

    total = burndown[0]["total"] if burndown else 0
    if total == 0:
        return "No tasks in project."

    lines: list[str] = []
    max_bar_width = 40
    label_width = len(str(total)) + 1  # width for the y-axis label

    lines.append("remaining")

    # Collect unique data points (deduplicate by date, keep last per date)
    seen: dict[str, dict] = {}
    for point in burndown:
        seen[point["date"]] = point
    unique_points = list(seen.values())

    for point in unique_points:
        remaining = point["remaining"]
        bar_len = int((remaining / total) * max_bar_width) if total > 0 else 0
        bar = "\u2588" * bar_len
        lines.append(f"{remaining:>{label_width}} |{bar}")

    # X-axis
    lines.append(f"{'':{label_width}} +{'-' * max_bar_width}")

    # Date labels
    dates = [p["date"] for p in unique_points]
    if dates:
        # Show first, middle, and last dates
        date_labels = []
        for d in dates:
            # Convert YYYY-MM-DD to MM/DD
            parts = d.split("-")
            if len(parts) >= 3:
                date_labels.append(f"{parts[1]}/{parts[2]}")
            else:
                date_labels.append(d)

        if len(date_labels) <= 5:
            label_line = "  ".join(date_labels)
        else:
            # Show first, 25%, 50%, 75%, last
            indices = [0, len(date_labels) // 4, len(date_labels) // 2,
                       3 * len(date_labels) // 4, len(date_labels) - 1]
            label_line = "  ".join(date_labels[i] for i in indices)
        lines.append(f"{'':{label_width}}  {label_line}")

    return "\n".join(lines)


def export_burndown_mermaid(burndown: list[dict], project_name: str = "") -> str:
    """Export burndown data in Mermaid xychart-beta format.

    Returns::

        xychart-beta
            title "Project Burndown"
            x-axis ["01/05", "01/08", ...]
            y-axis "Remaining" 0 --> 20
            line [19, 18, 15, 10, 5, 0]
    """
    if not burndown:
        return 'xychart-beta\n    title "Burndown"\n    x-axis ["N/A"]\n    y-axis "Remaining" 0 --> 1\n    line [0]'

    total = burndown[0]["total"] if burndown else 0
    title = f"{project_name} Burndown" if project_name else "Burndown"

    # Deduplicate by date (keep last per date)
    seen: dict[str, dict] = {}
    for point in burndown:
        seen[point["date"]] = point
    unique_points = list(seen.values())

    # Format dates as MM/DD
    x_labels: list[str] = []
    remaining_vals: list[int] = []
    for p in unique_points:
        parts = p["date"].split("-")
        if len(parts) >= 3:
            x_labels.append(f"{parts[1]}/{parts[2]}")
        else:
            x_labels.append(p["date"])
        remaining_vals.append(p["remaining"])

    x_axis_str = ", ".join(f'"{lbl}"' for lbl in x_labels)
    y_vals_str = ", ".join(str(v) for v in remaining_vals)

    lines = [
        "xychart-beta",
        f'    title "{title}"',
        f"    x-axis [{x_axis_str}]",
        f'    y-axis "Remaining" 0 --> {total}',
        f"    line [{y_vals_str}]",
    ]
    return "\n".join(lines)
