"""CLI 命令定义"""
import sys
import argparse
from . import core, flow as flowmod


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

    info = core.get_status(p)
    cat = info["categorized"]

    # 优先显示进行中
    if cat["in_progress"]:
        print("\n📌 继续推进:")
        for t in cat["in_progress"]:
            print(f"   [{t['id']}] {t['name']}")
            if t.get("deliverables"):
                print(f"   交付件: {', '.join(t['deliverables'])}")
        return

    # 然后显示可开始的
    if cat["pending"]:
        t = cat["pending"][0]
        print(f"\n📌 建议下一步:")
        print(f"   任务: {t['name']}")
        print(f"   ID:   {t['id']}")
        if t.get("owner"):
            print(f"   责任人: {t['owner']}")
        if t.get("deliverables"):
            print(f"   交付件: {', '.join(t['deliverables'])}")
        if t.get("gate"):
            print(f"   准入: {t['gate']}")
        print(f"\n   开始: pt start {t['id']}")
        return

    print("✅ 当前阶段所有任务已完成！运行 pt advance 进入下一阶段。")


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
        icon = {"init": "🆕", "start": "🔄", "done": "✅", "block": "🚫", "unblock": "🔓", "advance": "⏩", "note": "📝"}.get(action, "•")
        task = f" [{entry['task']}]" if entry.get("task") else ""
        detail = f" {entry.get('detail', '')}" if entry.get("detail") else ""
        print(f"  {entry['time']}  {icon}{task}{detail}")


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
        "phases": cmd_phases, "ph": cmd_phases,
        "start": cmd_start, "done": cmd_done, "d": cmd_done,
        "block": cmd_block, "unblock": cmd_unblock,
        "advance": cmd_advance, "note": cmd_note, "log": cmd_log,
    }

    fn = cmd_map.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()
