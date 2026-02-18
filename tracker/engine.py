"""智能推进引擎 - 基于依赖图分析最优行动"""
from . import flow as flowmod


def build_dep_graph(phase: dict) -> dict:
    """构建任务依赖图"""
    tasks = {t["id"]: t for t in phase.get("tasks", [])}
    # 正向依赖: task -> [依赖的任务]
    deps = {tid: t.get("depends", []) for tid, t in tasks.items()}
    # 反向依赖: task -> [被谁依赖]
    rdeps = {tid: [] for tid in tasks}
    for tid, dep_list in deps.items():
        for d in dep_list:
            if d in rdeps:
                rdeps[d].append(tid)
    return {"tasks": tasks, "deps": deps, "rdeps": rdeps}


def classify_tasks(phase: dict, task_status: dict) -> dict:
    """分类任务状态"""
    graph = build_dep_graph(phase)
    tasks = graph["tasks"]
    deps = graph["deps"]

    result = {
        "ready": [],       # 依赖已满足，可以立即开始
        "in_progress": [], # 进行中
        "blocked": [],     # 被标记阻塞
        "waiting": [],     # 依赖未满足，需要等待
        "done": [],        # 已完成
    }

    for tid, task in tasks.items():
        s = task_status.get(tid, {}).get("status", "pending")

        if s == "done":
            result["done"].append(task)
            continue
        if s == "blocked":
            result["blocked"].append(task)
            continue
        if s == "in_progress":
            result["in_progress"].append(task)
            continue

        # pending: 检查依赖
        dep_ids = deps.get(tid, [])
        all_deps_done = all(
            task_status.get(d, {}).get("status") == "done"
            for d in dep_ids
        )
        if all_deps_done:
            result["ready"].append(task)
        else:
            # 记录哪些依赖未完成
            missing = [d for d in dep_ids if task_status.get(d, {}).get("status") != "done"]
            task["_waiting_for"] = missing
            result["waiting"].append(task)

    return result


def compute_priority(task: dict, graph: dict, task_status: dict) -> int:
    """计算任务优先级（越高越应该先做）
    
    优先级因素:
    1. critical 标记 (+100)
    2. 下游任务数量（解锁越多越优先）(+10 * count)
    3. 有 gate 条件的（可能需要更多时间）(+5)
    4. 有交付件的（产出明确）(+3)
    """
    score = 0
    if task.get("critical"):
        score += 100

    # 计算下游解锁数
    rdeps = graph["rdeps"]
    downstream = _count_downstream(task["id"], rdeps, set())
    score += downstream * 10

    if task.get("gate"):
        score += 5
    if task.get("deliverables"):
        score += 3

    return score


def _count_downstream(tid: str, rdeps: dict, visited: set) -> int:
    """递归计算下游任务总数"""
    count = 0
    for child in rdeps.get(tid, []):
        if child not in visited:
            visited.add(child)
            count += 1 + _count_downstream(child, rdeps, visited)
    return count


def find_critical_path(phase: dict, task_status: dict) -> list[str]:
    """找到关键路径（最长依赖链）"""
    graph = build_dep_graph(phase)
    tasks = graph["tasks"]
    deps = graph["deps"]

    # 只考虑未完成的任务
    undone = {tid for tid in tasks if task_status.get(tid, {}).get("status") != "done"}

    memo = {}
    def longest_chain(tid):
        if tid in memo:
            return memo[tid]
        if tid not in undone:
            return []
        dep_chains = []
        for d in deps.get(tid, []):
            if d in undone:
                dep_chains.append(longest_chain(d))
        if dep_chains:
            best = max(dep_chains, key=len)
            result = best + [tid]
        else:
            result = [tid]
        memo[tid] = result
        return result

    all_chains = [longest_chain(tid) for tid in undone]
    if not all_chains:
        return []
    return max(all_chains, key=len)


def analyze(phase: dict, task_status: dict, blockers: list) -> dict:
    """核心分析：给出智能推进建议"""
    graph = build_dep_graph(phase)
    classified = classify_tasks(phase, task_status)
    critical_path = find_critical_path(phase, task_status)

    # 对 ready 任务按优先级排序
    for task in classified["ready"]:
        task["_priority"] = compute_priority(task, graph, task_status)
    classified["ready"].sort(key=lambda t: t.get("_priority", 0), reverse=True)

    # 分析阻塞影响
    blocked_impact = []
    active_blockers = [b for b in blockers if not b.get("resolved")]
    for b in active_blockers:
        tid = b["task_id"]
        downstream = _count_downstream(tid, graph["rdeps"], set())
        blocked_impact.append({
            "task_id": tid,
            "task_name": graph["tasks"].get(tid, {}).get("name", tid),
            "reason": b["reason"],
            "downstream_blocked": downstream,
        })
    blocked_impact.sort(key=lambda x: x["downstream_blocked"], reverse=True)

    # 找出被阻塞但可以绕过的工作
    bypass_suggestions = []
    for b in active_blockers:
        tid = b["task_id"]
        # 找同阶段中不依赖被阻塞任务的 ready 任务
        for task in classified["ready"]:
            if tid not in graph["deps"].get(task["id"], []):
                bypass_suggestions.append({
                    "blocked": tid,
                    "can_do": task["id"],
                    "can_do_name": task["name"],
                })

    # 并行建议：哪些 ready 任务可以同时推进
    parallel_groups = []
    if len(classified["ready"]) > 1:
        # 按 owner 分组
        by_owner = {}
        for t in classified["ready"]:
            owner = t.get("owner", "未指定")
            by_owner.setdefault(owner, []).append(t)
        parallel_groups = [
            {"owner": owner, "tasks": tasks}
            for owner, tasks in by_owner.items()
        ]

    return {
        "classified": classified,
        "critical_path": critical_path,
        "blocked_impact": blocked_impact,
        "bypass_suggestions": bypass_suggestions,
        "parallel_groups": parallel_groups,
        "phase_name": phase.get("name", ""),
    }


def format_advice(analysis: dict) -> str:
    """格式化输出智能建议"""
    lines = []
    c = analysis["classified"]
    cp = analysis["critical_path"]

    # 总览
    total = sum(len(v) for v in c.values())
    done = len(c["done"])
    lines.append(f"📊 {analysis['phase_name']}  {done}/{total} 完成\n")

    # 阻塞影响分析
    if analysis["blocked_impact"]:
        lines.append("🚨 阻塞影响分析:")
        for b in analysis["blocked_impact"]:
            lines.append(f"   {b['task_name']}: {b['reason']}")
            if b["downstream_blocked"] > 0:
                lines.append(f"   ⚠️  影响下游 {b['downstream_blocked']} 个任务")
        lines.append("")

        if analysis["bypass_suggestions"]:
            lines.append("💡 绕过阻塞，可以先做:")
            seen = set()
            for s in analysis["bypass_suggestions"]:
                if s["can_do"] not in seen:
                    seen.add(s["can_do"])
                    lines.append(f"   → [{s['can_do']}] {s['can_do_name']}")
            lines.append("")

    # 最优行动（按优先级排序的 ready 任务）
    if c["ready"]:
        lines.append("🎯 最优行动（按优先级）:")
        for i, t in enumerate(c["ready"], 1):
            pri = t.get("_priority", 0)
            reason = []
            if t.get("critical"):
                reason.append("关键节点")
            downstream = _count_downstream(t["id"], build_dep_graph({"tasks": list(build_dep_graph({"tasks": c["ready"] + c["waiting"] + c["in_progress"]})["tasks"].values())})["rdeps"], set()) if False else 0
            # 简化：直接用 priority 说明
            if pri >= 100:
                tag = "🔴 关键"
            elif pri >= 20:
                tag = "🟡 高优"
            else:
                tag = "🟢 可做"

            line = f"   {i}. {tag} [{t['id']}] {t['name']}"
            if t.get("owner"):
                line += f"  ← {t['owner']}"
            lines.append(line)
            if t.get("deliverables"):
                lines.append(f"      交付件: {', '.join(t['deliverables'])}")
            if t.get("gate"):
                lines.append(f"      ⚠️ 准入: {t['gate']}")
        lines.append("")

    # 并行建议
    if analysis["parallel_groups"] and len(analysis["parallel_groups"]) > 1:
        lines.append("⚡ 可并行推进:")
        for g in analysis["parallel_groups"]:
            task_names = [t["name"] for t in g["tasks"]]
            lines.append(f"   {g['owner']}: {', '.join(task_names)}")
        lines.append("")

    # 进行中
    if c["in_progress"]:
        lines.append("🔄 进行中:")
        for t in c["in_progress"]:
            lines.append(f"   [{t['id']}] {t['name']}")
        lines.append("")

    # 关键路径
    if cp and len(cp) > 1:
        lines.append(f"📐 关键路径 ({len(cp)} 步):")
        path_str = " → ".join(cp)
        lines.append(f"   {path_str}")
        lines.append("")

    # 等待中
    if c["waiting"]:
        lines.append(f"⏳ 等待依赖 ({len(c['waiting'])}):")
        for t in c["waiting"]:
            waiting_for = t.get("_waiting_for", [])
            lines.append(f"   [{t['id']}] {t['name']}  等待: {', '.join(waiting_for)}")
        lines.append("")

    return "\n".join(lines)
