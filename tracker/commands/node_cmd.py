"""节点 CRUD 命令 — add / rm / skip / undo / rewire / replace"""
import json
import sys
from .. import core


def _output(data: dict, json_mode: bool = False, dry_run: bool = False):
    """统一输出函数 (支持 --json 和 --dry-run)"""
    if dry_run:
        data["dry_run"] = True
    if json_mode:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        # 人类可读格式
        if dry_run:
            print("🔍 [DRY RUN] 试运行模式，不会保存文件")
        if data.get("success"):
            print(f"✅ {data.get('message', '操作成功')}")
            details = data.get("details", {})
            for key, val in details.items():
                if val is None:
                    continue
                if isinstance(val, list):
                    print(f"   {key}: {', '.join(str(v) for v in val)}")
                else:
                    print(f"   {key}: {val}")
        else:
            print(f"❌ {data.get('error', '操作失败')}", file=sys.stderr)


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

    dry_run = getattr(args, 'dry_run', False)
    json_mode = getattr(args, 'json', False)

    try:
        with core.mutate(p, dry_run=dry_run) as proj:
            node = core.add_node(proj, node_data, depends=depends, leads_to=leads_to)

        # 获取 CPM 信息
        info = core.get_status(p)
        cpm_nodes = info["cpm"].get("nodes", {})
        cn = cpm_nodes.get(args.id, {})
        critical = info["cpm"].get("critical_path", [])

        _output({
            "success": True,
            "message": f"已添加: [{args.id}] {node['name']}",
            "node_id": args.id,
            "details": {
                "阶段": node['phase'],
                "工时": f"{node.get('days', 3)}天",
                "slack": f"{cn.get('slack', '?')}天",
                "关键路径": args.id in critical,
                "上游": depends if depends else None,
                "下游": leads_to if leads_to else None,
            }
        }, json_mode, dry_run)
    except Exception as e:
        _output({"success": False, "error": str(e)}, json_mode, dry_run)
        sys.exit(1)


def cmd_rm(args):
    """从 DAG 移除节点"""
    p = core.require_active()
    dry_run = getattr(args, 'dry_run', False)
    json_mode = getattr(args, 'json', False)

    try:
        with core.mutate(p, dry_run=dry_run) as proj:
            removed = core.remove_node(proj, args.id, stitch=args.stitch)

        _output({
            "success": True,
            "message": f"已删除: [{args.id}] {removed.get('name', '')}",
            "node_id": args.id,
            "details": {
                "缝合": "已自动缝合依赖链" if args.stitch else None,
            }
        }, json_mode, dry_run)
    except Exception as e:
        _output({"success": False, "error": str(e)}, json_mode, dry_run)
        sys.exit(1)


def cmd_skip(args):
    """软删除: 标记节点为 skipped"""
    p = core.require_active()
    dry_run = getattr(args, 'dry_run', False)
    json_mode = getattr(args, 'json', False)

    try:
        with core.mutate(p, dry_run=dry_run) as proj:
            node = core.skip_node(proj, args.id, reason=args.reason or "")

        _output({
            "success": True,
            "message": f"已跳过: [{args.id}] {node.get('name', '')}",
            "node_id": args.id,
            "details": {
                "原因": args.reason if args.reason else None,
                "说明": "节点保留在 DAG 中，工时按 0 天计算",
            }
        }, json_mode, dry_run)
    except Exception as e:
        _output({"success": False, "error": str(e)}, json_mode, dry_run)
        sys.exit(1)


def cmd_undo(args):
    """恢复到上一个快照"""
    p = core.require_active()
    json_mode = getattr(args, 'json', False)

    try:
        msg = core.undo(p["id"])
        _output({
            "success": True,
            "message": msg,
            "project_id": p["id"],
        }, json_mode)
    except Exception as e:
        _output({"success": False, "error": str(e)}, json_mode)
        sys.exit(1)


def cmd_rewire(args):
    """底层拓扑原语: 修改节点的依赖关系"""
    p = core.require_active()
    dry_run = getattr(args, 'dry_run', False)
    json_mode = getattr(args, 'json', False)

    add_deps = [d.strip() for d in args.add.split(",")] if args.add else None
    rm_deps = [d.strip() for d in args.rm.split(",")] if args.rm else None

    if not add_deps and not rm_deps:
        _output({"success": False, "error": "至少指定 --add 或 --rm"}, json_mode, dry_run)
        sys.exit(1)

    try:
        with core.mutate(p, dry_run=dry_run) as proj:
            node = core.rewire(proj, args.target, add_deps=add_deps, rm_deps=rm_deps)

        _output({
            "success": True,
            "message": f"已修改: [{args.target}] {node.get('name', '')}",
            "node_id": args.target,
            "details": {
                "depends": node.get('depends', []),
                "+ 添加": add_deps if add_deps else None,
                "- 移除": rm_deps if rm_deps else None,
            }
        }, json_mode, dry_run)
    except Exception as e:
        _output({"success": False, "error": str(e)}, json_mode, dry_run)
        sys.exit(1)


def cmd_replace(args):
    """高阶业务宏: 方案交接棒"""
    p = core.require_active()
    dry_run = getattr(args, 'dry_run', False)
    json_mode = getattr(args, 'json', False)

    try:
        with core.mutate(p, dry_run=dry_run) as proj:
            result = core.replace(proj, args.old, entry=args.entry,
                                  exit=args.exit)

        old = result["old"]
        entry_node = result["entry"]
        exit_node = result["exit"]

        _output({
            "success": True,
            "message": "方案替换完成",
            "old_id": args.old,
            "entry_id": args.entry,
            "exit_id": args.exit,
            "details": {
                "旧方案": f"[{args.old}] {old.get('name', '')} → skipped",
                "入口接管": f"[{args.entry}] {entry_node.get('name', '')}",
                "出口交接": f"[{args.exit}] {exit_node.get('name', '')}" if args.exit and args.exit != args.entry else None,
                "继承上游": result["transferred_upstream"] if result["transferred_upstream"] else None,
                "接管下游": result["transferred_downstream"] if result["transferred_downstream"] else None,
            }
        }, json_mode, dry_run)
    except Exception as e:
        _output({"success": False, "error": str(e)}, json_mode, dry_run)
        sys.exit(1)


def cmd_promote(args):
    """提拔子任务为一等节点"""
    p = core.require_active()
    dry_run = getattr(args, 'dry_run', False)
    json_mode = getattr(args, 'json', False)

    new_node_data = {}
    if args.days:
        new_node_data["days"] = args.days
    if args.owner:
        new_node_data["owner"] = args.owner

    try:
        with core.mutate(p, dry_run=dry_run) as proj:
            result = core.promote(proj, args.parent, args.sub,
                                  new_node_data if new_node_data else None)

        new_node = result["new_node"]
        parent = result["parent"]

        # 获取 CPM 信息
        info = core.get_status(p)
        cpm_nodes = info["cpm"].get("nodes", {})
        cn = cpm_nodes.get(new_node["id"], {})
        critical = info["cpm"].get("critical_path", [])

        _output({
            "success": True,
            "message": f"已提拔: [{new_node['id']}] {new_node['name']}",
            "new_node_id": new_node["id"],
            "parent_id": args.parent,
            "details": {
                "阶段": new_node['phase'],
                "工时": f"{new_node.get('days', 3)}天",
                "slack": f"{cn.get('slack', '?')}天",
                "关键路径": new_node["id"] in critical,
                "继承上游": new_node.get("depends"),
                "父节点新增依赖": new_node["id"],
            }
        }, json_mode, dry_run)
    except Exception as e:
        _output({"success": False, "error": str(e)}, json_mode, dry_run)
        sys.exit(1)
