"""pt visual — 生成项目进度可视化 HTML + PNG"""
import sys
import json
import subprocess
import shutil
from pathlib import Path
from .. import core


def cmd_visual(args):
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    info = core.get_status(p)
    phases = core.get_phase_progress(p)
    cpm = info["cpm"]
    nodes_map = {n["id"]: n for n in p["nodes"]}
    cpm_nodes = cpm.get("nodes", {})
    critical_set = set(cpm.get("critical_path", []))

    # 找到当前节点（第一个 in_progress 或第一个 ready）
    classified = info["classified"]
    in_progress = [n for n in p["nodes"] if n.get("status") == "in_progress"]
    ready = classified.get("ready", [])
    current_id = None
    if in_progress:
        current_id = in_progress[0]["id"]
    elif ready:
        # 优先选关键路径上的 ready
        for r in ready:
            if r["id"] in critical_set:
                current_id = r["id"]
                break
        if not current_id:
            current_id = ready[0]["id"]

    # 决策摘要
    decisions = p.get("decisions", [])
    active_decisions = [d for d in decisions if d.get("status") == "active"]

    html = _generate_html(p, phases, cpm, nodes_map, cpm_nodes, critical_set,
                          current_id, info, ready, active_decisions)

    # 输出路径
    out_dir = Path(args.output) if hasattr(args, "output") and args.output else Path("/tmp")
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{p['id'].lower()}-progress.html"
    png_path = out_dir / f"{p['id'].lower()}-progress.png"

    try:
        html_path.write_text(html, encoding="utf-8")
    except OSError as e:
        print(f"❌ HTML 写入失败: {e}")
        sys.exit(1)
    print(f"📄 HTML: {html_path}")

    # 尝试用 playwright 截图 (2x 清晰度)
    if not getattr(args, "no_png", False):
        ok = _screenshot_2x(html_path, png_path)
        if ok:
            print(f"🖼️  PNG: {png_path}")
        else:
            print("⚠️  截图跳过（playwright 不可用）")


def _screenshot_2x(html_path: Path, png_path: Path) -> bool:
    """用 chrome headless 截图，2x deviceScaleFactor"""
    chrome = _find_chrome()
    pw_core = _find_playwright_core()
    if not chrome or not pw_core:
        # fallback: npx playwright screenshot (1x but larger viewport)
        try:
            result = subprocess.run(
                ["npx", "playwright", "screenshot", "--full-page",
                 "--viewport-size=1800,1600",
                 f"file://{html_path.resolve()}", str(png_path)],
                capture_output=True, text=True, timeout=30
            )
            return png_path.exists() and png_path.stat().st_size > 0
        except Exception:
            return False

    try:
        js = f"""
const {{ chromium }} = require('{pw_core}');
(async () => {{
  const b = await chromium.launch({{ executablePath: '{chrome}' }});
  const ctx = await b.newContext({{ deviceScaleFactor: 2, viewport: {{ width: 900, height: 800 }} }});
  const page = await ctx.newPage();
  await page.goto('file://{html_path.resolve()}');
  await page.waitForTimeout(300);
  await page.screenshot({{ path: '{png_path}', fullPage: true }});
  await b.close();
}})();
"""
        result = subprocess.run(
            ["node", "-e", js],
            capture_output=True, text=True, timeout=30
        )
        return png_path.exists() and png_path.stat().st_size > 0
    except Exception:
        return False


def _find_playwright_core() -> str | None:
    """找到 playwright-core 模块路径"""
    import glob
    patterns = [
        str(Path.home() / ".npm-global/lib/node_modules/openclaw/node_modules/playwright-core"),
        str(Path.home() / ".npm-global/lib/node_modules/playwright-core"),
    ]
    for p in patterns:
        if Path(p).exists():
            return p
    # 动态搜索
    for g in glob.glob(str(Path.home() / ".npm-global/**/playwright-core/index.js"), recursive=True):
        return str(Path(g).parent)
    return None


def _find_chrome() -> str | None:
    """找到 playwright 安装的 chrome"""
    candidates = [
        Path.home() / ".cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
    ]
    # 动态搜索
    pw_dir = Path.home() / ".cache/ms-playwright"
    if pw_dir.exists():
        for d in sorted(pw_dir.iterdir(), reverse=True):
            if d.name.startswith("chromium-"):
                c = d / "chrome-linux64" / "chrome"
                if c.exists():
                    return str(c)
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _node_class(node, current_id, critical_set, ready_ids):
    """确定节点的 CSS class"""
    nid = node["id"]
    status = node.get("status", "pending")
    is_milestone = node.get("type") == "milestone"

    if is_milestone:
        return "milestone"
    if nid == current_id:
        return "current you-are-here"
    if status == "done":
        return "done"
    if status == "in_progress":
        return "current"
    if status == "blocked":
        return "blocked"
    if nid in ready_ids:
        return "ready"
    return "waiting"


def _generate_html(p, phases, cpm, nodes_map, cpm_nodes, critical_set,
                   current_id, info, ready, active_decisions):
    """生成完整 HTML"""
    ready_ids = {r["id"] for r in ready}
    done_count = info["done_count"]
    total = info["total"]
    total_days = cpm.get("total_days", 0)
    pct = int(done_count / total * 100) if total > 0 else 0

    # 决策摘要 HTML
    dec_html = ""
    if active_decisions:
        items = "".join(
            f'<div class="dec-item">D{d["id"]}: {d["title"]}</div>'
            for d in active_decisions[:6]
        )
        dec_html = f'<div class="decisions"><div class="dec-title">📌 生效决策</div>{items}</div>'

    # 阶段 HTML
    phases_html = ""
    for phase in phases:
        pid = phase["id"]
        phase_nodes = [n for n in p["nodes"] if n.get("phase") == pid]
        if not phase_nodes:
            continue

        fill_pct = int(phase["done"] / phase["total"] * 100) if phase["total"] > 0 else 0
        fill_color = "#238636" if phase["complete"] else ("#f0883e" if fill_pct > 0 else "#30363d")
        check = " ✅" if phase["complete"] else ""

        # 节点卡片
        cards = ""
        for i, node in enumerate(phase_nodes):
            nid = node["id"]
            cls = _node_class(node, current_id, critical_set, ready_ids)
            crit_cls = " critical" if nid in critical_set else ""
            badge = '<div class="you-badge">👈 你在这里</div>' if nid == current_id else ""

            name = node.get("name", nid)
            owner = node.get("owner", "")
            days_info = ""
            if nid in cpm_nodes:
                cn = cpm_nodes[nid]
                slack = cn.get("slack", 0)
                days = cn.get("days", 0)
                if days > 0:
                    days_info = f"{days:.0f}天"
                    if slack == 0 and nid in critical_set:
                        days_info += " | slack=0"
                    elif slack > 0:
                        days_info += f" | slack={slack:.0f}天"

            # 图标
            icon = "🏁" if node.get("type") == "milestone" else {
                "done": "✅", "in_progress": "⚡", "blocked": "🚫"
            }.get(node.get("status", ""), "")

            arrow = '<div class="arrow">→</div>' if i < len(phase_nodes) - 1 else ""

            cards += f'''<div class="node {cls}{crit_cls}">{badge}
<div class="name">{icon} {name}</div>
{"<div class='meta'>" + owner + "</div>" if owner else ""}
{"<div class='days'>" + days_info + "</div>" if days_info else ""}
</div>{arrow}'''

        phases_html += f'''<div class="phase">
<div class="phase-header">
<span class="phase-name">{phase["name"]}</span>
<div class="phase-bar"><div class="phase-fill" style="width:{fill_pct}%; background:{fill_color}"></div></div>
<span class="phase-pct" {"style='color:#3fb950'" if phase["complete"] else ""}>{phase["progress"]}{check}</span>
</div>
<div class="pipeline">{cards}</div>
</div>'''

    # 行动建议
    action_items = ""
    if current_id and current_id in nodes_map:
        cn = nodes_map[current_id]
        action_items += f'<div class="step"><span class="step-num">①</span> {cn["name"]}（关键路径，立即执行）</div>'

    parallel = [r for r in ready if r["id"] != current_id]
    for i, r in enumerate(parallel[:2]):
        slack = cpm_nodes.get(r["id"], {}).get("slack", 0)
        action_items += f'<div class="step"><span class="step-num">{chr(0x2461+i)}</span> {r["name"]}（可并行，slack={slack:.0f}天）</div>'

    return f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{p["name"]} — 项目进度图</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0d1117; color: #e6edf3; font-family: -apple-system, 'PingFang SC', 'Noto Sans SC', sans-serif; padding: 24px; max-width: 900px; }}
h1 {{ font-size: 22px; margin-bottom: 4px; }}
.subtitle {{ color: #8b949e; font-size: 13px; margin-bottom: 16px; }}
.legend {{ display: flex; gap: 14px; margin-bottom: 20px; flex-wrap: wrap; }}
.legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 12px; color: #8b949e; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 3px; }}

.decisions {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 12px 16px; margin-bottom: 20px; }}
.dec-title {{ font-size: 13px; font-weight: 600; margin-bottom: 6px; }}
.dec-item {{ font-size: 12px; color: #8b949e; padding: 2px 0; }}

.phase {{ margin-bottom: 20px; }}
.phase-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
.phase-name {{ font-size: 15px; font-weight: 600; min-width: 70px; }}
.phase-bar {{ flex: 1; height: 6px; background: #21262d; border-radius: 3px; overflow: hidden; }}
.phase-fill {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
.phase-pct {{ font-size: 12px; color: #8b949e; min-width: 50px; text-align: right; }}

.pipeline {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.node {{ position: relative; padding: 8px 12px; border-radius: 8px; font-size: 12px; min-width: 80px; border: 2px solid; }}
.node .name {{ font-weight: 600; margin-bottom: 1px; white-space: nowrap; }}
.node .meta {{ font-size: 10px; opacity: 0.7; }}
.node .days {{ font-size: 10px; opacity: 0.5; }}

.node.you-are-here {{ animation: pulse 2s infinite; }}
@keyframes pulse {{
  0%, 100% {{ box-shadow: 0 0 0 0 rgba(255,165,0,0.4); }}
  50% {{ box-shadow: 0 0 0 8px rgba(255,165,0,0); }}
}}

.node.done {{ background: #0d2818; border-color: #238636; color: #3fb950; }}
.node.current {{ background: #2a1800; border-color: #f0883e; color: #f0883e; }}
.node.ready {{ background: #0c1929; border-color: #388bfd; color: #58a6ff; }}
.node.waiting {{ background: #161b22; border-color: #30363d; color: #484f58; }}
.node.blocked {{ background: #2a0a0a; border-color: #f85149; color: #f85149; }}
.node.milestone {{ background: #1a1028; border-color: #8957e5; color: #bc8cff; border-style: dashed; }}

.arrow {{ color: #30363d; font-size: 16px; display: flex; align-items: center; }}
.you-badge {{ position: absolute; top: -10px; right: -10px; background: #f0883e; color: #0d1117; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 10px; white-space: nowrap; }}
.critical {{ border-left: 3px solid #f85149 !important; }}

.summary {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 16px; margin-top: 16px; }}
.summary h2 {{ font-size: 15px; margin-bottom: 10px; }}
.summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.summary-label {{ font-size: 11px; color: #8b949e; }}
.summary-value {{ font-size: 16px; font-weight: 600; }}

.action-box {{ background: #1c1206; border: 1px solid #f0883e; border-radius: 12px; padding: 16px; margin-top: 12px; }}
.action-box h2 {{ font-size: 15px; color: #f0883e; margin-bottom: 8px; }}
.action-box .step {{ font-size: 13px; margin: 4px 0; line-height: 1.5; }}
.action-box .step-num {{ color: #f0883e; font-weight: 700; }}
</style>
</head>
<body>
<h1>{p["name"]} — 项目进度图</h1>
<div class="subtitle">{p["id"]} | 进度 {done_count}/{total} ({pct}%) | 总工期 {total_days:.0f} 天</div>

<div class="legend">
<div class="legend-item"><div class="legend-dot" style="background:#238636"></div>已完成</div>
<div class="legend-item"><div class="legend-dot" style="background:#f0883e"></div>👈 当前</div>
<div class="legend-item"><div class="legend-dot" style="background:#388bfd"></div>可并行</div>
<div class="legend-item"><div class="legend-dot" style="background:#30363d"></div>等待中</div>
<div class="legend-item"><div class="legend-dot" style="background:#8957e5"></div>里程碑</div>
<div class="legend-item" style="color:#f85149">┃ 关键路径</div>
</div>

{dec_html}
{phases_html}

<div class="summary">
<h2>📊 项目概览</h2>
<div class="summary-grid">
<div><div class="summary-label">总进度</div><div class="summary-value" style="color:#f0883e">{done_count}/{total} ({pct}%)</div></div>
<div><div class="summary-label">总工期</div><div class="summary-value">{total_days:.0f} 天</div></div>
<div><div class="summary-label">关键路径</div><div class="summary-value" style="color:#f85149">{len(critical_set)} 个节点</div></div>
<div><div class="summary-label">可并行启动</div><div class="summary-value" style="color:#58a6ff">{len(parallel)} 个</div></div>
</div>
</div>

<div class="action-box">
<h2>🎯 下一步行动</h2>
{action_items}
</div>

</body>
</html>'''
