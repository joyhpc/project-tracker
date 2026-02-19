"""项目管理命令: init, list, switch, status, phases, note, log"""
import sys
from .. import core


def _icon(status: str) -> str:
    return {"done": "✅", "in_progress": "🔄", "blocked": "🚫", "pending": "⏳", "expanded": "📦"}.get(status, "❓")


def cmd_init(args):
    try:
        p = core.init_project(args.id, args.name, args.flow)
        print(f"✅ 项目已创建: {p['id']} ({p['name']})")
        print(f"   流程: {p['flow']}, {len(p['nodes'])} 个节点")
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
        total = len(p.get("nodes", []))
        done = sum(1 for n in p.get("nodes", []) if n.get("status") == "done")
        print(f"  {'●' if p.get('_active') else '○'} {p['id']} | {p['name']} | {done}/{total}{marker}")


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
    classified = info["classified"]
    cpm = info["cpm"]

    print(f"\n📋 {p['name']} ({p['id']})")
    print(f"📊 进度: {info['done_count']}/{info['total']}")
    print(f"⏱️  总工期: {cpm['total_days']:.0f} 天")

    # 阶段进度
    phase_progress = core.get_phase_progress(p)
    if phase_progress:
        print(f"\n📍 阶段进度:")
        for ph in phase_progress:
            bar = "█" * ph["done"] + "░" * (ph["total"] - ph["done"])
            check = " ✅" if ph["complete"] else ""
            print(f"   {ph['name']}: [{bar}] {ph['progress']}{check}")

    # 关键路径
    if cpm["critical_path"]:
        print(f"\n🔴 关键路径 ({len(cpm['critical_path'])} 节点):")
        graph_nodes = {n["id"]: n for n in p["nodes"]}
        for nid in cpm["critical_path"][:8]:
            node = graph_nodes.get(nid, {})
            r = cpm["nodes"][nid]
            print(f"   [{nid}] {node.get('name','')} ({r['days']:.0f}天, ES={r['es']:.0f})")
        if len(cpm["critical_path"]) > 8:
            print(f"   ... 共 {len(cpm['critical_path'])} 个")

    # 阻塞
    if info["blockers"]:
        print(f"\n🚫 阻塞 ({len(info['blockers'])}):")
        for b in info["blockers"]:
            print(f"   {b['task_id']}: {b['reason']}")

    # 可执行任务
    ready = classified["ready"]
    if ready:
        print(f"\n✅ 可执行 ({len(ready)}):")
        for t in ready[:5]:
            slack = cpm["nodes"].get(t["id"], {}).get("slack", 0)
            crit = " 🔴" if cpm["nodes"].get(t["id"], {}).get("critical") else ""
            print(f"   [{t['id']}] {t['name']}  ← {t.get('owner','?')} (slack={slack:.0f}天){crit}")
        if len(ready) > 5:
            print(f"   ... 共 {len(ready)} 个")

    print()


def cmd_phases(args):
    p = _require()
    phase_progress = core.get_phase_progress(p)
    if not phase_progress:
        print("没有阶段信息")
        return

    print(f"\n📋 {p['name']} - 阶段进度\n")
    for ph in phase_progress:
        pct = (ph["done"] / ph["total"] * 100) if ph["total"] > 0 else 0
        check = " ✅" if ph["complete"] else ""
        print(f"  {'●' if 0 < pct < 100 else '○'} {ph['id']} - {ph['name']} [{ph['progress']}] {pct:.0f}%{check}")
    print()


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
             "note": "📝", "subtask_add": "➕", "subtask_done": "✅", "subtask_block": "🚫",
             "subtask_template_load": "📦"}
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
