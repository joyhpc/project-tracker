"""节点 CRUD 命令 — add / rm / skip / undo / rewire / replace"""
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


def cmd_rewire(args):
    """底层拓扑原语: 修改节点的依赖关系"""
    p = core.require_active()

    add_deps = [d.strip() for d in args.add.split(",")] if args.add else None
    rm_deps = [d.strip() for d in args.rm.split(",")] if args.rm else None

    if not add_deps and not rm_deps:
        print("❌ 至少指定 --add 或 --rm")
        return

    with core.mutate(p) as proj:
        node = core.rewire(proj, args.target, add_deps=add_deps, rm_deps=rm_deps)

    print(f"✅ 已修改: [{args.target}] {node.get('name', '')}")
    print(f"   depends = {node.get('depends', [])}")
    if add_deps:
        print(f"   + 添加: {', '.join(add_deps)}")
    if rm_deps:
        print(f"   - 移除: {', '.join(rm_deps)}")


def cmd_replace(args):
    """高阶业务宏: 方案交接棒"""
    p = core.require_active()

    with core.mutate(p) as proj:
        result = core.replace(proj, args.old, entry=args.entry,
                              exit=args.exit)

    old = result["old"]
    entry_node = result["entry"]
    exit_node = result["exit"]

    print(f"✅ 方案替换完成")
    print(f"   旧方案: [{args.old}] {old.get('name', '')} → skipped")
    print(f"   入口接管: [{args.entry}] {entry_node.get('name', '')}")
    if args.exit and args.exit != args.entry:
        print(f"   出口交接: [{args.exit}] {exit_node.get('name', '')}")
    if result["transferred_upstream"]:
        print(f"   继承上游: {', '.join(result['transferred_upstream'])}")
    if result["transferred_downstream"]:
        print(f"   接管下游: {', '.join(result['transferred_downstream'])}")
