"""风险评估引擎

多维度风险评分:
1. 依赖深度 — 下游任务越多，风险越高
2. 关键路径 — 在关键路径上的任务延误直接影响总工期
3. Gate 准入 — 有审批/准入条件的任务不确定性高
4. 资源瓶颈 — 某个 owner 负载过重
5. 长周期 — 预估工时长的任务风险高
6. 外部依赖 — 涉及采购/送样/认证等外部环节
"""
from .engine import build_dep_graph, _count_downstream, find_critical_path
from .timeline import estimate_task_days


EXTERNAL_KEYWORDS = ["申请", "审批", "送样", "制样", "采购", "知识产权", "新品承认", "认证", "EQ"]


def assess_task_risk(task: dict, graph: dict, critical_set: set,
                     owner_load: dict, custom_estimates: dict) -> dict:
    """评估单个任务的风险"""
    tid = task["id"]
    name = task.get("name", "")
    factors = []
    score = 0

    # 1. 下游影响
    downstream = _count_downstream(tid, graph["rdeps"], set())
    if downstream >= 5:
        score += 30
        factors.append(f"阻塞下游 {downstream} 个任务")
    elif downstream >= 3:
        score += 15
        factors.append(f"阻塞下游 {downstream} 个任务")

    # 2. 关键路径
    if tid in critical_set:
        score += 25
        factors.append("关键路径上")

    # 3. Gate 准入
    if task.get("gate"):
        score += 15
        factors.append(f"准入: {task['gate']}")

    # 4. Critical 标记
    if task.get("critical"):
        score += 20
        factors.append("关键节点")

    # 5. 资源瓶颈
    owner = task.get("owner", "")
    for o in owner.replace("/", ",").replace("、", ",").split(","):
        o = o.strip()
        if o and owner_load.get(o, 0) >= 8:
            score += 10
            factors.append(f"{o} 负载过重 ({owner_load[o]} 个任务)")
            break

    # 6. 长周期
    est = custom_estimates.get(tid, estimate_task_days(task))
    if est >= 14:
        score += 15
        factors.append(f"预估 {est} 天")
    elif est >= 7:
        score += 5

    # 7. 外部依赖
    for kw in EXTERNAL_KEYWORDS:
        if kw in name:
            score += 10
            factors.append("涉及外部环节")
            break

    level = "🔴 高" if score >= 40 else "🟡 中" if score >= 20 else "🟢 低"

    return {
        "task_id": tid,
        "name": name,
        "score": score,
        "level": level,
        "factors": factors,
        "owner": owner,
        "est_days": est,
    }


def assess_phase_risk(phase: dict, task_status: dict, custom_estimates: dict = None) -> list[dict]:
    """评估阶段内所有未完成任务的风险"""
    if custom_estimates is None:
        custom_estimates = {}

    graph = build_dep_graph(phase)
    cp = find_critical_path(phase, task_status)
    critical_set = set(cp)

    # 计算 owner 负载
    owner_load = {}
    for tid, task in graph["tasks"].items():
        if task_status.get(tid, {}).get("status") == "done":
            continue
        for o in task.get("owner", "").replace("/", ",").replace("、", ",").split(","):
            o = o.strip()
            if o:
                owner_load[o] = owner_load.get(o, 0) + 1

    results = []
    for tid, task in graph["tasks"].items():
        if task_status.get(tid, {}).get("status") == "done":
            continue
        r = assess_task_risk(task, graph, critical_set, owner_load, custom_estimates)
        results.append(r)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def assess_project_risk(flow: dict, current_phase: str, task_status: dict,
                        custom_estimates: dict = None) -> dict:
    """评估整个项目的风险"""
    if custom_estimates is None:
        custom_estimates = {}

    phases = flow.get("phases", [])
    order = [p["id"] for p in phases]
    phase_map = {p["id"]: p for p in phases}

    try:
        start_idx = order.index(current_phase)
    except ValueError:
        return {"error": f"未知阶段: {current_phase}"}

    all_risks = []
    phase_risks = []

    for pid in order[start_idx:]:
        phase = phase_map[pid]
        risks = assess_phase_risk(phase, task_status, custom_estimates)
        high = sum(1 for r in risks if r["score"] >= 40)
        med = sum(1 for r in risks if 20 <= r["score"] < 40)

        phase_risks.append({
            "phase_id": pid,
            "phase_name": phase.get("name", pid),
            "high": high,
            "medium": med,
            "top_risks": risks[:3],
        })
        all_risks.extend(risks)

    all_risks.sort(key=lambda x: x["score"], reverse=True)

    # 资源瓶颈汇总
    owner_total = {}
    for pid in order[start_idx:]:
        phase = phase_map[pid]
        for task in phase.get("tasks", []):
            if task_status.get(task["id"], {}).get("status") == "done":
                continue
            for o in task.get("owner", "").replace("/", ",").replace("、", ",").split(","):
                o = o.strip()
                if o:
                    owner_total[o] = owner_total.get(o, 0) + 1

    bottlenecks = sorted(owner_total.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "phase_risks": phase_risks,
        "top_risks": all_risks[:10],
        "bottlenecks": bottlenecks,
        "total_high": sum(pr["high"] for pr in phase_risks),
        "total_medium": sum(pr["medium"] for pr in phase_risks),
    }


def format_risk_report(result: dict) -> str:
    """格式化风险报告"""
    lines = []

    lines.append(f"🔴 高风险: {result['total_high']} 个  🟡 中风险: {result['total_medium']} 个")
    lines.append("")

    # Top 10 风险
    lines.append("📊 风险排行 (Top 10):\n")
    for i, r in enumerate(result["top_risks"], 1):
        lines.append(f"  {i}. {r['level']} [{r['task_id']}] {r['name']}  (分数: {r['score']})")
        if r["factors"]:
            lines.append(f"     原因: {'; '.join(r['factors'])}")
    lines.append("")

    # 按阶段
    lines.append("📍 各阶段风险:\n")
    for pr in result["phase_risks"]:
        if pr["high"] == 0 and pr["medium"] == 0:
            lines.append(f"  🟢 {pr['phase_name']}: 无显著风险")
            continue
        tag = f"🔴×{pr['high']}" if pr["high"] else ""
        tag += f" 🟡×{pr['medium']}" if pr["medium"] else ""
        lines.append(f"  {pr['phase_name']}: {tag.strip()}")
        for r in pr["top_risks"]:
            if r["score"] >= 20:
                lines.append(f"    {r['level']} [{r['task_id']}] {r['name']}")
    lines.append("")

    # 资源瓶颈
    if result["bottlenecks"]:
        lines.append("👥 资源瓶颈:\n")
        for owner, count in result["bottlenecks"]:
            bar = "█" * min(count, 20)
            lines.append(f"  {owner:16s} {bar} {count}个任务")
    lines.append("")

    return "\n".join(lines)
