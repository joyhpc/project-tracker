"""智能推进引擎 — 纯分析逻辑，无格式化"""
from datetime import datetime


def build_dep_graph(phase: dict) -> dict:
    """构建任务依赖图"""
    tasks = {t["id"]: t for t in phase.get("tasks", [])}
    deps = {tid: t.get("depends", []) for tid, t in tasks.items()}
    rdeps = {tid: [] for tid in tasks}
    for tid, dep_list in deps.items():
        for d in dep_list:
            if d in rdeps:
                rdeps[d].append(tid)
    return {"tasks": tasks, "deps": deps, "rdeps": rdeps}


def classify_tasks(phase: dict, task_status: dict) -> dict:
    """分类任务状态: ready/in_progress/blocked/waiting/done"""
    graph = build_dep_graph(phase)
    tasks = graph["tasks"]
    deps = graph["deps"]

    result = {"ready": [], "in_progress": [], "blocked": [], "waiting": [], "done": []}

    for tid, task in tasks.items():
        s = task_status.get(tid, {}).get("status", "pending")
        if s == "done":
            result["done"].append(task)
        elif s == "blocked":
            result["blocked"].append(task)
        elif s == "in_progress":
            result["in_progress"].append(task)
        else:
            dep_ids = deps.get(tid, [])
            all_done = all(task_status.get(d, {}).get("status") == "done" for d in dep_ids)
            if all_done:
                result["ready"].append(task)
            else:
                task["_waiting_for"] = [d for d in dep_ids if task_status.get(d, {}).get("status") != "done"]
                result["waiting"].append(task)

    return result


def _count_downstream(tid: str, rdeps: dict, visited: set) -> int:
    """递归计算下游任务总数"""
    count = 0
    for child in rdeps.get(tid, []):
        if child not in visited:
            visited.add(child)
            count += 1 + _count_downstream(child, rdeps, visited)
    return count


def compute_priority(task: dict, graph: dict, task_status: dict) -> int:
    """计算任务优先级"""
    score = 0
    if task.get("critical"):
        score += 100
    score += _count_downstream(task["id"], graph["rdeps"], set()) * 10
    if task.get("gate"):
        score += 5
    if task.get("deliverables"):
        score += 3
    return score


def find_critical_path(phase: dict, task_status: dict) -> list[str]:
    """找到关键路径（最长依赖链）"""
    graph = build_dep_graph(phase)
    tasks = graph["tasks"]
    deps = graph["deps"]
    undone = {tid for tid in tasks if task_status.get(tid, {}).get("status") != "done"}

    memo = {}
    def longest_chain(tid):
        if tid in memo:
            return memo[tid]
        if tid not in undone:
            return []
        dep_chains = [longest_chain(d) for d in deps.get(tid, []) if d in undone]
        best = max(dep_chains, key=len) if dep_chains else []
        result = best + [tid]
        memo[tid] = result
        return result

    all_chains = [longest_chain(tid) for tid in undone]
    if not all_chains:
        return []
    max_len = max(len(c) for c in all_chains)
    # 同长度时优先选包含 critical 任务的链
    candidates = [c for c in all_chains if len(c) == max_len]
    for c in candidates:
        if any(tasks.get(tid, {}).get("critical") for tid in c):
            return c
    return candidates[0]


def analyze(phase: dict, task_status: dict, blockers: list) -> dict:
    """核心分析：返回结构化数据"""
    graph = build_dep_graph(phase)
    classified = classify_tasks(phase, task_status)
    critical_path = find_critical_path(phase, task_status)

    for task in classified["ready"]:
        task["_priority"] = compute_priority(task, graph, task_status)
    classified["ready"].sort(key=lambda t: t.get("_priority", 0), reverse=True)

    active_blockers = [b for b in blockers if not b.get("resolved")]
    blocked_impact = []
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

    bypass_suggestions = []
    for b in active_blockers:
        tid = b["task_id"]
        for task in classified["ready"]:
            if tid not in graph["deps"].get(task["id"], []):
                bypass_suggestions.append({
                    "blocked": tid, "can_do": task["id"], "can_do_name": task["name"],
                })

    parallel_groups = []
    if len(classified["ready"]) > 1:
        by_owner = {}
        for t in classified["ready"]:
            by_owner.setdefault(t.get("owner", "未指定"), []).append(t)
        parallel_groups = [{"owner": o, "tasks": ts} for o, ts in by_owner.items()]

    return {
        "classified": classified,
        "critical_path": critical_path,
        "blocked_impact": blocked_impact,
        "bypass_suggestions": bypass_suggestions,
        "parallel_groups": parallel_groups,
        "phase_name": phase.get("name", ""),
    }


def generate_digest(project: dict, flow: dict) -> dict:
    """生成项目状态摘要数据"""
    phase_map = {p["id"]: p for p in flow.get("phases", [])}
    current_phase = project["current_phase"]
    task_status = project.get("tasks", {})
    blockers = project.get("blockers", [])
    phase = phase_map.get(current_phase, {})

    alerts = []
    active_blockers = [b for b in blockers if not b.get("resolved")]

    # 阻塞告警
    for b in active_blockers:
        tid = b["task_id"]
        tname = next((t["name"] for t in phase.get("tasks", []) if t["id"] == tid), tid)
        graph = build_dep_graph(phase)
        downstream = _count_downstream(tid, graph["rdeps"], set())
        alert = f"🚫 [{tid}] {tname} 被阻塞: {b['reason']}"
        if downstream > 0:
            alert += f" (影响下游 {downstream} 个任务)"
        alerts.append(alert)

    # 停滞告警
    tasks = phase.get("tasks", [])
    done_count = sum(1 for t in tasks if task_status.get(t["id"], {}).get("status") == "done")
    total = len(tasks)
    progress_pct = (done_count / total * 100) if total > 0 else 0

    stale_tasks = []
    now = datetime.now()
    for t in tasks:
        entry = task_status.get(t["id"], {})
        if entry.get("status") == "in_progress" and entry.get("started"):
            try:
                started = datetime.strptime(entry["started"], "%Y-%m-%d %H:%M")
                days = (now - started).days
                if days >= 3:
                    stale_tasks.append((t, days))
            except (ValueError, TypeError):
                pass

    for t, days in stale_tasks:
        alerts.append(f"⏰ [{t['id']}] {t['name']} 已进行 {days} 天未完成")

    # 子任务阻塞
    for tid, entry in task_status.items():
        for sid, sub in entry.get("subtasks", {}).items():
            if sub.get("status") == "blocked":
                alerts.append(f"🚫 子任务 [{tid}.{sid}] {sub['name']} 阻塞: {sub.get('blocked_reason', '未知')}")

    classified = classify_tasks(phase, task_status)
    ready_tasks = classified["ready"]

    # 摘要文本
    lines = [f"📋 {project['name']} ({project['id']})",
             f"📍 {phase.get('name', '')} — {done_count}/{total} ({progress_pct:.0f}%)", ""]
    if alerts:
        lines.append("⚠️ 需要关注:")
        lines.extend(f"  {a}" for a in alerts)
        lines.append("")
    if ready_tasks:
        lines.append(f"🎯 可立即推进 ({len(ready_tasks)}):")
        for t in ready_tasks[:5]:
            lines.append(f"  → [{t['id']}] {t['name']}  ← {t.get('owner', '')}")
        if len(ready_tasks) > 5:
            lines.append(f"  ... 还有 {len(ready_tasks)-5} 个")
        lines.append("")
    if not alerts and not ready_tasks:
        lines.append("✅ 一切正常，无需关注")

    return {
        "has_alerts": len(alerts) > 0,
        "text": "\n".join(lines),
        "alerts": alerts,
        "summary": {
            "phase": current_phase, "progress": f"{done_count}/{total}",
            "blockers": len(active_blockers), "stale": len(stale_tasks), "ready": len(ready_tasks),
        },
    }
