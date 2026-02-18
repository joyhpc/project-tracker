"""时间线管理引擎

功能：
1. 给任务设置预估工时（天）
2. 基于依赖图计算最早开始/最晚开始时间
3. 计算项目总工期
4. 识别关键路径（时间维度）
5. 甘特图文本可视化
"""
from datetime import datetime, timedelta
from . import flow as flowmod
from .engine import build_dep_graph


# ── 默认工时估算（天）──────────────────────────────────

# 基于任务特征的默认工时，用户可通过 pt estimate 覆盖
DEFAULT_ESTIMATES = {
    # 通用规则：有 gate 的任务通常更久
    "gate": 5,
    "critical": 7,
    "review": 3,
    "default": 3,
    # 关键词匹配
    "keywords": {
        "评审": 2,
        "审批": 5,
        "设计": 10,
        "开发": 15,
        "测试": 10,
        "制样": 7,
        "布局": 5,
        "走线": 7,
        "联调": 10,
        "试产": 14,
        "送样": 5,
        "归档": 2,
        "培训": 1,
        "检索": 3,
        "选型": 5,
        "估算": 2,
    },
}


def estimate_task_days(task: dict) -> int:
    """根据任务特征估算工时（天）"""
    name = task.get("name", "")

    # 关键词匹配（取最长匹配）
    for kw, days in DEFAULT_ESTIMATES["keywords"].items():
        if kw in name:
            # 有 gate 的加 2 天
            if task.get("gate"):
                days += 2
            return days

    # 特征匹配
    if task.get("critical"):
        return DEFAULT_ESTIMATES["critical"]
    if task.get("gate"):
        return DEFAULT_ESTIMATES["gate"]

    return DEFAULT_ESTIMATES["default"]


def compute_schedule(phase: dict, task_status: dict, start_date: datetime | None = None,
                     custom_estimates: dict | None = None) -> dict:
    """计算阶段内所有任务的时间安排

    返回:
        {
            task_id: {
                "name": str,
                "est_days": int,
                "earliest_start": int,  # 从项目开始的第几天
                "earliest_end": int,
                "latest_start": int,    # 最晚开始（不影响总工期）
                "slack": int,           # 松弛时间
                "is_critical": bool,    # 是否在关键路径上
                "status": str,          # done/in_progress/pending
            }
        }
    """
    if start_date is None:
        start_date = datetime.now()
    if custom_estimates is None:
        custom_estimates = {}

    graph = build_dep_graph(phase)
    tasks = graph["tasks"]
    deps = graph["deps"]

    schedule = {}

    # 1. 前向传播：计算最早开始/结束时间
    def earliest_end(tid):
        if tid in schedule and "earliest_end" in schedule[tid]:
            return schedule[tid]["earliest_end"]

        est = custom_estimates.get(tid, estimate_task_days(tasks[tid]))
        status = task_status.get(tid, {}).get("status", "pending")

        # 已完成的任务工时为 0（不占时间）
        if status == "done":
            est = 0

        dep_ends = []
        for d in deps.get(tid, []):
            if d in tasks:
                dep_ends.append(earliest_end(d))

        es = max(dep_ends) if dep_ends else 0
        ee = es + est

        if tid not in schedule:
            schedule[tid] = {}
        schedule[tid].update({
            "name": tasks[tid].get("name", tid),
            "est_days": est,
            "earliest_start": es,
            "earliest_end": ee,
            "status": status,
        })
        return ee

    # 计算所有任务
    for tid in tasks:
        earliest_end(tid)

    # 2. 项目总工期
    project_end = max(s["earliest_end"] for s in schedule.values()) if schedule else 0

    # 3. 后向传播：计算最晚开始时间和松弛
    rdeps = graph["rdeps"]

    def latest_start(tid):
        if "latest_start" in schedule[tid]:
            return schedule[tid]["latest_start"]

        successors = rdeps.get(tid, [])
        if not successors:
            ls = project_end - schedule[tid]["est_days"]
        else:
            ls = min(latest_start(s) for s in successors if s in schedule) - schedule[tid]["est_days"]

        slack = ls - schedule[tid]["earliest_start"]
        schedule[tid]["latest_start"] = ls
        schedule[tid]["slack"] = max(0, slack)
        schedule[tid]["is_critical"] = (slack <= 0)
        return ls

    for tid in tasks:
        latest_start(tid)

    return {
        "tasks": schedule,
        "total_days": project_end,
        "start_date": start_date,
        "end_date": start_date + timedelta(days=project_end),
    }


def compute_full_schedule(flow: dict, current_phase: str, task_status: dict,
                          start_date: datetime | None = None,
                          custom_estimates: dict | None = None) -> dict:
    """计算从当前阶段到结束的完整时间线"""
    if start_date is None:
        start_date = datetime.now()
    if custom_estimates is None:
        custom_estimates = {}

    phases = flow.get("phases", [])
    order = [p["id"] for p in phases]
    phase_map = {p["id"]: p for p in phases}

    try:
        start_idx = order.index(current_phase)
    except ValueError:
        return {"error": f"未知阶段: {current_phase}"}

    phase_schedules = []
    cumulative_days = 0

    for pid in order[start_idx:]:
        phase = phase_map[pid]
        phase_start = start_date + timedelta(days=cumulative_days)
        sched = compute_schedule(phase, task_status, phase_start, custom_estimates)

        phase_schedules.append({
            "phase_id": pid,
            "phase_name": phase.get("name", pid),
            "milestone": phase.get("milestone"),
            "start_day": cumulative_days,
            "duration": sched["total_days"],
            "end_day": cumulative_days + sched["total_days"],
            "tasks": sched["tasks"],
        })
        cumulative_days += sched["total_days"]

    total_end = start_date + timedelta(days=cumulative_days)

    return {
        "phases": phase_schedules,
        "total_days": cumulative_days,
        "start_date": start_date,
        "end_date": total_end,
    }


def format_timeline(result: dict) -> str:
    """格式化时间线输出"""
    lines = []
    start = result["start_date"]
    end = result["end_date"]
    total = result["total_days"]

    lines.append(f"📅 项目时间线")
    lines.append(f"   开始: {start.strftime('%Y-%m-%d')}  →  预计完成: {end.strftime('%Y-%m-%d')}")
    lines.append(f"   总工期: {total} 天 ({total // 7} 周 {total % 7} 天)")
    lines.append("")

    for ps in result.get("phases", []):
        phase_start = start + timedelta(days=ps["start_day"])
        phase_end = start + timedelta(days=ps["end_day"])
        ms = f" [{ps['milestone']}]" if ps.get("milestone") else ""

        lines.append(f"{'─'*55}")
        lines.append(f"📍 {ps['phase_id']}: {ps['phase_name']}{ms}")
        lines.append(f"   {phase_start.strftime('%m/%d')} → {phase_end.strftime('%m/%d')} ({ps['duration']} 天)")
        lines.append("")

        # 甘特图
        tasks = ps.get("tasks", {})
        if not tasks:
            continue

        max_days = ps["duration"] or 1
        bar_width = 30  # 甘特条最大宽度

        # 按最早开始时间排序
        sorted_tasks = sorted(tasks.items(), key=lambda x: x[1]["earliest_start"])

        for tid, t in sorted_tasks:
            name = t["name"][:16].ljust(16)
            est = t["est_days"]
            es = t["earliest_start"]
            status = t["status"]

            # 状态图标
            if status == "done":
                icon = "✅"
            elif status == "in_progress":
                icon = "🔄"
            elif t.get("is_critical"):
                icon = "🔴"
            else:
                icon = "  "

            # 甘特条
            if max_days > 0 and est > 0:
                bar_start = int(es / max_days * bar_width)
                bar_len = max(1, int(est / max_days * bar_width))
                bar = " " * bar_start + "█" * bar_len
                bar = bar[:bar_width].ljust(bar_width)
            elif status == "done":
                bar = "✓".ljust(bar_width)
            else:
                bar = " " * bar_width

            slack_str = f"+{t['slack']}d" if t.get("slack", 0) > 0 else ""
            days_str = f"{est}d" if est > 0 else "done"

            lines.append(f"  {icon} {name} |{bar}| {days_str:>4s} {slack_str}")

        lines.append("")

    # 关键路径摘要
    critical_tasks = []
    for ps in result.get("phases", []):
        for tid, t in ps.get("tasks", {}).items():
            if t.get("is_critical") and t["status"] != "done":
                critical_tasks.append(f"{tid}")

    if critical_tasks:
        lines.append(f"🔴 关键路径任务 ({len(critical_tasks)} 个):")
        lines.append(f"   {' → '.join(critical_tasks[:15])}")
        if len(critical_tasks) > 15:
            lines.append(f"   ... 还有 {len(critical_tasks) - 15} 个")
        lines.append("")

    return "\n".join(lines)


def format_phase_gantt(phase: dict, task_status: dict,
                       custom_estimates: dict | None = None) -> str:
    """单阶段甘特图"""
    sched = compute_schedule(phase, task_status, custom_estimates=custom_estimates)
    result = {
        "start_date": sched["start_date"],
        "end_date": sched["end_date"],
        "total_days": sched["total_days"],
        "phases": [{
            "phase_id": phase.get("id", "?"),
            "phase_name": phase.get("name", ""),
            "milestone": phase.get("milestone"),
            "start_day": 0,
            "duration": sched["total_days"],
            "end_day": sched["total_days"],
            "tasks": sched["tasks"],
        }],
    }
    return format_timeline(result)
