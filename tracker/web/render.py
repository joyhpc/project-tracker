"""HTML rendering helpers -- pure functions that return self-contained HTML."""

from __future__ import annotations

import html as _html

# ---------------------------------------------------------------------------
# Shared styles / layout
# ---------------------------------------------------------------------------

_COMMON_CSS = """\
:root {
  --bg: #0f172a;
  --bg-card: #1e293b;
  --bg-hover: #334155;
  --text: #e2e8f0;
  --text-dim: #94a3b8;
  --accent: #38bdf8;
  --green: #22c55e;
  --yellow: #eab308;
  --red: #ef4444;
  --orange: #f97316;
  --purple: #a78bfa;
  --border: #334155;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  min-height: 100vh;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.container { max-width: 1200px; margin: 0 auto; padding: 1rem 1.5rem; }
header {
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}
header h1 { font-size: 1.25rem; font-weight: 600; }
header .breadcrumb { color: var(--text-dim); font-size: 0.875rem; }
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1.4;
}
.badge-done   { background: var(--green); color: #000; }
.badge-in_progress { background: var(--yellow); color: #000; }
.badge-pending { background: var(--border); color: var(--text-dim); }
.badge-blocked { background: var(--red); color: #fff; }
.badge-expanded { background: var(--purple); color: #fff; }
.badge-skipped { background: var(--text-dim); color: #000; }
.badge-critical { background: var(--orange); color: #000; }
.badge-milestone { background: var(--purple); color: #fff; }
"""


def _e(text: str) -> str:
    """Escape HTML."""
    return _html.escape(str(text)) if text else ""


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(title)}</title>
<style>{_COMMON_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Project list page
# ---------------------------------------------------------------------------

def render_project_list(projects: list[dict]) -> str:
    """Return a full HTML page listing all projects."""
    rows = []
    for p in projects:
        pct = p.get("percent", 0)
        done = p.get("done", 0)
        total = p.get("total", 0)
        pid = _e(p.get("id", ""))
        name = _e(p.get("name", pid))
        created = _e(p.get("created", ""))
        bar_color = "var(--green)" if pct == 100 else "var(--accent)"
        rows.append(f"""
        <a href="/project/{pid}" class="project-card">
          <div class="project-card-header">
            <span class="project-name">{name}</span>
            <span class="project-id">{pid}</span>
          </div>
          <div class="progress-row">
            <div class="progress-bar">
              <div class="progress-fill" style="width:{pct}%; background:{bar_color};"></div>
            </div>
            <span class="progress-text">{done}/{total} ({pct}%)</span>
          </div>
          <div class="project-meta">Created: {created}</div>
        </a>""")

    count = len(projects)
    body = f"""
<header>
  <h1>Project Tracker</h1>
  <span class="breadcrumb">{count} project{"s" if count != 1 else ""}</span>
</header>
<div class="container">
  <div class="project-grid">
    {"".join(rows) if rows else "<p style='color:var(--text-dim);'>No projects found.</p>"}
  </div>
</div>
<style>
.project-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}}
.project-card {{
  display: block;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1rem 1.25rem;
  transition: border-color 0.15s;
  text-decoration: none !important;
  color: var(--text);
}}
.project-card:hover {{ border-color: var(--accent); }}
.project-card-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem; }}
.project-name {{ font-size: 1.1rem; font-weight: 600; }}
.project-id {{ color: var(--text-dim); font-size: 0.8rem; font-family: monospace; }}
.progress-row {{ display: flex; align-items: center; gap: 0.75rem; }}
.progress-bar {{
  flex: 1;
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}}
.progress-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
.progress-text {{ font-size: 0.8rem; color: var(--text-dim); white-space: nowrap; }}
.project-meta {{ font-size: 0.75rem; color: var(--text-dim); margin-top: 0.5rem; }}
</style>
"""
    return _page("Project Tracker", body)


# ---------------------------------------------------------------------------
# Single project dashboard
# ---------------------------------------------------------------------------

_STATUS_COLORS = {
    "done": "var(--green)",
    "in_progress": "var(--yellow)",
    "pending": "#475569",
    "blocked": "var(--red)",
    "expanded": "var(--purple)",
    "skipped": "var(--text-dim)",
}

_STATUS_LABELS = {
    "done": "Done",
    "in_progress": "In Progress",
    "pending": "Pending",
    "blocked": "Blocked",
    "expanded": "Expanded",
    "skipped": "Skipped",
}


def render_dashboard(project: dict) -> str:
    """Return a full HTML page showing the kanban-style dashboard for *project*."""
    pid = _e(project.get("id", ""))
    pname = _e(project.get("name", pid))
    done = project.get("done", 0)
    total = project.get("total", 0)
    pct = project.get("percent", 0)
    total_days = project.get("total_days", 0)
    critical_path = project.get("critical_path", [])
    status_counts = project.get("status_counts", {})
    phases = project.get("phases", [])
    nodes = project.get("nodes", [])
    log_entries = project.get("log", [])

    # --- Status distribution bar ---
    bar_segments = []
    all_statuses = ["done", "in_progress", "pending", "blocked", "expanded", "skipped"]
    for s in all_statuses:
        cnt = status_counts.get(s, 0)
        if cnt == 0:
            continue
        w = cnt / total * 100 if total else 0
        color = _STATUS_COLORS.get(s, "#475569")
        label = _STATUS_LABELS.get(s, s)
        bar_segments.append(
            f'<div class="dist-seg" style="width:{w}%;background:{color};" '
            f'title="{label}: {cnt}"></div>'
        )

    legend_items = []
    for s in all_statuses:
        cnt = status_counts.get(s, 0)
        if cnt == 0:
            continue
        color = _STATUS_COLORS.get(s, "#475569")
        label = _STATUS_LABELS.get(s, s)
        legend_items.append(
            f'<span class="legend-item">'
            f'<span class="legend-dot" style="background:{color};"></span>'
            f'{label}: {cnt}</span>'
        )

    # --- Nodes grouped by phase ---
    phase_map: dict[str, list[dict]] = {}
    for node in nodes:
        ph = node.get("phase", "")
        phase_map.setdefault(ph, []).append(node)

    phase_id_to_name = {p["id"]: p.get("name", p["id"]) for p in phases}
    critical_set = set(critical_path)

    phase_sections = []
    # Render phases in declared order, then any remaining
    rendered_phase_ids: set[str] = set()
    phase_order = [p["id"] for p in phases]
    for ph_id in list(phase_order) + sorted(phase_map.keys()):
        if ph_id in rendered_phase_ids:
            continue
        rendered_phase_ids.add(ph_id)
        ph_nodes = phase_map.get(ph_id, [])
        if not ph_nodes:
            continue
        ph_name = _e(phase_id_to_name.get(ph_id, ph_id or "Unphased"))

        node_rows = []
        for n in ph_nodes:
            nid = _e(n["id"])
            nname = _e(n.get("name", nid))
            nstatus = n.get("status", "pending")
            ntype = n.get("type", "task")
            is_crit = n["id"] in critical_set
            owner = _e(n.get("owner", ""))
            deps = n.get("depends", [])
            slack = n.get("slack", 0)
            deliverables = n.get("deliverables", [])
            gate = _e(n.get("gate", ""))

            badge_cls = f"badge-{nstatus}"
            status_label = _STATUS_LABELS.get(nstatus, nstatus)

            extra_badges = ""
            if is_crit:
                extra_badges += ' <span class="badge badge-critical">Critical Path</span>'
            if ntype == "milestone":
                extra_badges += ' <span class="badge badge-milestone">Milestone</span>'

            dep_html = ""
            if deps:
                dep_links = ", ".join(
                    f'<code>{_e(d)}</code>' for d in deps
                )
                dep_html = f'<div class="node-deps">Depends: {dep_links}</div>'

            deliv_html = ""
            if deliverables:
                items = ", ".join(_e(str(d)) for d in deliverables)
                deliv_html = f'<div class="node-deliverables">Deliverables: {items}</div>'

            gate_html = ""
            if gate:
                gate_html = f'<div class="node-gate">Gate: {gate}</div>'

            owner_html = f'<span class="node-owner">{owner}</span>' if owner else ""

            crit_cls = " node-critical" if is_crit else ""

            node_rows.append(f"""
            <div class="node-card{crit_cls}">
              <div class="node-header">
                <span class="node-name">{nname}</span>
                <span class="badge {badge_cls}">{status_label}</span>
                {extra_badges}
              </div>
              <div class="node-meta">
                <code class="node-id">{nid}</code>
                {owner_html}
                <span class="node-slack" title="Slack (days)">Slack: {slack:.1f}d</span>
              </div>
              {dep_html}
              {deliv_html}
              {gate_html}
            </div>""")

        phase_sections.append(f"""
        <div class="phase-section">
          <h3 class="phase-title">{ph_name}</h3>
          <div class="phase-nodes">{"".join(node_rows)}</div>
        </div>""")

    # --- Critical path display ---
    cp_html = ""
    if critical_path:
        cp_items = []
        for i, nid in enumerate(critical_path):
            cp_items.append(f'<span class="cp-node">{_e(nid)}</span>')
            if i < len(critical_path) - 1:
                cp_items.append('<span class="cp-arrow">&rarr;</span>')
        cp_html = f"""
        <div class="section">
          <h2 class="section-title">Critical Path</h2>
          <div class="cp-chain">{"".join(cp_items)}</div>
          <div class="cp-days">Total estimated: {total_days:.1f} days</div>
        </div>"""

    # --- Log ---
    log_html = ""
    if log_entries:
        log_rows = []
        for entry in log_entries:
            time_str = _e(str(entry.get("time", "")))
            action = _e(str(entry.get("action", "")))
            task = _e(str(entry.get("task", "")))
            detail = _e(str(entry.get("detail", "")))
            task_part = f' <code>{task}</code>' if task else ""
            log_rows.append(
                f'<div class="log-row">'
                f'<span class="log-time">{time_str}</span>'
                f'<span class="log-action">{action}</span>'
                f'{task_part}'
                f'<span class="log-detail">{detail}</span>'
                f'</div>'
            )
        log_html = f"""
        <div class="section">
          <h2 class="section-title">Recent Log</h2>
          <div class="log-list">{"".join(log_rows)}</div>
        </div>"""

    # --- Assemble ---
    body = f"""
<header>
  <h1><a href="/">Project Tracker</a></h1>
  <span class="breadcrumb">/ {pname}</span>
</header>
<div class="container">

  <!-- Overview -->
  <div class="overview-grid">
    <div class="overview-card">
      <div class="ov-label">Progress</div>
      <div class="ov-value">{done} / {total} <small>({pct}%)</small></div>
      <div class="progress-bar" style="margin-top:0.5rem;">
        <div class="progress-fill" style="width:{pct}%;background:{"var(--green)" if pct==100 else "var(--accent)"};"></div>
      </div>
    </div>
    <div class="overview-card">
      <div class="ov-label">Est. Duration</div>
      <div class="ov-value">{total_days:.1f} <small>days</small></div>
    </div>
    <div class="overview-card">
      <div class="ov-label">Critical Path</div>
      <div class="ov-value">{len(critical_path)} <small>node{"s" if len(critical_path)!=1 else ""}</small></div>
    </div>
  </div>

  <!-- Status distribution -->
  <div class="section">
    <h2 class="section-title">Status Distribution</h2>
    <div class="dist-bar">{"".join(bar_segments)}</div>
    <div class="legend">{"".join(legend_items)}</div>
  </div>

  {cp_html}

  <!-- Phases / Nodes -->
  <div class="section">
    <h2 class="section-title">Nodes by Phase</h2>
    {"".join(phase_sections)}
  </div>

  {log_html}

</div>

<style>
/* ---- overview ---- */
.overview-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
}}
.overview-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1rem 1.25rem;
}}
.ov-label {{ font-size: 0.8rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.05em; }}
.ov-value {{ font-size: 1.5rem; font-weight: 700; margin-top: 0.25rem; }}
.ov-value small {{ font-size: 0.875rem; font-weight: 400; color: var(--text-dim); }}

/* ---- progress bar (reused) ---- */
.progress-bar {{
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}}
.progress-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}

/* ---- section ---- */
.section {{
  margin: 1.5rem 0;
}}
.section-title {{
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid var(--border);
}}

/* ---- status distribution bar ---- */
.dist-bar {{
  display: flex;
  height: 20px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--border);
}}
.dist-seg {{ transition: width 0.3s; }}
.legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.5rem;
  font-size: 0.8rem;
}}
.legend-item {{ display: flex; align-items: center; gap: 0.3rem; }}
.legend-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}

/* ---- critical path ---- */
.cp-chain {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  font-family: monospace;
  font-size: 0.85rem;
}}
.cp-node {{
  background: var(--orange);
  color: #000;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
}}
.cp-arrow {{ color: var(--text-dim); font-size: 1rem; }}
.cp-days {{ font-size: 0.8rem; color: var(--text-dim); margin-top: 0.4rem; }}

/* ---- phases / nodes ---- */
.phase-section {{ margin-bottom: 1.25rem; }}
.phase-title {{
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 0.5rem;
}}
.phase-nodes {{ display: flex; flex-direction: column; gap: 0.5rem; }}
.node-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
}}
.node-card.node-critical {{ border-left: 3px solid var(--orange); }}
.node-header {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }}
.node-name {{ font-weight: 600; }}
.node-meta {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.25rem;
  font-size: 0.8rem;
  color: var(--text-dim);
}}
.node-id {{ font-size: 0.75rem; }}
.node-owner {{ }}
.node-slack {{ }}
.node-deps, .node-deliverables, .node-gate {{
  font-size: 0.8rem;
  color: var(--text-dim);
  margin-top: 0.25rem;
}}
.node-deps code {{ font-size: 0.75rem; background: var(--bg); padding: 0.1rem 0.3rem; border-radius: 3px; }}

/* ---- log ---- */
.log-list {{ display: flex; flex-direction: column; gap: 0.25rem; }}
.log-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: 0.8rem;
  padding: 0.35rem 0.5rem;
  background: var(--bg-card);
  border-radius: 4px;
  align-items: baseline;
}}
.log-time {{ color: var(--text-dim); font-family: monospace; font-size: 0.75rem; white-space: nowrap; }}
.log-action {{ font-weight: 600; color: var(--accent); }}
.log-row code {{ font-size: 0.75rem; background: var(--bg); padding: 0.1rem 0.3rem; border-radius: 3px; }}
.log-detail {{ color: var(--text-dim); }}
</style>
"""
    return _page(f"{pname} - Project Tracker", body)
