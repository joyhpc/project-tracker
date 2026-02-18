"""分析命令: plan, digest, timeline, estimate"""
import sys
import json
from .. import core, flow as flowmod
from ..engine import generate_digest
from ..formatter import format_plan
from ..timeline import compute_full_schedule, format_timeline, format_phase_gantt, estimate_task_days


def _require():
    try:
        return core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_plan(args):
    p = _require()
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    task_status = p.get("tasks", {})
    blockers = p.get("blockers", [])

    print(f"\n{'='*60}")
    print(f"  📋 {p['name']} ({p['id']}) - 作战地图")
    print(f"{'='*60}\n")
    print(format_plan(fl, p["current_phase"], task_status, blockers))


def cmd_digest(args):
    projects = core.list_projects()
    if not projects:
        if args.json:
            print(json.dumps({"projects": [], "has_alerts": False}))
        else:
            print("没有项目")
        return

    all_digests = []
    any_alerts = False
    for p in projects:
        fl = flowmod.load_flow(p.get("flow", "duxin"))
        d = generate_digest(p, fl)
        all_digests.append(d)
        if d["has_alerts"]:
            any_alerts = True

    if args.json:
        output = {
            "has_alerts": any_alerts,
            "projects": [
                {"id": p["id"], "name": p["name"], **d["summary"], "alerts": d["alerts"]}
                for p, d in zip(projects, all_digests)
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for d in all_digests:
            print(d["text"])
            print("─" * 40)


def cmd_timeline(args):
    p = _require()
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    task_status = p.get("tasks", {})
    custom_estimates = p.get("estimates", {})

    from datetime import datetime
    start_date = None
    if args.start:
        try:
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
        except ValueError:
            print("❌ 日期格式错误，应为 YYYY-MM-DD")
            sys.exit(1)

    if args.phase:
        phases = flowmod.get_phases(fl)
        phase = phases.get(args.phase.upper())
        if not phase:
            print(f"❌ 未找到阶段: {args.phase}")
            sys.exit(1)
        print(f"\n📋 {p['name']} ({p['id']})")
        print(format_phase_gantt(phase, task_status, custom_estimates))
    else:
        result = compute_full_schedule(fl, p["current_phase"], task_status, start_date, custom_estimates)
        print(f"\n📋 {p['name']} ({p['id']})")
        print(format_timeline(result))


def cmd_estimate(args):
    p = _require()
    fl = flowmod.load_flow(p.get("flow", "duxin"))

    if args.task_id and args.days is not None:
        _, task = flowmod.find_task(fl, args.task_id)
        if not task:
            print(f"❌ 任务不存在: {args.task_id}")
            sys.exit(1)
        if "estimates" not in p:
            p["estimates"] = {}
        p["estimates"][args.task_id] = args.days
        core._save(p)
        print(f"⏱️  [{args.task_id}] {task['name']} → {args.days} 天")
    elif args.show:
        custom = p.get("estimates", {})
        print("\n⏱️  工时估算:\n")
        for phase in fl.get("phases", []):
            has_tasks = False
            for task in phase.get("tasks", []):
                tid = task["id"]
                if tid in custom or args.all:
                    if not has_tasks:
                        print(f"  📍 {phase['name']}:")
                        has_tasks = True
                    est = custom.get(tid, estimate_task_days(task))
                    marker = " (自定义)" if tid in custom else " (默认)"
                    print(f"     [{tid}] {task['name']}: {est} 天{marker}")
        print()
    else:
        print("用法: pt estimate <task_id> <days>  或  pt estimate --show")
