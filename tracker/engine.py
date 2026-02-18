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


# ── 通知摘要 ──────────────────────────────────────────

def generate_digest(project: dict, flow: dict) -> dict:
    """生成项目状态摘要，用于通知推送。
    
    返回:
        {
            "has_alerts": bool,      # 是否有需要关注的事项
            "text": str,             # 格式化的摘要文本
            "alerts": list[str],     # 告警列表
            "summary": dict,         # 数据摘要
        }
    """
    phase_map = {p["id"]: p for p in flow.get("phases", [])}
    order = [p["id"] for p in flow.get("phases", [])]
    current_phase = project["current_phase"]
    task_status = project.get("tasks", {})
    blockers = project.get("blockers", [])
    phase = phase_map.get(current_phase, {})

    alerts = []
    
    # 1. 活跃阻塞
    active_blockers = [b for b in blockers if not b.get("resolved")]
    for b in active_blockers:
        tid = b["task_id"]
        tname = ""
        for t in phase.get("tasks", []):
            if t["id"] == tid:
                tname = t["name"]
                break
        graph = build_dep_graph(phase)
        downstream = _count_downstream(tid, graph["rdeps"], set())
        alert = f"🚫 [{tid}] {tname} 被阻塞: {b['reason']}"
        if downstream > 0:
            alert += f" (影响下游 {downstream} 个任务)"
        alerts.append(alert)

    # 2. 阶段完成度
    tasks = phase.get("tasks", [])
    done_count = sum(1 for t in tasks if task_status.get(t["id"], {}).get("status") == "done")
    total = len(tasks)
    progress_pct = (done_count / total * 100) if total > 0 else 0

    # 3. 进行中但可能停滞的任务（有 started 但超过一定时间没动静）
    from datetime import datetime, timedelta
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

    # 4. 子任务中的阻塞
    for tid, entry in task_status.items():
        subs = entry.get("subtasks", {})
        for sid, sub in subs.items():
            if sub.get("status") == "blocked":
                alerts.append(f"🚫 子任务 [{tid}.{sid}] {sub['name']} 阻塞: {sub.get('blocked_reason', '未知')}")

    # 5. 可以立即开始的任务（提醒推进）
    classified = classify_tasks(phase, task_status)
    ready_tasks = classified["ready"]

    # 构建摘要文本
    lines = []
    lines.append(f"📋 {project['name']} ({project['id']})")
    lines.append(f"📍 {phase.get('name', '')} — {done_count}/{total} ({progress_pct:.0f}%)")
    lines.append("")

    if alerts:
        lines.append("⚠️ 需要关注:")
        for a in alerts:
            lines.append(f"  {a}")
        lines.append("")

    if ready_tasks:
        lines.append(f"🎯 可立即推进 ({len(ready_tasks)}):")
        for t in ready_tasks[:5]:
            owner = t.get("owner", "")
            lines.append(f"  → [{t['id']}] {t['name']}  ← {owner}")
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
            "phase": current_phase,
            "progress": f"{done_count}/{total}",
            "blockers": len(active_blockers),
            "stale": len(stale_tasks),
            "ready": len(ready_tasks),
        },
    }

def plan_project(flow: dict, current_phase: str, task_status: dict, blockers: list) -> str:
    """项目全局作战地图：从当前阶段到结束的完整分析"""
    phases = [p for p in flow.get("phases", [])]
    phase_map = {p["id"]: p for p in phases}
    order = [p["id"] for p in phases]

    try:
        start_idx = order.index(current_phase)
    except ValueError:
        return f"❌ 未知阶段: {current_phase}"

    lines = []

    # ── 1. 全局进度总览 ──
    total_tasks = 0
    total_done = 0
    phase_summaries = []
    for pid in order:
        ph = phase_map[pid]
        tasks = ph.get("tasks", [])
        done = sum(1 for t in tasks if task_status.get(t["id"], {}).get("status") == "done")
        total_tasks += len(tasks)
        total_done += done
        phase_summaries.append((pid, ph, len(tasks), done))

    lines.append(f"📊 全局进度: {total_done}/{total_tasks} 任务完成\n")

    # 阶段进度条
    for pid, ph, count, done in phase_summaries:
        if count == 0:
            bar = "  "
        else:
            pct = done / count
            filled = int(pct * 10)
            bar = "█" * filled + "░" * (10 - filled)

        marker = " ◀" if pid == current_phase else ""
        ms = f" [{ph.get('milestone')}]" if ph.get("milestone") else ""
        status_tag = ""
        idx = order.index(pid)
        if idx < start_idx:
            status_tag = " ✅"
        elif done == count and count > 0:
            status_tag = " ✅"

        lines.append(f"  {bar} {pid:8s} {ph['name']}{ms}{status_tag}{marker}  ({done}/{count})")
    lines.append("")

    # ── 2. 剩余阶段关键路径 ──
    lines.append("📐 剩余关键路径:\n")
    remaining_phases = order[start_idx:]
    for pid in remaining_phases:
        ph = phase_map[pid]
        cp = find_critical_path(ph, task_status)
        if cp:
            lines.append(f"  {ph['name']} ({len(cp)} 步关键链):")
            lines.append(f"    {' → '.join(cp)}")
        else:
            lines.append(f"  {ph['name']}: ✅ 无剩余关键任务")
    lines.append("")

    # ── 3. 高风险节点（跨所有剩余阶段）──
    lines.append("⚠️ 高风险节点（需要重点盯的）:\n")
    risk_items = []
    for pid in remaining_phases:
        ph = phase_map[pid]
        graph = build_dep_graph(ph)
        for tid, task in graph["tasks"].items():
            if task_status.get(tid, {}).get("status") == "done":
                continue
            downstream = _count_downstream(tid, graph["rdeps"], set())
            is_critical = task.get("critical", False)
            has_gate = bool(task.get("gate"))
            risk_score = 0
            reasons = []
            if is_critical:
                risk_score += 50
                reasons.append("关键节点")
            if downstream >= 3:
                risk_score += downstream * 5
                reasons.append(f"阻塞下游{downstream}个任务")
            if has_gate:
                risk_score += 10
                reasons.append(f"准入: {task['gate']}")
            if risk_score > 0:
                risk_items.append((risk_score, ph["name"], task, reasons))

    risk_items.sort(key=lambda x: x[0], reverse=True)
    for score, phase_name, task, reasons in risk_items[:10]:
        lines.append(f"  🔴 [{task['id']}] {task['name']}  ({phase_name})")
        lines.append(f"     {'; '.join(reasons)}")
    if not risk_items:
        lines.append("  无高风险节点")
    lines.append("")

    # ── 4. 长周期预警（需要提前准备的）──
    lines.append("🕐 需要提前准备的事项:\n")
    early_items = []
    for pid in remaining_phases:
        ph = phase_map[pid]
        for task in ph.get("tasks", []):
            if task_status.get(task["id"], {}).get("status") == "done":
                continue
            # 有 gate 的任务通常需要提前准备
            if task.get("gate"):
                early_items.append((pid, ph["name"], task))
            # 涉及外部依赖的关键词
            name_lower = task["name"].lower()
            for kw in ["申请", "审批", "送样", "制样", "采购", "知识产权", "新品承认"]:
                if kw in task["name"]:
                    early_items.append((pid, ph["name"], task))
                    break

    seen = set()
    for pid, pname, task in early_items:
        if task["id"] in seen:
            continue
        seen.add(task["id"])
        line = f"  📌 [{task['id']}] {task['name']}  ({pname})"
        if task.get("gate"):
            line += f"\n     准入: {task['gate']}"
        lines.append(line)
    if not seen:
        lines.append("  无特殊提前准备项")
    lines.append("")

    # ── 5. 人力分布（谁最忙）──
    lines.append("👥 人力负载分布:\n")
    owner_load = {}
    for pid in remaining_phases:
        ph = phase_map[pid]
        for task in ph.get("tasks", []):
            if task_status.get(task["id"], {}).get("status") == "done":
                continue
            owner = task.get("owner", "未指定")
            # 拆分多人
            for o in owner.replace("/", ",").replace("、", ",").split(","):
                o = o.strip()
                if o:
                    owner_load.setdefault(o, []).append((ph["name"], task["name"]))

    sorted_owners = sorted(owner_load.items(), key=lambda x: len(x[1]), reverse=True)
    for owner, tasks in sorted_owners[:8]:
        lines.append(f"  {owner}: {len(tasks)} 个待办")
        # 显示前3个
        for pname, tname in tasks[:3]:
            lines.append(f"    - {tname} ({pname})")
        if len(tasks) > 3:
            lines.append(f"    ... 还有 {len(tasks)-3} 个")
    lines.append("")

    # ── 6. 当前阶段行动建议 ──
    current = phase_map[current_phase]
    result = analyze(current, task_status, blockers)
    lines.append(f"🎯 当前阶段行动:\n")
    lines.append(format_advice(result))

    return "\n".join(lines)
