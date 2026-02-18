"""任务命令: tasks, start, done, block, unblock, next, sub*"""
import sys
from .. import core, flow as flowmod
from ..engine import analyze
from ..formatter import format_advice


def _icon(status: str) -> str:
    return {"done": "✅", "in_progress": "🔄", "blocked": "🚫", "pending": "⏳"}.get(status, "❓")


def _require():
    try:
        return core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_tasks(args):
    p = _require()
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
    p = _require()
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    phases = flowmod.get_phases(fl)
    phase = phases.get(p["current_phase"], {})
    task_status = p.get("tasks", {})
    blockers = p.get("blockers", [])

    result = analyze(phase, task_status, blockers)
    print(f"\n📋 {p['name']} ({p['id']})")
    print(f"📍 {phase.get('name', '')} ({p['current_phase']})\n")
    print(format_advice(result))


def cmd_start(args):
    try:
        p = _require()
        task = core.start_task(p["id"], args.task_id)
        print(f"🔄 已开始: [{args.task_id}] {task['name']}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_done(args):
    try:
        p = _require()
        result = core.done_task(p["id"], args.task_id, args.note or "", force=getattr(args, 'force', False))
        print(f"✅ 已完成: {args.task_id}")
        print(f"   进度: {result['progress']}")
        if result["complete"]:
            print("🎉 阶段完成！运行 pt advance 进入下一阶段。")
        elif result["remaining"]:
            print(f"   剩余: {', '.join(result['remaining'][:3])}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_block(args):
    try:
        p = _require()
        core.block_task(p["id"], args.task_id, args.reason)
        print(f"🚫 已阻塞: {args.task_id} - {args.reason}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_unblock(args):
    try:
        p = _require()
        core.unblock_task(p["id"], args.task_id)
        print(f"✅ 已解除阻塞: {args.task_id}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_sub_add(args):
    try:
        p = _require()
        kwargs = {}
        if args.owner:
            kwargs["owner"] = args.owner
        if args.depends:
            kwargs["depends"] = args.depends.split(",")
        core.add_subtask(p["id"], args.parent, args.sub_id, args.name, **kwargs)
        print(f"➕ 子任务已添加: {args.parent}.{args.sub_id} - {args.name}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_sub_done(args):
    try:
        p = _require()
        result = core.done_subtask(p["id"], args.full_id, args.note or "")
        print(f"✅ 子任务完成: {args.full_id}")
        if result.get("all_subtasks_done"):
            print(f"🎉 {result['hint']}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_sub_block(args):
    try:
        p = _require()
        core.block_subtask(p["id"], args.full_id, args.reason)
        print(f"🚫 子任务阻塞: {args.full_id} - {args.reason}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_sub_list(args):
    try:
        p = _require()
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


def cmd_sub_load(args):
    """从模板批量加载子任务"""
    try:
        if args.list:
            templates = core.list_subtask_templates()
            if not templates:
                print("没有可用的子任务模板")
                return
            print("\n📋 可用子任务模板:\n")
            for t in templates:
                print(f"  [{t['id']}] {t['name']} ({t['task_count']}个任务)")
                if t['description']:
                    print(f"       {t['description']}")
                print(f"       适用: {', '.join(t['attach_to'])}")
                print(f"       阶段: {' → '.join(t['phases'])}")
                print()
            return

        p = _require()
        result = core.load_subtask_template(p["id"], args.parent, args.template)
        print(f"✅ 已加载模板 [{result['template']}] {result['template_name']}")
        print(f"   → {result['parent']}: {result['loaded']} 个子任务")
        print(f"   查看: pt sl {args.parent}")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)
