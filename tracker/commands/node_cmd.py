"""节点 CRUD 命令 — add / rm / skip / undo"""
from .. import core


def cmd_add(args):
    """添加一等节点到 DAG"""
    p = core.require_active()

    node_data = {
        "id": args.id,
        "name": args.name or args.id,
        "phase": args.phase or "DETAIL",
    }
    if args.days:
        node_data["days"] = args.days
    if args.owner:
        node_data["owner"] = args.owner
    if args.note:
        node_data["note"] = args.note

    depends = [d.strip() for d in args.depends.split(",")] if args.depends else []
    leads_to = [d.strip() for d in args.leads_to.split(",")] if args.leads_to else []

    with core.mutate(p) as proj:
        node = core.add_node(proj, node_data, depends=depends, leads_to=leads_to)

    # 输出结果
    info = core.get_status(p)
    cpm_nodes = info["cpm"].get("nodes", {})
    cn = cpm_nodes.get(args.id, {})
    critical = info["cpm"].get("critical_path", [])
    on_cp = "🔴 关键路径" if args.id in critical else ""

    print(f"✅ 已添加: [{args.id}] {node['name']}")
    print(f"   阶段: {node['phase']} | 工时: {node.get('days', 3)}天 | slack={cn.get('slack', '?')}天 {on_cp}")
    if depends:
        print(f"   上游: {', '.join(depends)}")
    if leads_to:
        print(f"   下游: {', '.join(leads_to)} (已自动接入)")


def cmd_rm(args):
    """从 DAG 移除节点"""
    p = core.require_active()

    with core.mutate(p) as proj:
        removed = core.remove_node(proj, args.id, stitch=args.stitch)

    print(f"✅ 已删除: [{args.id}] {removed.get('name', '')}")
    if args.stitch:
        print(f"   依赖链已自动缝合")


def cmd_skip(args):
    """软删除: 标记节点为 skipped"""
    p = core.require_active()

    with core.mutate(p) as proj:
        node = core.skip_node(proj, args.id, reason=args.reason or "")

    print(f"✅ 已跳过: [{args.id}] {node.get('name', '')}")
    if args.reason:
        print(f"   原因: {args.reason}")
    print(f"   节点保留在 DAG 中，工时按 0 天计算")


def cmd_undo(args):
    """恢复到上一个快照"""
    p = core.require_active()
    msg = core.undo(p["id"])
    print(f"✅ {msg}")
