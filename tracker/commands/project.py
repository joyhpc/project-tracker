"""项目管理命令: init, list, switch, status, phases, advance, note, log"""
import sys
from .. import core, flow as flowmod


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
    p = _require()
    info = core.get_status(p)
    phase = info["phase"]
    cat = info["categorized"]

    print(f"\n📋 {p['name']} ({p['id']})")
    print(f"📍 阶段: {phase.get('name', '')} ({p['current_phase']})")
    if phase.get("milestone"):
        print(f"🎯 里程碑: {phase['milestone']}")
    print(f"📊 进度: {info['done_count']}/{info['total']}")

    for label, key, icon in [("🚫 阻塞", "blockers", None), ("🔄 进行中", "in_progress", None),
                              ("✅ 已完成", "done", None), ("⏳ 待开始", "pending", None)]:
        if key == "blockers":
            items = info[key]
            if items:
                print(f"\n{label} ({len(items)}):")
                for b in items:
                    print(f"   {b['task_id']}: {b['reason']}")
        else:
            items = cat[key]
            if items:
                print(f"\n{label} ({len(items)}):")
                for t in items:
                    line = f"   [{t['id']}] {t['name']}"
                    if key == "pending" and t.get("owner"):
                        line += f"  ← {t['owner']}"
                    print(line)
    print()


def cmd_phases(args):
    p = _require()
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


def cmd_advance(args):
    try:
        p = _require()
        result = core.advance(p["id"], force=args.force)
        print(f"⏩ 阶段推进: {result['from']} → {result['to']}")
        if result["milestone"]:
            print(f"🎯 里程碑达成: {result['milestone']}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_note(args):
    try:
        p = _require()
        core.add_note(p["id"], args.text)
        print("📝 已记录")
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_log(args):
    p = _require()
    logs = p.get("log", [])
    n = args.n or 20
    icons = {"init": "🆕", "start": "🔄", "done": "✅", "block": "🚫", "unblock": "🔓",
             "advance": "⏩", "note": "📝", "subtask_add": "➕", "subtask_done": "✅", "subtask_block": "🚫"}
    for entry in logs[-n:]:
        icon = icons.get(entry.get("action", ""), "•")
        task = f" [{entry['task']}]" if entry.get("task") else ""
        detail = f" {entry.get('detail', '')}" if entry.get("detail") else ""
        print(f"  {entry['time']}  {icon}{task}{detail}")


def _require():
    try:
        return core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
