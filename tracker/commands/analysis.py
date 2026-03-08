"""分析命令: plan, digest, timeline, estimate"""
import sys
import json
from .. import core
from ..engine import compute_cpm, build_graph, classify_tasks
from ..project_map import build_project_map, render_project_map_text


def _require():
    try:
        return core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def _icon(status: str) -> str:
    return {"done": "✅", "in_progress": "🔄", "blocked": "🚫", "pending": "⏳", "expanded": "📦"}.get(status, "❓")


def cmd_plan(args):
    """项目作战地图 — 终端友好的项目状态地图"""
    project = _require()
    map_data = build_project_map(project)
    print(render_project_map_text(map_data), end="")


def cmd_digest(args):
    """项目状态摘要"""
    projects = core.list_projects()
    if not projects:
        if getattr(args, "json", False):
            print(json.dumps({"projects": [], "has_alerts": False}))
        else:
            print("没有项目")
        return

    all_data = []
    for p in projects:
        flow = core._project_as_flow(p)
        task_status = core._get_task_status(p)
        cpm = compute_cpm(flow, task_status)
        classified = classify_tasks(flow, task_status)

        done, total = core._progress_counts(p)
        blocked = len(classified["blocked"])
        active_blockers = [b for b in p.get("blockers", []) if not b.get("resolved")]

        alerts = []
        if blocked > 0:
            alerts.append(f"🚫 {blocked} 个任务阻塞")
        if cpm["total_days"] > 60:
            alerts.append(f"⚠️ 总工期 {cpm['total_days']:.0f} 天")

        summary = {
            "total": total, "done": done, "blocked": blocked,
            "total_days": cpm["total_days"],
            "critical_path_len": len(cpm["critical_path"]),
        }

        all_data.append({
            "project": p, "summary": summary, "alerts": alerts,
            "cpm": cpm, "classified": classified,
        })

    if getattr(args, "json", False):
        output = {
            "has_alerts": any(d["alerts"] for d in all_data),
            "projects": [
                {"id": d["project"]["id"], "name": d["project"]["name"],
                 **d["summary"], "alerts": d["alerts"]}
                for d in all_data
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for d in all_data:
            if getattr(args, "quiet", False) and not d["alerts"]:
                continue
            p = d["project"]
            s = d["summary"]
            print(f"\n📋 {p['name']} ({p['id']})")
            print(f"   进度: {s['done']}/{s['total']} | 工期: {s['total_days']:.0f}天 | 关键路径: {s['critical_path_len']}节点")
            if d["alerts"]:
                for a in d["alerts"]:
                    print(f"   {a}")
            print(f"{'─'*40}")


def cmd_timeline(args):
    """项目时间线 — 基于 CPM"""
    p = _require()
    flow = core._project_as_flow(p)
    task_status = core._get_task_status(p)
    custom_estimates = p.get("estimates", {})
    cpm = compute_cpm(flow, task_status, custom_estimates)

    from datetime import datetime, timedelta
    start_date = datetime.now()
    if args.start:
        try:
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
        except ValueError:
            print("❌ 日期格式错误，应为 YYYY-MM-DD")
            sys.exit(1)

    print(f"\n📋 {p['name']} ({p['id']}) - 时间线")
    print(f"⏱️  总工期: {cpm['total_days']:.0f} 天")
    print(f"📅 起始: {start_date.strftime('%Y-%m-%d')}")
    end_date = start_date + timedelta(days=cpm["total_days"])
    print(f"📅 预计完成: {end_date.strftime('%Y-%m-%d')}")
    print()

    # 按阶段分组的甘特图
    phases = flow.get("phases", [])
    nodes_by_phase = {}
    for n in flow["nodes"]:
        ph = n.get("phase", "未分类")
        nodes_by_phase.setdefault(ph, []).append(n)

    max_width = 40
    scale = max_width / cpm["total_days"] if cpm["total_days"] > 0 else 1

    phase_filter = getattr(args, "phase", None)

    for phase in phases:
        pid = phase["id"]
        if phase_filter and pid.upper() != phase_filter.upper():
            continue
        phase_nodes = [n for n in nodes_by_phase.get(pid, []) if not n.get("parent") and n.get("status") != "expanded"]
        phase_nodes.sort(key=lambda node: (cpm["nodes"].get(node["id"], {}).get("es", 0), node["id"]))
        if not phase_nodes:
            continue

        print(f"📍 {phase.get('name', pid)}")
        for n in phase_nodes:
            r = cpm["nodes"].get(n["id"], {})
            es = r.get("es", 0)
            ef = r.get("ef", 0)
            days = r.get("days", 0)
            slack = r.get("slack", 0)

            # 甘特条
            bar_start = int(es * scale)
            bar_len = max(1, int(days * scale))
            bar = " " * bar_start + "█" * bar_len

            status = n.get("status", "pending")
            icon = _icon(status)
            crit = "🔴" if r.get("critical") else "  "

            name = n["name"][:14].ljust(14)
            es_date = (start_date + timedelta(days=es)).strftime("%m/%d")
            ef_date = (start_date + timedelta(days=ef)).strftime("%m/%d")

            print(f"  {icon}{crit} {name} |{bar}| {es_date}-{ef_date} ({days:.0f}d, s={slack:.0f})")
        print()


def cmd_estimate(args):
    """设置/查看工时估算"""
    p = _require()

    if args.task_id and args.days is not None:
        node = core._find_node(p, args.task_id)
        if not node:
            print(f"❌ 任务不存在: {args.task_id}")
            sys.exit(1)
        # 直接修改节点的 days 属性
        node["days"] = args.days
        core._save(p)
        print(f"⏱️  [{args.task_id}] {node['name']} → {args.days} 天")
    elif args.show:
        print("\n⏱️  工时估算:\n")
        phases = p.get("phases", [])
        nodes_by_phase = {}
        for n in p["nodes"]:
            ph = n.get("phase", "未分类")
            nodes_by_phase.setdefault(ph, []).append(n)

        for phase in phases:
            pid = phase["id"]
            phase_nodes = [n for n in nodes_by_phase.get(pid, []) if not n.get("parent") and n.get("status") != "expanded"]
            if not phase_nodes:
                continue
            print(f"  📍 {phase.get('name', pid)}:")
            for n in phase_nodes:
                days = n.get("days", 3)
                has_custom = "days" in n and n["type"] != "milestone"
                marker = "" if has_custom else " (默认)"
                if has_custom or getattr(args, "all", False):
                    print(f"     [{n['id']}] {n['name']}: {days} 天{marker}")
        print()
    else:
        print("用法: pt estimate <task_id> <days>  或  pt estimate --show")
