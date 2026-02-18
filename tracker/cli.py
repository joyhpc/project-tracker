"""CLI 命令定义"""
import sys
import argparse
from . import core, flow as flowmod
from .engine import analyze, format_advice, plan_project, generate_digest


def _icon(status: str) -> str:
    return {"done": "✅", "in_progress": "🔄", "blocked": "🚫", "pending": "⏳"}.get(status, "❓")


def cmd_init(args):
    try:
        p = core.init_project(args.id, args.name, args.phase, args.flow)
        print(f"✅ 项目已创建: {p['id']} ({p['name']})")
        print(f"   起始阶段: {p['current_phase']}")
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_list(args):
    projects = core.list_projects()
    if not projects:
        print("没有项目。使用 pt init <id> --name <name> 创建。")
        return
    for p in projects:
        marker = " ◀" if p.get("_active") else ""
        print(f"  {'●' if p.get('_active') else '○'} {p['id']} | {p['name']} | {p['current_phase']}{marker}")


def cmd_switch(args):
    try:
        core.switch_project(args.id)
        print(f"✅ 已切换到: {args.id}")
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_status(args):
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    info = core.get_status(p)
    phase = info["phase"]
    cat = info["categorized"]

    print(f"\n📋 {p['name']} ({p['id']})")
    print(f"📍 阶段: {phase.get('name', '')} ({p['current_phase']})")
    if phase.get("milestone"):
        print(f"🎯 里程碑: {phase['milestone']}")
    print(f"📊 进度: {info['done_count']}/{info['total']}")

    if info["blockers"]:
        print(f"\n🚫 阻塞 ({len(info['blockers'])}):")
        for b in info["blockers"]:
            print(f"   {b['task_id']}: {b['reason']}")

    if cat["in_progress"]:
        print(f"\n🔄 进行中 ({len(cat['in_progress'])}):")
        for t in cat["in_progress"]:
            print(f"   [{t['id']}] {t['name']}")

    if cat["done"]:
        print(f"\n✅ 已完成 ({len(cat['done'])}):")
        for t in cat["done"]:
            print(f"   [{t['id']}] {t['name']}")

    if cat["pending"]:
        print(f"\n⏳ 待开始 ({len(cat['pending'])}):")
        for t in cat["pending"]:
            line = f"   [{t['id']}] {t['name']}"
            if t.get("owner"):
                line += f"  ← {t['owner']}"
            print(line)

    print()


def cmd_tasks(args):
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    fl = flowmod.load_flow(p.get("flow", "duxin"))
    phases = flowmod.get_phases(fl)
    phase = phases.get(p["current_phase"], {})
    tasks = phase.get("tasks", [])
    task_status = p.get("tasks", {})

    print(f"\n📋 {phase.get('name', '')} - 任务列表\n")
    for t in tasks:
        s = task_status.get(t["id"], {}).get("status", "pending")
        icon = _icon(s)
        line = f"  {icon} [{t['id']}] {t['name']}"
        if t.get("owner"):
            line += f"  ← {t['owner']}"
        print(line)
        if t.get("deliverables"):
            print(f"      交付件: {', '.join(t['deliverables'])}")
        if t.get("gate"):
            print(f"      准入: {t['gate']}")
        if s == "blocked":
            reason = task_status.get(t["id"], {}).get("blocked_reason", "")
            if reason:
                print(f"      阻塞: {reason}")
    print()


def cmd_next(args):
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    fl = flowmod.load_flow(p.get("flow", "duxin"))
    phases = flowmod.get_phases(fl)
    phase = phases.get(p["current_phase"], {})
    task_status = p.get("tasks", {})
    blockers = p.get("blockers", [])

    result = analyze(phase, task_status, blockers)
    print(f"\n📋 {p['name']} ({p['id']})")
    print(f"📍 {phase.get('name', '')} ({p['current_phase']})\n")
    print(format_advice(result))


def cmd_plan(args):
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    fl = flowmod.load_flow(p.get("flow", "duxin"))
    task_status = p.get("tasks", {})
    blockers = p.get("blockers", [])

    print(f"\n{'='*60}")
    print(f"  📋 {p['name']} ({p['id']}) - 作战地图")
    print(f"{'='*60}\n")
    print(plan_project(fl, p["current_phase"], task_status, blockers))


def cmd_digest(args):
    """生成通知摘要（供 cron 调用或手动查看）"""
    import json
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
        # JSON 模式：供程序调用
        output = {
            "has_alerts": any_alerts,
            "projects": [
                {"id": p["id"], "name": p["name"], **d["summary"], "alerts": d["alerts"]}
                for p, d in zip(projects, all_digests)
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # 人类可读模式
        for d in all_digests:
            print(d["text"])
            print("─" * 40)

    # 退出码：有告警返回 1，无告警返回 0
    if any_alerts and not args.quiet:
        sys.exit(0)  # 正常退出但有告警
    sys.exit(0)


def cmd_start(args):
    try:
        p = core.require_active()
        task = core.start_task(p["id"], args.task_id)
        print(f"🔄 已开始: [{args.task_id}] {task['name']}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_done(args):
    try:
        p = core.require_active()
        result = core.done_task(p["id"], args.task_id, args.note or "")
        print(f"✅ 已完成: {args.task_id}")
        print(f"   进度: {result['progress']}")
        if result["complete"]:
            print(f"🎉 阶段完成！运行 pt advance 进入下一阶段。")
        elif result["remaining"]:
            print(f"   剩余: {', '.join(result['remaining'][:3])}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_block(args):
    try:
        p = core.require_active()
        core.block_task(p["id"], args.task_id, args.reason)
        print(f"🚫 已阻塞: {args.task_id} - {args.reason}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_unblock(args):
    try:
        p = core.require_active()
        core.unblock_task(p["id"], args.task_id)
        print(f"✅ 已解除阻塞: {args.task_id}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_advance(args):
    try:
        p = core.require_active()
        result = core.advance(p["id"], force=args.force)
        print(f"⏩ 阶段推进: {result['from']} → {result['to']}")
        if result["milestone"]:
            print(f"🎯 里程碑达成: {result['milestone']}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_note(args):
    try:
        p = core.require_active()
        core.add_note(p["id"], args.text)
        print(f"📝 已记录")
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_log(args):
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    logs = p.get("log", [])
    n = args.n or 20
    for entry in logs[-n:]:
        action = entry.get("action", "")
        icon = {"init": "🆕", "start": "🔄", "done": "✅", "block": "🚫", "unblock": "🔓", "advance": "⏩", "note": "📝",
                "subtask_add": "➕", "subtask_done": "✅", "subtask_block": "🚫"}.get(action, "•")
        task = f" [{entry['task']}]" if entry.get("task") else ""
        detail = f" {entry.get('detail', '')}" if entry.get("detail") else ""
        print(f"  {entry['time']}  {icon}{task}{detail}")


def cmd_sub_add(args):
    try:
        p = core.require_active()
        kwargs = {}
        if args.owner:
            kwargs["owner"] = args.owner
        if args.depends:
            kwargs["depends"] = args.depends.split(",")
        sub = core.add_subtask(p["id"], args.parent, args.sub_id, args.name, **kwargs)
        print(f"➕ 子任务已添加: {args.parent}.{args.sub_id} - {args.name}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_sub_done(args):
    try:
        p = core.require_active()
        result = core.done_subtask(p["id"], args.full_id, args.note or "")
        print(f"✅ 子任务完成: {args.full_id}")
        if result.get("all_subtasks_done"):
            print(f"🎉 {result['hint']}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_sub_block(args):
    try:
        p = core.require_active()
        core.block_subtask(p["id"], args.full_id, args.reason)
        print(f"🚫 子任务阻塞: {args.full_id} - {args.reason}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_sub_list(args):
    try:
        p = core.require_active()
        subs = core.list_subtasks(p["id"], args.parent)
        if not subs:
            print(f"  {args.parent} 没有子任务")
            return
        print(f"\n📋 {args.parent} 子任务:\n")
        for s in subs:
            icon = _icon(s["status"])
            line = f"  {icon} [{s['id']}] {s['name']}"
            if s.get("owner"):
                line += f"  ← {s['owner']}"
            print(line)
            if s.get("blocked_reason"):
                print(f"      阻塞: {s['blocked_reason']}")
            if s.get("note") and s["status"] == "done":
                print(f"      备注: {s['note']}")
        print()
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_phases(args):
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    fl = flowmod.load_flow(p.get("flow", "duxin"))
    order = flowmod.get_phase_order(fl)
    phases = flowmod.get_phases(fl)
    current = p["current_phase"]

    print(f"\n📋 {p['name']} - 流程阶段\n")
    for pid in order:
        ph = phases[pid]
        if pid == current:
            marker = " ◀ 当前"
        elif order.index(pid) < order.index(current):
            marker = " ✅"
        else:
            marker = ""
        ms = f" [{ph['milestone']}]" if ph.get("milestone") else ""
        print(f"  {'●' if pid == current else '○'} {pid} - {ph['name']}{ms}{marker}")
    print()


def main():
    parser = argparse.ArgumentParser(prog="pt", description="项目推进助手")
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="创建项目")
    p_init.add_argument("id", help="项目ID (如 A57-CAMRX)")
    p_init.add_argument("--name", "-n", required=True, help="项目名称")
    p_init.add_argument("--phase", "-p", default="REQ", help="起始阶段 (默认 REQ)")
    p_init.add_argument("--flow", "-f", default="duxin", help="流程定义 (默认 duxin)")

    # list
    sub.add_parser("list", aliases=["ls"], help="列出所有项目")

    # switch
    p_switch = sub.add_parser("switch", aliases=["sw"], help="切换活跃项目")
    p_switch.add_argument("id", help="项目ID")

    # status
    sub.add_parser("status", aliases=["s"], help="查看项目状态")

    # tasks
    sub.add_parser("tasks", aliases=["t"], help="查看当前阶段任务")

    # next
    sub.add_parser("next", aliases=["n"], help="查看下一步行动")

    # plan
    sub.add_parser("plan", help="项目作战地图（全局视角）")

    # digest
    p_digest = sub.add_parser("digest", help="项目状态摘要（通知用）")
    p_digest.add_argument("--json", action="store_true", help="JSON 输出")
    p_digest.add_argument("--quiet", "-q", action="store_true", help="静默模式")

    # phases
    sub.add_parser("phases", aliases=["ph"], help="查看流程阶段")

    # start
    p_start = sub.add_parser("start", help="开始任务")
    p_start.add_argument("task_id", help="任务ID")

    # done
    p_done = sub.add_parser("done", aliases=["d"], help="完成任务")
    p_done.add_argument("task_id", help="任务ID")
    p_done.add_argument("--note", help="备注")

    # block
    p_block = sub.add_parser("block", help="标记任务阻塞")
    p_block.add_argument("task_id", help="任务ID")
    p_block.add_argument("--reason", "-r", required=True, help="阻塞原因")

    # unblock
    p_unblock = sub.add_parser("unblock", help="解除任务阻塞")
    p_unblock.add_argument("task_id", help="任务ID")

    # advance
    p_advance = sub.add_parser("advance", help="推进到下一阶段")
    p_advance.add_argument("--force", action="store_true", help="强制推进（跳过未完成检查）")

    # note
    p_note = sub.add_parser("note", help="添加备注")
    p_note.add_argument("text", help="备注内容")

    # log
    p_log = sub.add_parser("log", help="查看项目日志")
    p_log.add_argument("-n", type=int, default=20, help="显示条数")

    # sub add
    p_sub_add = sub.add_parser("sub", help="添加子任务")
    p_sub_add.add_argument("parent", help="父任务ID")
    p_sub_add.add_argument("sub_id", help="子任务ID")
    p_sub_add.add_argument("--name", "-n", required=True, help="子任务名称")
    p_sub_add.add_argument("--owner", "-o", help="责任人")
    p_sub_add.add_argument("--depends", help="依赖的子任务ID，逗号分隔")

    # sub done
    p_sub_done = sub.add_parser("sub-done", aliases=["sd"], help="完成子任务")
    p_sub_done.add_argument("full_id", help="子任务ID (parent.sub)")
    p_sub_done.add_argument("--note", help="备注")

    # sub block
    p_sub_block = sub.add_parser("sub-block", aliases=["sb"], help="阻塞子任务")
    p_sub_block.add_argument("full_id", help="子任务ID (parent.sub)")
    p_sub_block.add_argument("--reason", "-r", required=True, help="阻塞原因")

    # sub list
    p_sub_list = sub.add_parser("sub-list", aliases=["sl"], help="查看子任务")
    p_sub_list.add_argument("parent", help="父任务ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cmd_map = {
        "init": cmd_init, "list": cmd_list, "ls": cmd_list,
        "switch": cmd_switch, "sw": cmd_switch,
        "status": cmd_status, "s": cmd_status,
        "tasks": cmd_tasks, "t": cmd_tasks,
        "next": cmd_next, "n": cmd_next,
        "plan": cmd_plan, "digest": cmd_digest,
        "phases": cmd_phases, "ph": cmd_phases,
        "start": cmd_start, "done": cmd_done, "d": cmd_done,
        "block": cmd_block, "unblock": cmd_unblock,
        "advance": cmd_advance, "note": cmd_note, "log": cmd_log,
        "sub": cmd_sub_add, "sub-done": cmd_sub_done, "sd": cmd_sub_done,
        "sub-block": cmd_sub_block, "sb": cmd_sub_block,
        "sub-list": cmd_sub_list, "sl": cmd_sub_list,
    }

    fn = cmd_map.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()
