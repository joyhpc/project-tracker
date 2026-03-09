"""任务命令: tasks, start, done, block, unblock, next, sub*"""
import sys
from .. import core
from ..engine import analyze, compute_cpm
from . import _icon, _require


def cmd_tasks(args):
    p = _require()
    nodes = p.get("nodes", [])

    # 可选按阶段过滤
    phase_filter = getattr(args, "phase", None)
    if phase_filter:
        nodes = [n for n in nodes if n.get("phase") == phase_filter]

    # 不显示子任务（有 parent 的）和已展开的父节点
    show_subs = getattr(args, "all", False)
    if not show_subs:
        nodes = [n for n in nodes if not n.get("parent") and n.get("status") != "expanded"]

    print(f"\n📋 {p['name']} - 任务列表 ({len(nodes)} 个)\n")
    for n in nodes:
        icon = _icon(n.get("status", "pending"))
        line = f"  {icon} [{n['id']}] {n['name']}"
        if n.get("owner"):
            line += f"  ← {n['owner']}"
        if n.get("type") == "milestone":
            line += " 🏁"
        print(line)
        if n.get("deliverables"):
            print(f"      交付件: {', '.join(n['deliverables'])}")
        if n.get("gate"):
            print(f"      准入: {n['gate']}")
        if n.get("status") == "blocked" and n.get("blocked_reason"):
            print(f"      阻塞: {n['blocked_reason']}")
    print()


def cmd_next(args):
    p = _require()
    flow = core._project_as_flow(p)
    task_status = core._get_task_status(p)
    blockers = p.get("blockers", [])

    result = analyze(flow, task_status, blockers)
    classified = result["classified"]
    cpm = result["cpm"]

    print(f"\n📋 {p['name']} ({p['id']})")
    print(f"⏱️  总工期: {cpm['total_days']:.0f} 天\n")

    # 推荐任务（按优先级排序的 ready 列表）
    ready = classified["ready"]
    if ready:
        print(f"🎯 推荐执行 ({len(ready)} 个可执行):\n")
        for i, t in enumerate(ready[:5], 1):
            slack = cpm["nodes"].get(t["id"], {}).get("slack", 0)
            crit = " 🔴关键" if cpm["nodes"].get(t["id"], {}).get("critical") else ""
            owner = t.get("owner", "未分配")
            print(f"  {i}. [{t['id']}] {t['name']}  ← {owner}")
            print(f"     slack={slack:.0f}天{crit}")
        if len(ready) > 5:
            print(f"\n  ... 共 {len(ready)} 个可执行任务")
    else:
        print("没有可执行的任务。")

    # 阻塞
    if result["blockers"]:
        print(f"\n🚫 阻塞影响:")
        for b in result["blockers"]:
            print(f"  [{b['task_id']}] {b['task_name']}: {b['reason']}")
            print(f"     影响 {b['downstream_count']} 个下游任务")

    # 并行建议
    parallel = result["parallel"]
    if len(parallel) > 1:
        print(f"\n👥 并行建议:")
        for owner, tasks in parallel.items():
            names = [t["name"] for t in tasks[:3]]
            print(f"  {owner}: {', '.join(names)}")

    print()


def cmd_start(args):
    p = _require()
    task_ids = args.task_id  # now a list
    for task_id in task_ids:
        try:
            task = core.start_task(p["id"], task_id)
            print(f"🔄 已开始: [{task_id}] {task['name']}")

            # 自动提示匹配的子任务模板
            matched = task.get("_matched_templates", [])
            for t in matched:
                print(f"\n💡 发现匹配的子任务模板: [{t['id']}] {t['name']} ({t['task_count']}个子任务)")
                print(f"   阶段: {' → '.join(t['phases'])}")
                print(f"   加载: pt sub-load {task_id} {t['id']}")
        except (RuntimeError, ValueError) as e:
            print(f"❌ {task_id}: {e}")
            if len(task_ids) == 1:
                sys.exit(1)


def cmd_done(args):
    p = _require()
    task_ids = args.task_id  # now a list
    note = getattr(args, 'note', '') or ''
    note_file = getattr(args, 'note_file', '') or ''
    force = getattr(args, 'force', False)
    quick = getattr(args, 'quick', False)

    for task_id in task_ids:
        try:
            # 检查该任务是否有未审核的 review
            reviews = p.get("reviews", [])
            unreviewed = [r for r in reviews if r.get("task") == task_id and r.get("reviewed") is False]
            if unreviewed:
                print(f"  ⚠️ {len(unreviewed)} 份回复未审核:")
                for r in unreviewed:
                    print(f"     - {r['file']}")
                print(f"  使用 pt review --approve <file> 审核，或 --force 强制完成")
                if not force:
                    if len(task_ids) == 1:
                        sys.exit(1)
                    continue

            if quick:
                result = core.quick_done(p["id"], task_id, note=note)
            else:
                result = core.done_task(p["id"], task_id, note,
                                        force=force,
                                        note_file=note_file)
            print(f"✅ 已完成: {task_id}")
            print(f"   进度: {result['progress']}")
            if note_file:
                print(f"   📎 备注文件: {note_file}")
            if result.get("remaining_ready"):
                print(f"   下一步可做: {', '.join(result['remaining_ready'])}")

            # 检查阶段完成
            p_data = core._load(p["id"])
            node = core._find_node(p_data, task_id)
            if node:
                phase = node.get("phase", "")
                if phase:
                    phase_nodes = [n for n in p_data.get("nodes", [])
                                   if n.get("phase") == phase and n.get("status") != "expanded"]
                    all_done = all(n.get("status") == "done" for n in phase_nodes)
                    if all_done and phase_nodes:
                        phase_name = phase
                        for ph in p_data.get("phases", []):
                            if ph.get("id") == phase:
                                phase_name = ph.get("name", phase)
                                break
                        print(f"🎉 阶段完成: {phase_name} ({len(phase_nodes)}/{len(phase_nodes)})")

        except (RuntimeError, ValueError) as e:
            print(f"❌ {task_id}: {e}")
            if len(task_ids) == 1:
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
            icon = _icon(s.get("status", "pending"))
            line = f"  {icon} [{s['id']}] {s['name']}"
            if s.get("owner"):
                line += f"  ← {s['owner']}"
            print(line)
            if s.get("blocked_reason"):
                print(f"      阻塞: {s['blocked_reason']}")
            if s.get("note") and s.get("status") == "done":
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

        # 显示外部依赖建议
        suggestions = result.get("external_dep_suggestions", [])
        if suggestions:
            auto = [s for s in suggestions if s["auto_added"]]
            manual = [s for s in suggestions if not s["auto_added"]]
            if auto:
                print(f"\n   🔗 已自动添加外部依赖:")
                for s in auto:
                    print(f"      {s['subtask']} ← {s['external_dep']} ({s['reason']})")
            if manual:
                print(f"\n   💡 建议添加的外部依赖（非必需，可提升调试效率）:")
                for s in manual:
                    print(f"      {s['subtask']} ← {s['external_dep']} ({s['reason']})")
    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)
