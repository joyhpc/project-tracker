"""格式化输出 — 所有 print/display 逻辑集中在这里"""
from .engine import build_dep_graph, _count_downstream, classify_tasks, find_critical_path, analyze


def format_advice(analysis: dict) -> str:
    """格式化智能推进建议"""
    lines = []
    c = analysis["classified"]
    cp = analysis["critical_path"]

    total = sum(len(v) for v in c.values())
    done = len(c["done"])
    lines.append(f"📊 {analysis['phase_name']}  {done}/{total} 完成\n")

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

    if c["ready"]:
        lines.append("🎯 最优行动（按优先级）:")
        for i, t in enumerate(c["ready"], 1):
            pri = t.get("_priority", 0)
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

    if analysis["parallel_groups"] and len(analysis["parallel_groups"]) > 1:
        lines.append("⚡ 可并行推进:")
        for g in analysis["parallel_groups"]:
            task_names = [t["name"] for t in g["tasks"]]
            lines.append(f"   {g['owner']}: {', '.join(task_names)}")
        lines.append("")

    if c["in_progress"]:
        lines.append("🔄 进行中:")
        for t in c["in_progress"]:
            lines.append(f"   [{t['id']}] {t['name']}")
        lines.append("")

    if cp and len(cp) > 1:
        lines.append(f"📐 关键路径 ({len(cp)} 步):")
        lines.append(f"   {' → '.join(cp)}")
        lines.append("")

    if c["waiting"]:
        lines.append(f"⏳ 等待依赖 ({len(c['waiting'])}):")
        for t in c["waiting"]:
            waiting_for = t.get("_waiting_for", [])
            lines.append(f"   [{t['id']}] {t['name']}  等待: {', '.join(waiting_for)}")
        lines.append("")

    return "\n".join(lines)


def format_plan(flow: dict, current_phase: str, task_status: dict, blockers: list) -> str:
    """项目全局作战地图"""
    phases = flow.get("phases", [])
    phase_map = {p["id"]: p for p in phases}
    order = [p["id"] for p in phases]

    try:
        start_idx = order.index(current_phase)
    except ValueError:
        return f"❌ 未知阶段: {current_phase}"

    lines = []

    # 1. 全局进度
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

    for pid, ph, count, done in phase_summaries:
        pct = done / count if count else 0
        filled = int(pct * 10)
        bar = "█" * filled + "░" * (10 - filled) if count else "  "
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

    # 2. 关键路径
    lines.append("📐 剩余关键路径:\n")
    remaining = order[start_idx:]
    for pid in remaining:
        ph = phase_map[pid]
        cp = find_critical_path(ph, task_status)
        if cp:
            lines.append(f"  {ph['name']} ({len(cp)} 步): {' → '.join(cp)}")
        else:
            lines.append(f"  {ph['name']}: ✅ 无剩余关键任务")
    lines.append("")

    # 3. 高风险节点
    lines.append("⚠️ 高风险节点:\n")
    risk_items = []
    for pid in remaining:
        ph = phase_map[pid]
        graph = build_dep_graph(ph)
        for tid, task in graph["tasks"].items():
            if task_status.get(tid, {}).get("status") == "done":
                continue
            downstream = _count_downstream(tid, graph["rdeps"], set())
            score = 0
            reasons = []
            if task.get("critical"):
                score += 50
                reasons.append("关键节点")
            if downstream >= 3:
                score += downstream * 5
                reasons.append(f"阻塞下游{downstream}个任务")
            if task.get("gate"):
                score += 10
                reasons.append(f"准入: {task['gate']}")
            if score > 0:
                risk_items.append((score, ph["name"], task, reasons))

    risk_items.sort(key=lambda x: x[0], reverse=True)
    for _, pname, task, reasons in risk_items[:10]:
        lines.append(f"  🔴 [{task['id']}] {task['name']}  ({pname})")
        lines.append(f"     {'; '.join(reasons)}")
    if not risk_items:
        lines.append("  无高风险节点")
    lines.append("")

    # 4. 提前准备
    lines.append("🕐 需要提前准备:\n")
    early_kw = ["申请", "审批", "送样", "制样", "采购", "知识产权", "新品承认"]
    seen = set()
    for pid in remaining:
        ph = phase_map[pid]
        for task in ph.get("tasks", []):
            if task_status.get(task["id"], {}).get("status") == "done" or task["id"] in seen:
                continue
            need = task.get("gate") or any(kw in task["name"] for kw in early_kw)
            if need:
                seen.add(task["id"])
                line = f"  📌 [{task['id']}] {task['name']}  ({ph['name']})"
                if task.get("gate"):
                    line += f"\n     准入: {task['gate']}"
                lines.append(line)
    if not seen:
        lines.append("  无特殊提前准备项")
    lines.append("")

    # 5. 人力分布
    lines.append("👥 人力负载:\n")
    owner_load = {}
    for pid in remaining:
        ph = phase_map[pid]
        for task in ph.get("tasks", []):
            if task_status.get(task["id"], {}).get("status") == "done":
                continue
            for o in task.get("owner", "未指定").replace("/", ",").replace("、", ",").split(","):
                o = o.strip()
                if o:
                    owner_load.setdefault(o, []).append((ph["name"], task["name"]))

    for owner, tasks in sorted(owner_load.items(), key=lambda x: len(x[1]), reverse=True)[:8]:
        lines.append(f"  {owner}: {len(tasks)} 个待办")
        for pname, tname in tasks[:3]:
            lines.append(f"    - {tname} ({pname})")
        if len(tasks) > 3:
            lines.append(f"    ... 还有 {len(tasks)-3} 个")
    lines.append("")

    # 6. 当前行动
    current = phase_map[current_phase]
    result = analyze(current, task_status, blockers)
    lines.append("🎯 当前阶段行动:\n")
    lines.append(format_advice(result))

    return "\n".join(lines)
