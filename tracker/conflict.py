"""多项目资源冲突检测

场景：同时跑多个项目时，检测：
1. 同一 owner 在多个项目中的任务冲突
2. 时间线重叠的关键任务
3. 资源过载预警
"""
from datetime import datetime, timedelta
from . import core, flow as flowmod
from .timeline import compute_full_schedule
from .engine import find_critical_path, build_dep_graph


def detect_conflicts(start_dates: dict = None, custom_estimates: dict = None) -> dict:
    """检测所有活跃项目间的资源冲突

    Args:
        start_dates: {project_id: datetime} 各项目开始日期
        custom_estimates: {project_id: {task_id: days}} 各项目自定义工时

    Returns:
        {
            "owner_conflicts": [...],  # 同一人跨项目冲突
            "overloaded": [...],       # 资源过载
            "timeline_overlaps": [...], # 时间线重叠
        }
    """
    if start_dates is None:
        start_dates = {}
    if custom_estimates is None:
        custom_estimates = {}

    projects = core.list_projects()
    if len(projects) < 2:
        return {"owner_conflicts": [], "overloaded": [], "timeline_overlaps": [],
                "project_count": len(projects)}

    # 收集每个项目中每个 owner 的任务
    owner_tasks = {}  # owner -> [(project_id, project_name, task_id, task_name, phase, is_critical)]

    project_schedules = {}

    for p in projects:
        pid = p["id"]
        fl = flowmod.load_flow(p.get("flow", "duxin"))
        task_status = p.get("tasks", {})
        est = custom_estimates.get(pid, p.get("estimates", {}))

        # 计算时间线
        sd = start_dates.get(pid, datetime.now())
        sched = compute_full_schedule(fl, p["current_phase"], task_status, sd, est)
        project_schedules[pid] = sched

        # 收集 owner 任务
        for phase in fl.get("phases", []):
            cp = find_critical_path(phase, task_status)
            critical_set = set(cp)

            for task in phase.get("tasks", []):
                tid = task["id"]
                if task_status.get(tid, {}).get("status") == "done":
                    continue

                owners = task.get("owner", "").replace("/", ",").replace("、", ",").split(",")
                for o in owners:
                    o = o.strip()
                    if not o:
                        continue
                    owner_tasks.setdefault(o, []).append({
                        "project_id": pid,
                        "project_name": p["name"],
                        "task_id": tid,
                        "task_name": task["name"],
                        "phase": phase.get("name", ""),
                        "is_critical": tid in critical_set,
                    })

    # 1. 跨项目冲突：同一 owner 在多个项目有任务
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
            "by_project": {pid: ts for pid, ts in by_project.items()},
        })

    owner_conflicts.sort(key=lambda x: x["total_tasks"], reverse=True)

    # 2. 资源过载：单人总任务数过多
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

    # 跨项目冲突
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

    # 过载
    if result["overloaded"]:
        lines.append(f"🔥 资源过载 ({len(result['overloaded'])} 人):\n")
        for o in result["overloaded"]:
            bar = "█" * min(o["total_tasks"], 25)
            lines.append(f"  {o['owner']:16s} {bar} {o['total_tasks']}个任务 ({len(o['projects'])}个项目)")
        lines.append("")

    return "\n".join(lines)
