"""Project map snapshot builders and renderers."""

from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path

from .close_gate import summarize_close_gates
from .project_query import get_status

LANE_ORDER = ["in_progress", "ready", "blocked", "waiting", "done"]
LANE_LABELS = {
    "in_progress": "进行中",
    "ready": "可推进",
    "blocked": "阻塞",
    "waiting": "等待依赖",
    "done": "已完成",
}
LANE_ICONS = {
    "in_progress": "⚡",
    "ready": "🟦",
    "blocked": "🚫",
    "waiting": "⏳",
    "done": "✅",
}


def _is_visible_main_node(node: dict) -> bool:
    return not node.get("parent") and node.get("status") != "expanded"


def _repo_state(project: dict) -> dict:
    repo = (project.get("repo") or "").strip()
    if not repo:
        return {"configured": False, "exists": False, "path": "", "label": "未绑定仓库"}
    exists = Path(repo).expanduser().exists()
    return {
        "configured": True,
        "exists": exists,
        "path": repo,
        "label": "仓库已连接" if exists else "仓库路径缺失",
    }


def _note_brief(node: dict, limit: int = 36) -> str:
    note = (node.get("note") or "").strip().replace("\n", " ")
    if len(note) <= limit:
        return note
    return note[: limit - 1] + "…"


def _select_focus(entries: list[dict]) -> dict | None:
    in_progress = [entry for entry in entries if entry["lane"] == "in_progress"]
    if in_progress:
        return sorted(
            in_progress,
            key=lambda entry: (
                not entry["critical"],
                entry.get("started") or "",
                entry["order"],
            ),
        )[0]

    ready = [entry for entry in entries if entry["lane"] == "ready"]
    if ready:
        return sorted(
            ready,
            key=lambda entry: (
                not entry["critical"],
                entry["slack"],
                entry["order"],
            ),
        )[0]
    return None


def build_project_map(project: dict, info: dict | None = None) -> dict:
    if info is None:
        info = get_status(project)

    phases = project.get("phases", [])
    phase_index = {phase["id"]: idx for idx, phase in enumerate(phases)}
    nodes_map = {node["id"]: node for node in project.get("nodes", [])}
    cpm = info.get("cpm", {}) or {}
    cpm_nodes = cpm.get("nodes", {}) or {}
    classified = info.get("classified", {}) or {}
    ready_ids = {node["id"] for node in classified.get("ready", [])}
    waiting_by_id = {node["id"]: node for node in classified.get("waiting", [])}
    critical_path = cpm.get("critical_path", []) or []

    visible_nodes = [node for node in project.get("nodes", []) if _is_visible_main_node(node)]
    visible_ids = {node["id"] for node in visible_nodes}

    topo_order = [node_id for node_id in cpm.get("topo_order", []) if node_id in visible_ids]
    remaining_ids = sorted(
        visible_ids - set(topo_order),
        key=lambda node_id: (
            phase_index.get(nodes_map[node_id].get("phase", ""), 999),
            node_id,
        ),
    )
    ordered_ids = topo_order + remaining_ids
    order_index = {node_id: idx for idx, node_id in enumerate(ordered_ids)}
    close_summary = summarize_close_gates(project)
    close_by_id = {entry["task_id"]: entry for entry in close_summary.get("entries", [])}

    entries = []
    for node_id in ordered_ids:
        node = nodes_map[node_id]
        status = node.get("status", "pending")
        if status in ("done", "skipped"):
            lane = "done"
        elif status == "blocked":
            lane = "blocked"
        elif status == "in_progress":
            lane = "in_progress"
        elif node_id in ready_ids:
            lane = "ready"
        else:
            lane = "waiting"

        waiting_for = waiting_by_id.get(node_id, {}).get("_waiting_for", [])
        entry = {
            "id": node_id,
            "name": node.get("name", node_id),
            "phase": node.get("phase", ""),
            "phase_name": next((phase.get("name", phase["id"]) for phase in phases if phase["id"] == node.get("phase")), node.get("phase", "")),
            "lane": lane,
            "status": status,
            "owner": node.get("owner", ""),
            "days": cpm_nodes.get(node_id, {}).get("days", node.get("days", 0)),
            "slack": cpm_nodes.get(node_id, {}).get("slack", 0),
            "critical": node_id in critical_path or bool(cpm_nodes.get(node_id, {}).get("critical")),
            "waiting_for": waiting_for,
            "waiting_for_names": [nodes_map.get(dep_id, {}).get("name", dep_id) for dep_id in waiting_for],
            "blocked_reason": node.get("blocked_reason", ""),
            "depends": node.get("depends", []),
            "depends_names": [nodes_map.get(dep_id, {}).get("name", dep_id) for dep_id in node.get("depends", [])],
            "docs_count": len(node.get("docs", []) or []),
            "has_note": bool(node.get("note") or node.get("note_file")),
            "note": _note_brief(node),
            "note_file": node.get("note_file", ""),
            "is_milestone": node.get("type") == "milestone",
            "started": node.get("started", ""),
            "completed": node.get("completed", ""),
            "close_required": bool(close_by_id.get(node_id)),
            "close_valid": close_by_id.get(node_id, {}).get("valid", True),
            "close_issue_count": close_by_id.get(node_id, {}).get("issue_count", 0),
            "order": order_index[node_id],
        }
        entries.append(entry)

    focus = _select_focus(entries)
    if focus:
        for entry in entries:
            entry["is_focus"] = entry["id"] == focus["id"]
    else:
        for entry in entries:
            entry["is_focus"] = False

    phase_sections = []
    for phase in phases:
        phase_entries = [entry for entry in entries if entry["phase"] == phase["id"]]
        if not phase_entries:
            continue

        total = len(phase_entries)
        done_count = sum(1 for entry in phase_entries if entry["status"] in ("done", "skipped"))
        progress_pct = int(done_count / total * 100) if total else 0
        lanes = {lane: [entry for entry in phase_entries if entry["lane"] == lane] for lane in LANE_ORDER}

        phase_sections.append({
            "id": phase["id"],
            "name": phase.get("name", phase["id"]),
            "milestone": phase.get("milestone", ""),
            "entries": phase_entries,
            "lanes": lanes,
            "done": done_count,
            "total": total,
            "progress": f"{done_count}/{total}",
            "progress_pct": progress_pct,
            "complete": done_count == total and total > 0,
        })

    warnings = info.get("warnings", []) or []
    warning_counts = Counter(issue.get("severity", "info") for issue in warnings)
    decisions = [decision for decision in project.get("decisions", []) if decision.get("status") == "active"]
    blockers = [entry for entry in entries if entry["lane"] == "blocked"]
    ready_entries = [entry for entry in entries if entry["lane"] == "ready"]
    waiting_entries = [entry for entry in entries if entry["lane"] == "waiting"]
    in_progress_entries = [entry for entry in entries if entry["lane"] == "in_progress"]
    done_entries = [entry for entry in entries if entry["lane"] == "done"]
    child_nodes = [node for node in project.get("nodes", []) if node.get("parent")]
    active_child_nodes = [node for node in child_nodes if node.get("status") not in ("done", "skipped")]

    return {
        "project_id": project.get("id", ""),
        "project_name": project.get("name", ""),
        "project": project,
        "repo": _repo_state(project),
        "metrics": {
            "done_count": info.get("done_count", 0),
            "total": info.get("total", 0),
            "progress_pct": int(info.get("done_count", 0) / info.get("total", 1) * 100) if info.get("total", 0) else 0,
            "total_days": cpm.get("total_days", 0),
            "critical_count": len([entry for entry in entries if entry["critical"]]),
            "ready_count": len(ready_entries),
            "blocked_count": len(blockers),
            "in_progress_count": len(in_progress_entries),
            "done_visible_count": len(done_entries),
            "docs_total": sum(entry["docs_count"] for entry in entries),
            "tasks_with_docs": sum(1 for entry in entries if entry["docs_count"] > 0),
            "active_decision_count": len(decisions),
            "active_subtask_count": len(active_child_nodes),
            "close_required_count": close_summary.get("required_count", 0),
            "close_invalid_count": close_summary.get("invalid_count", 0),
        },
        "focus": focus,
        "parallel_ready": [entry for entry in ready_entries if not focus or entry["id"] != focus["id"]],
        "blocked": blockers,
        "waiting": waiting_entries,
        "critical_path": [next(entry for entry in entries if entry["id"] == node_id) for node_id in critical_path if any(entry["id"] == node_id for entry in entries)],
        "phases": phase_sections,
        "entries": entries,
        "warnings": warnings,
        "warning_counts": dict(warning_counts),
        "active_decisions": decisions,
        "close_gates": close_summary,
    }


def _phase_bar(done: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "░" * width
    fill = round(done / total * width)
    return "█" * fill + "░" * (width - fill)


def _entry_line(entry: dict) -> str:
    owner = f" ← {entry['owner']}" if entry.get("owner") else ""
    crit = " 🔴" if entry.get("critical") else ""
    slack = "" if entry.get("critical") else f" slack={entry['slack']:.0f}d"
    milestone = " 🏁" if entry.get("is_milestone") else ""
    extras = []
    if entry.get("docs_count"):
        extras.append(f"docs={entry['docs_count']}")
    if entry.get("has_note"):
        extras.append("有备注")
    if entry.get("close_required"):
        if entry.get("close_valid"):
            extras.append("close=OK")
        else:
            extras.append(f"close=NG({entry.get('close_issue_count', 0)})")
    if entry["lane"] == "waiting" and entry.get("waiting_for_names"):
        extras.append("等待: " + ", ".join(entry["waiting_for_names"][:3]))
    if entry["lane"] == "blocked" and entry.get("blocked_reason"):
        extras.append("原因: " + entry["blocked_reason"])
    extra_str = f" | {' | '.join(extras)}" if extras else ""
    return f"    {LANE_ICONS[entry['lane']]} [{entry['id']}] {entry['name']}{milestone}{crit}{slack}{owner}{extra_str}"


def render_project_map_text(map_data: dict) -> str:
    metrics = map_data["metrics"]
    repo = map_data["repo"]
    focus = map_data.get("focus")
    close_gates = map_data.get("close_gates", {})
    lines = []
    lines.append("=" * 68)
    lines.append(f"📋 {map_data['project_name']} ({map_data['project_id']}) - 项目地图")
    lines.append("=" * 68)
    lines.append(
        f"进度 {metrics['done_count']}/{metrics['total']} ({metrics['progress_pct']}%) | "
        f"总工期 {metrics['total_days']:.0f} 天 | 关键路径 {len(map_data['critical_path'])} 节点"
    )
    lines.append(
        f"仓库状态: {repo['label']}" + (f" | {repo['path']}" if repo.get('path') else "")
    )
    if metrics["active_subtask_count"]:
        lines.append(f"已展开子任务: {metrics['active_subtask_count']} 个活跃子任务（主地图默认隐藏）")
    warning_total = sum(map_data["warning_counts"].values())
    if warning_total:
        lines.append(
            "完整性提示: "
            + ", ".join(
                f"{severity}={count}" for severity, count in sorted(map_data["warning_counts"].items()) if count
            )
        )
    if metrics["close_required_count"]:
        lines.append(
            f"Merge-to-Close: required={metrics['close_required_count']} | invalid={metrics['close_invalid_count']}"
        )
    lines.append("")

    lines.append("🎯 当前焦点")
    if focus:
        lines.append(_entry_line(focus))
        if focus.get("waiting_for_names"):
            lines.append("    依赖: " + ", ".join(focus["waiting_for_names"]))
    else:
        lines.append("    暂无进行中/可推进任务")
    lines.append("")

    lines.append(f"🟦 可并行推进 ({len(map_data['parallel_ready'])})")
    if map_data["parallel_ready"]:
        for entry in map_data["parallel_ready"][:5]:
            lines.append(_entry_line(entry))
    else:
        lines.append("    暂无")
    lines.append("")

    lines.append(f"🚫 当前阻塞 ({len(map_data['blocked'])})")
    if map_data["blocked"]:
        for entry in map_data["blocked"][:5]:
            lines.append(_entry_line(entry))
    else:
        lines.append("    暂无")
    lines.append("")

    lines.append("🔴 关键路径")
    if map_data["critical_path"]:
        lines.append("    " + " → ".join(entry["name"] for entry in map_data["critical_path"][:8]))
        if len(map_data["critical_path"]) > 8:
            lines.append(f"    ... 共 {len(map_data['critical_path'])} 个关键节点")
    else:
        lines.append("    暂无")
    lines.append("")

    if map_data["active_decisions"]:
        lines.append(f"📌 生效决策 ({len(map_data['active_decisions'])})")
        for decision in map_data["active_decisions"][:4]:
            lines.append(f"    D{decision['id']}: {decision['title']}")
        lines.append("")

    if close_gates.get("required_count"):
        lines.append(
            f"🔒 Merge-to-Close ({close_gates['required_count']})"
        )
        invalid_entries = [entry for entry in close_gates.get("entries", []) if not entry.get("valid")]
        if invalid_entries:
            for entry in invalid_entries[:6]:
                lines.append(
                    f"    ❌ [{entry['task_id']}] {entry['name']} | status={entry['status']} | issues={entry['issue_count']}"
                )
                if entry.get("top_issues"):
                    lines.append("       " + " | ".join(entry["top_issues"]))
            if len(invalid_entries) > 6:
                lines.append(f"    ... 还有 {len(invalid_entries)-6} 个")
        else:
            lines.append("    ✅ 所有 close gate 已满足")
        lines.append("")

    for phase in map_data["phases"]:
        milestone = f" | {phase['milestone']}" if phase.get("milestone") else ""
        lines.append(
            f"📍 {phase['name']} [{_phase_bar(phase['done'], phase['total'])}] {phase['progress']} ({phase['progress_pct']}%){milestone}"
        )
        for lane in LANE_ORDER:
            entries = phase["lanes"][lane]
            if not entries:
                continue
            lines.append(f"  {LANE_ICONS[lane]} {LANE_LABELS[lane]} ({len(entries)})")
            for entry in entries[:6]:
                lines.append(_entry_line(entry))
            if len(entries) > 6:
                lines.append(f"    ... 还有 {len(entries)-6} 个")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _card_html(entry: dict) -> str:
    detail_bits = []
    if entry.get("owner"):
        detail_bits.append(escape(entry["owner"]))
    if entry.get("docs_count"):
        detail_bits.append(f"docs={entry['docs_count']}")
    if entry.get("days"):
        detail_bits.append(f"{entry['days']:.0f}天")
    if entry.get("critical"):
        detail_bits.append("critical")
    elif entry.get("slack"):
        detail_bits.append(f"slack={entry['slack']:.0f}d")
    if entry.get("close_required"):
        detail_bits.append("close=OK" if entry.get("close_valid") else f"close=NG({entry.get('close_issue_count', 0)})")

    message = ""
    if entry["lane"] == "waiting" and entry.get("waiting_for_names"):
        message = "等待: " + ", ".join(entry["waiting_for_names"][:3])
    elif entry["lane"] == "blocked" and entry.get("blocked_reason"):
        message = entry["blocked_reason"]
    elif entry.get("note"):
        message = entry["note"]
    elif entry.get("note_file"):
        message = entry["note_file"]

    milestone = '<span class="pill milestone">里程碑</span>' if entry.get("is_milestone") else ""
    focus = '<span class="pill focus">当前焦点</span>' if entry.get("is_focus") else ""
    critical = '<span class="pill critical">关键路径</span>' if entry.get("critical") else ""
    close_gate = ""
    if entry.get("close_required"):
        close_gate = (
            '<span class="pill close-ok">Close OK</span>'
            if entry.get("close_valid")
            else f'<span class="pill close-ng">Close NG({entry.get("close_issue_count", 0)})</span>'
        )
    classes = ["task-card", entry["lane"]]
    if entry.get("is_focus"):
        classes.append("focus")
    if entry.get("critical"):
        classes.append("critical")

    return f'''<div class="{' '.join(classes)}">
<div class="task-head">
  <div class="task-title">{escape(entry['name'])}</div>
  <div class="task-id">[{escape(entry['id'])}]</div>
</div>
<div class="task-pills">{focus}{critical}{milestone}{close_gate}</div>
<div class="task-meta">{' · '.join(detail_bits) if detail_bits else '&nbsp;'}</div>
<div class="task-msg">{escape(message) if message else '—'}</div>
</div>'''


def render_project_map_html(map_data: dict) -> str:
    metrics = map_data["metrics"]
    repo = map_data["repo"]
    focus = map_data.get("focus")
    close_gates = map_data.get("close_gates", {})
    critical_cards = "".join(_card_html(entry) for entry in map_data["critical_path"][:8])
    decision_html = "".join(
        f'<div class="simple-item">D{decision["id"]}: {escape(decision["title"])}</div>'
        for decision in map_data["active_decisions"][:6]
    )
    blocker_html = "".join(
        f'<div class="simple-item">{escape(entry["name"])}：{escape(entry.get("blocked_reason") or "已阻塞")}</div>'
        for entry in map_data["blocked"][:6]
    )
    parallel_items = []
    for entry in map_data["parallel_ready"][:6]:
        suffix = " · 🔴" if entry.get("critical") else f" · slack={entry['slack']:.0f}d"
        parallel_items.append(f'<div class="simple-item">{escape(entry["name"])}{suffix}</div>')
    parallel_html = "".join(parallel_items)
    close_invalid_html = "".join(
        f'<div class="simple-item">[{escape(entry["task_id"])}] {escape(entry["name"])} · issues={entry["issue_count"]}</div>'
        for entry in close_gates.get("entries", [])
        if not entry.get("valid")
    )
    close_panel_html = ""
    if metrics["close_required_count"]:
        close_panel_body = close_invalid_html or '<div class="simple-item">✅ 所有 close gate 已满足</div>'
        close_panel_html = f'<div class="panel"><div class="panel-title">🔒 Merge-to-Close</div>{close_panel_body}</div>'

    phase_html = ""
    for phase in map_data["phases"]:
        lanes_html = ""
        for lane in LANE_ORDER:
            entries = phase["lanes"][lane]
            cards = "".join(_card_html(entry) for entry in entries) if entries else '<div class="lane-empty">暂无</div>'
            lanes_html += f'''<div class="lane lane-{lane}">
<div class="lane-title">{LANE_ICONS[lane]} {LANE_LABELS[lane]} <span>{len(entries)}</span></div>
{cards}
</div>'''
        milestone = f' <span class="phase-milestone">{escape(phase["milestone"])}</span>' if phase.get("milestone") else ""
        phase_html += f'''<section class="phase-section">
<div class="phase-top">
  <div class="phase-name">{escape(phase['name'])}{milestone}</div>
  <div class="phase-progress">{phase['progress']} ({phase['progress_pct']}%)</div>
</div>
<div class="phase-bar"><div class="phase-fill" style="width:{phase['progress_pct']}%"></div></div>
<div class="lane-grid">{lanes_html}</div>
</section>'''

    warning_bits = "".join(
        f'<div class="metric-card compact"><div class="metric-label">{escape(severity)}</div><div class="metric-value">{count}</div></div>'
        for severity, count in sorted(map_data["warning_counts"].items()) if count
    )

    focus_html = _card_html(focus) if focus else '<div class="simple-item">暂无进行中/可推进任务</div>'
    return f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(map_data['project_name'])} — 项目地图</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Noto Sans SC', sans-serif; }}
.page {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
h1 {{ margin: 0 0 6px; font-size: 28px; }}
.subtitle {{ color: #8b949e; margin-bottom: 20px; }}
.hero-grid, .info-grid, .warn-grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 16px; }}
.metric-card, .panel, .phase-section {{ background: #161b22; border: 1px solid #30363d; border-radius: 14px; padding: 16px; }}
.metric-card.compact {{ padding: 12px; }}
.metric-label {{ color: #8b949e; font-size: 12px; margin-bottom: 6px; }}
.metric-value {{ font-size: 24px; font-weight: 700; }}
.panel-title {{ font-size: 15px; font-weight: 700; margin-bottom: 10px; }}
.simple-item {{ font-size: 13px; line-height: 1.55; color: #c9d1d9; margin: 4px 0; }}
.phase-section {{ margin-bottom: 18px; }}
.phase-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 10px; }}
.phase-name {{ font-size: 18px; font-weight: 700; }}
.phase-milestone {{ color: #bc8cff; font-size: 12px; margin-left: 8px; }}
.phase-progress {{ color: #8b949e; font-size: 13px; }}
.phase-bar {{ height: 8px; background: #21262d; border-radius: 999px; overflow: hidden; margin-bottom: 14px; }}
.phase-fill {{ height: 100%; background: linear-gradient(90deg, #388bfd, #3fb950); border-radius: 999px; }}
.lane-grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
.lane {{ background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 12px; min-height: 120px; }}
.lane-title {{ font-size: 13px; font-weight: 700; margin-bottom: 10px; display: flex; justify-content: space-between; }}
.lane-empty {{ color: #6e7681; font-size: 12px; padding: 8px 4px; }}
.task-card {{ border: 1px solid #30363d; border-left: 4px solid #30363d; border-radius: 10px; padding: 10px; margin-bottom: 10px; background: #161b22; }}
.task-card.ready {{ border-left-color: #388bfd; }}
.task-card.in_progress {{ border-left-color: #f0883e; background: #2a1800; }}
.task-card.blocked {{ border-left-color: #f85149; background: #2a0a0a; }}
.task-card.waiting {{ border-left-color: #6e7681; }}
.task-card.done {{ border-left-color: #238636; background: #0d2818; }}
.task-card.critical {{ box-shadow: inset 0 0 0 1px rgba(248,81,73,0.25); }}
.task-card.focus {{ outline: 1px solid #f0883e; }}
.task-head {{ display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }}
.task-title {{ font-size: 14px; font-weight: 700; }}
.task-id {{ color: #8b949e; font-size: 11px; }}
.task-pills {{ display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0; }}
.pill {{ font-size: 10px; padding: 2px 6px; border-radius: 999px; border: 1px solid #30363d; color: #c9d1d9; }}
.pill.focus {{ border-color: #f0883e; color: #f0883e; }}
.pill.critical {{ border-color: #f85149; color: #f85149; }}
.pill.milestone {{ border-color: #8957e5; color: #bc8cff; }}
.pill.close-ok {{ border-color: #3fb950; color: #3fb950; }}
.pill.close-ng {{ border-color: #f85149; color: #f85149; }}
.task-meta {{ color: #8b949e; font-size: 11px; margin-bottom: 6px; min-height: 15px; }}
.task-msg {{ font-size: 12px; line-height: 1.45; color: #c9d1d9; }}
.critical-strip {{ display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
.repo-ok {{ color: #3fb950; }}
.repo-warn {{ color: #f0883e; }}
@media (max-width: 800px) {{ .page {{ padding: 16px; }} h1 {{ font-size: 24px; }} }}
</style>
</head>
<body>
<div class="page">
<h1>{escape(map_data['project_name'])} — 项目地图</h1>
<div class="subtitle">{escape(map_data['project_id'])} | 进度 {metrics['done_count']}/{metrics['total']} ({metrics['progress_pct']}%) | 总工期 {metrics['total_days']:.0f} 天</div>

<div class="hero-grid">
  <div class="metric-card"><div class="metric-label">总进度</div><div class="metric-value">{metrics['progress_pct']}%</div></div>
  <div class="metric-card"><div class="metric-label">关键路径</div><div class="metric-value">{len(map_data['critical_path'])}</div></div>
  <div class="metric-card"><div class="metric-label">可推进</div><div class="metric-value">{metrics['ready_count']}</div></div>
  <div class="metric-card"><div class="metric-label">阻塞</div><div class="metric-value">{metrics['blocked_count']}</div></div>
  <div class="metric-card"><div class="metric-label">文档覆盖</div><div class="metric-value">{metrics['tasks_with_docs']}/{metrics['total']}</div></div>
  <div class="metric-card"><div class="metric-label">Close Gate</div><div class="metric-value">{metrics['close_invalid_count']}/{metrics['close_required_count']}</div></div>
  <div class="metric-card"><div class="metric-label">生效决策</div><div class="metric-value">{metrics['active_decision_count']}</div></div>
</div>

<div class="info-grid">
  <div class="panel"><div class="panel-title">🎯 当前焦点</div>{focus_html}</div>
  <div class="panel"><div class="panel-title">🟦 可并行推进</div>{parallel_html or '<div class="simple-item">暂无</div>'}</div>
  <div class="panel"><div class="panel-title">🚫 当前阻塞</div>{blocker_html or '<div class="simple-item">暂无</div>'}</div>
  <div class="panel"><div class="panel-title">📦 仓库状态</div><div class="simple-item {'repo-ok' if repo['exists'] else 'repo-warn'}">{escape(repo['label'])}</div><div class="simple-item">{escape(repo['path'] or '未设置 repo 路径')}</div></div>
</div>

{close_panel_html}

<div class="panel"><div class="panel-title">🔴 关键路径</div><div class="critical-strip">{critical_cards or '<div class="simple-item">暂无</div>'}</div></div>

{f'<div class="panel"><div class="panel-title">📌 生效决策</div>{decision_html}</div>' if decision_html else ''}
{f'<div class="warn-grid">{warning_bits}</div>' if warning_bits else ''}

{phase_html}
</div>
</body>
</html>'''
