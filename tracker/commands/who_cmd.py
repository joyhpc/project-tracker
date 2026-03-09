"""人员视图命令"""
import sys
from . import _icon, _require
from .. import core
from ..engine import compute_cpm, build_graph
from ..project_model import _effective_nodes, _undone_dependencies, _project_as_flow, _get_task_status


def cmd_who(args):
    """按人员维度展示任务分配"""
    p = _require()

    nodes = _effective_nodes(p)

    # 计算 CPM 获取 slack 和关键路径
    flow = _project_as_flow(p)
    task_status = _get_task_status(p)
    try:
        cpm = compute_cpm(flow, task_status)
        critical_set = set(cpm.get("critical_path", []))
    except Exception:
        cpm = {"nodes": {}}
        critical_set = set()

    # 按 owner 分组
    owner_map = {}
    for node in nodes:
        owner = node.get("owner", "") or "未分配"
        owner_map.setdefault(owner, []).append(node)

    # 可选：只显示特定人员
    filter_owner = getattr(args, "owner", None)

    # 可选：只显示特定状态
    filter_status = getattr(args, "status", None)

    print(f"\n📋 {p.get('name', p['id'])} - 人员分配\n")

    # 排序：活跃任务多的人排前面，"未分配"排最后
    def sort_key(item):
        owner, tasks = item
        if owner == "未分配":
            return (1, 0, owner)
        active = sum(1 for t in tasks if t.get("status") in ("in_progress", "pending"))
        return (0, -active, owner)

    critical_owners = set()

    for owner, tasks in sorted(owner_map.items(), key=sort_key):
        if filter_owner and owner != filter_owner:
            continue

        # 过滤已完成的？默认显示 in_progress + pending + blocked
        display_tasks = tasks
        if not getattr(args, "all", False):
            display_tasks = [t for t in tasks if t.get("status") != "done"]

        if filter_status:
            display_tasks = [t for t in display_tasks if t.get("status") == filter_status]

        if not display_tasks and not getattr(args, "all", False):
            continue

        # 统计
        active_count = len([t for t in tasks if t.get("status") in ("in_progress", "pending", "blocked")])
        done_count = len([t for t in tasks if t.get("status") == "done"])

        count_str = f"{active_count} active"
        if done_count:
            count_str += f", {done_count} done"

        print(f"  {owner} ({count_str})")

        for node in display_tasks:
            nid = node["id"]
            status = node.get("status", "pending")
            name = node.get("name", nid)
            icon = _icon(status)

            # CPM info
            cpm_info = cpm["nodes"].get(nid, {})
            slack = cpm_info.get("slack", 0)
            is_critical = nid in critical_set

            if is_critical:
                critical_owners.add(owner)

            # Build suffix
            suffix_parts = []
            if status == "in_progress" or status == "pending":
                if slack == 0 and is_critical:
                    suffix_parts.append("🔴")
                elif slack > 0:
                    suffix_parts.append(f"slack={slack:.0f}d")

            if status == "pending":
                undone = _undone_dependencies(p, node)
                if undone:
                    # Show what it's waiting for
                    wait_names = []
                    for dep_id in undone[:2]:
                        dep_node = next((n for n in nodes if n["id"] == dep_id), None)
                        if dep_node:
                            wait_names.append(dep_node.get("name", dep_id))
                        else:
                            wait_names.append(dep_id)
                    wait_str = ", ".join(wait_names)
                    if len(undone) > 2:
                        wait_str += f" +{len(undone)-2}"
                    suffix_parts.append(f"等待: {wait_str}")

            suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
            print(f"    {icon} [{nid}] {name}{suffix}")

        print()

    # 汇总
    total_owners = len([o for o in owner_map if o != "未分配"])
    total_tasks = len(nodes)

    if owner_map:
        busiest = max(
            ((o, len([t for t in ts if t.get("status") != "done"]))
             for o, ts in owner_map.items() if o != "未分配"),
            key=lambda x: x[1],
            default=("N/A", 0)
        )

        print(f"  ── 汇总 ──")
        print(f"  总人数: {total_owners} | 总任务: {total_tasks}")
        if busiest[1] > 0:
            print(f"  负载最高: {busiest[0]} ({busiest[1]} active)")
        if critical_owners:
            print(f"  🔴 关键路径: {', '.join(sorted(critical_owners))}")
    print()
