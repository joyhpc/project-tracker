"""多项目资源冲突检测 v2 — 基于全局 DAG

场景：同时跑多个项目时，检测：
1. 同一 owner 在多个项目中的任务冲突
2. 资源过载预警
"""
from . import core
from .engine import compute_cpm


def detect_conflicts() -> dict:
    """检测所有活跃项目间的资源冲突"""
    projects = core.list_projects()
    if len(projects) < 2:
        return {"owner_conflicts": [], "overloaded": [],
                "project_count": len(projects)}

    # 收集每个项目中每个 owner 的任务
    owner_tasks = {}

    for p in projects:
        pid = p["id"]
        flow = core._project_as_flow(p)
        task_status = core._get_task_status(p)
        cpm = compute_cpm(flow, task_status)
        critical_set = set(cpm["critical_path"])

        for node in flow.get("nodes", []):
            nid = node["id"]
            if node.get("status") == "done":
                continue
            if node.get("type") == "milestone":
                continue

            owners = node.get("owner", "").replace("/", ",").replace("、", ",").split(",")
            for o in owners:
                o = o.strip()
                if not o:
                    continue
                owner_tasks.setdefault(o, []).append({
                    "project_id": pid,
                    "project_name": p["name"],
                    "task_id": nid,
                    "task_name": node["name"],
                    "phase": node.get("phase", ""),
                    "is_critical": nid in critical_set,
                    "slack": cpm["nodes"].get(nid, {}).get("slack", 999),
                })

    # 1. 跨项目冲突
    owner_conflicts = []
    for owner, tasks in owner_tasks.items():
        project_ids = set(t["project_id"] for t in tasks)
        if len(project_ids) < 2:
            continue

        by_project = {}
        for t in tasks:
            by_project.setdefault(t["project_id"], []).append(t)

        critical_count = sum(1 for t in tasks if t["is_critical"])

        owner_conflicts.append({
            "owner": owner,
            "projects": list(project_ids),
            "total_tasks": len(tasks),
            "critical_tasks": critical_count,
            "by_project": by_project,
        })

    owner_conflicts.sort(key=lambda x: x["total_tasks"], reverse=True)

    # 2. 资源过载
    overloaded = []
    for owner, tasks in owner_tasks.items():
        if len(tasks) >= 10:
            overloaded.append({
                "owner": owner,
                "total_tasks": len(tasks),
                "critical_tasks": sum(1 for t in tasks if t["is_critical"]),
                "projects": list(set(t["project_id"] for t in tasks)),
            })
    overloaded.sort(key=lambda x: x["total_tasks"], reverse=True)

    return {
        "owner_conflicts": owner_conflicts,
        "overloaded": overloaded,
        "project_count": len(projects),
    }


def format_conflicts(result: dict) -> str:
    """格式化冲突报告"""
    lines = []
    lines.append(f"📊 {result['project_count']} 个项目资源分析\n")

    conflicts = result["owner_conflicts"]
    if conflicts:
        lines.append(f"⚠️ 跨项目资源冲突 ({len(conflicts)} 人):\n")
        for c in conflicts:
            crit = f" (🔴 {c['critical_tasks']} 个关键任务)" if c["critical_tasks"] else ""
            lines.append(f"  {c['owner']}: {c['total_tasks']} 个任务跨 {len(c['projects'])} 个项目{crit}")
            for pid, tasks in c["by_project"].items():
                names = [t["task_name"] for t in tasks[:3]]
                more = f" +{len(tasks)-3}" if len(tasks) > 3 else ""
                lines.append(f"    {pid}: {', '.join(names)}{more}")
        lines.append("")
    else:
        lines.append("✅ 无跨项目资源冲突\n")

    if result["overloaded"]:
        lines.append(f"🔥 资源过载 ({len(result['overloaded'])} 人):\n")
        for o in result["overloaded"]:
            bar = "█" * min(o["total_tasks"], 25)
            lines.append(f"  {o['owner']:16s} {bar} {o['total_tasks']}个任务 ({len(o['projects'])}个项目)")
        lines.append("")

    return "\n".join(lines)
