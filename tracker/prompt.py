"""Prompt 导出引擎

根据用户问题 + 项目当前状态，生成带完整上下文的 prompt。
让 LLM 能基于真实项目数据给出精准建议。
"""
from . import core, flow as flowmod
from .engine import analyze, find_critical_path, build_dep_graph, classify_tasks, _count_downstream
from .timeline import compute_full_schedule, estimate_task_days
from .risk import assess_project_risk


def gather_project_context(project: dict, flow: dict) -> dict:
    """收集项目的完整上下文数据"""
    task_status = project.get("tasks", {})
    blockers = project.get("blockers", [])
    current_phase_id = project["current_phase"]
    phases = flow.get("phases", [])
    phase_map = {p["id"]: p for p in phases}
    order = [p["id"] for p in phases]
    current_phase = phase_map.get(current_phase_id, {})

    # 基本信息
    total_tasks = sum(len(p.get("tasks", [])) for p in phases)
    total_done = sum(
        1 for p in phases
        for t in p.get("tasks", [])
        if task_status.get(t["id"], {}).get("status") == "done"
    )

    # 当前阶段分析
    classified = classify_tasks(current_phase, task_status)
    cp = find_critical_path(current_phase, task_status)
    active_blockers = [b for b in blockers if not b.get("resolved")]

    # 阻塞影响
    graph = build_dep_graph(current_phase)
    blocker_details = []
    for b in active_blockers:
        tid = b["task_id"]
        downstream = _count_downstream(tid, graph["rdeps"], set())
        blocker_details.append({
            "task": tid,
            "name": graph["tasks"].get(tid, {}).get("name", tid),
            "reason": b["reason"],
            "downstream": downstream,
        })

    # 进行中任务
    in_progress = []
    for t in classified.get("in_progress", []):
        entry = task_status.get(t["id"], {})
        in_progress.append({
            "id": t["id"], "name": t["name"],
            "owner": t.get("owner", ""),
            "started": entry.get("started", ""),
        })

    # Ready 任务
    ready = [{"id": t["id"], "name": t["name"], "owner": t.get("owner", "")}
             for t in classified.get("ready", [])]

    # 风险概要
    risk = assess_project_risk(flow, current_phase_id, task_status,
                               project.get("estimates", {}))
    top_risks = [{"name": r["name"], "score": r["score"], "factors": r["factors"]}
                 for r in risk.get("top_risks", [])[:5]]

    # 时间线概要
    sched = compute_full_schedule(flow, current_phase_id, task_status,
                                  custom_estimates=project.get("estimates", {}))

    # 阶段进度
    phase_progress = []
    for p in phases:
        pid = p["id"]
        tasks = p.get("tasks", [])
        done = sum(1 for t in tasks if task_status.get(t["id"], {}).get("status") == "done")
        phase_progress.append(f"{pid}({p['name']}): {done}/{len(tasks)}")

    return {
        "project_name": project["name"],
        "project_id": project["id"],
        "flow_name": project.get("flow", "duxin"),
        "current_phase": f"{current_phase_id} ({current_phase.get('name', '')})",
        "global_progress": f"{total_done}/{total_tasks}",
        "phase_progress": phase_progress,
        "critical_path": cp,
        "blockers": blocker_details,
        "in_progress": in_progress,
        "ready_tasks": ready,
        "top_risks": top_risks,
        "total_days": sched.get("total_days", 0),
        "end_date": sched.get("end_date", None),
        "bottlenecks": risk.get("bottlenecks", []),
    }


def format_context_block(ctx: dict) -> str:
    """将项目上下文格式化为 prompt 可用的文本块"""
    lines = []

    lines.append(f"## 项目: {ctx['project_name']} ({ctx['project_id']})")
    lines.append(f"- 流程: {ctx['flow_name']}")
    lines.append(f"- 当前阶段: {ctx['current_phase']}")
    lines.append(f"- 全局进度: {ctx['global_progress']}")
    lines.append(f"- 预计剩余工期: {ctx['total_days']} 天")
    if ctx.get("end_date"):
        lines.append(f"- 预计完成: {ctx['end_date'].strftime('%Y-%m-%d')}")
    lines.append("")

    # 阶段进度
    lines.append("### 各阶段进度")
    for pp in ctx["phase_progress"]:
        lines.append(f"- {pp}")
    lines.append("")

    # 关键路径
    if ctx["critical_path"]:
        lines.append(f"### 当前阶段关键路径")
        lines.append(f"{' → '.join(ctx['critical_path'])}")
        lines.append("")

    # 阻塞
    if ctx["blockers"]:
        lines.append("### 当前阻塞")
        for b in ctx["blockers"]:
            lines.append(f"- [{b['task']}] {b['name']}: {b['reason']} (影响下游 {b['downstream']} 个任务)")
        lines.append("")

    # 进行中
    if ctx["in_progress"]:
        lines.append("### 进行中的任务")
        for t in ctx["in_progress"]:
            lines.append(f"- [{t['id']}] {t['name']} ← {t['owner']} (开始于 {t['started']})")
        lines.append("")

    # 可启动
    if ctx["ready_tasks"]:
        lines.append("### 可立即启动的任务")
        for t in ctx["ready_tasks"]:
            lines.append(f"- [{t['id']}] {t['name']} ← {t['owner']}")
        lines.append("")

    # 风险
    if ctx["top_risks"]:
        lines.append("### Top 风险")
        for r in ctx["top_risks"]:
            lines.append(f"- {r['name']} (风险分: {r['score']}): {'; '.join(r['factors'])}")
        lines.append("")

    # 资源瓶颈
    if ctx["bottlenecks"]:
        lines.append("### 资源瓶颈")
        for owner, count in ctx["bottlenecks"][:3]:
            lines.append(f"- {owner}: {count} 个待办任务")
        lines.append("")

    return "\n".join(lines)


# ── Prompt 模板 ──────────────────────────────────────

PROMPT_TEMPLATES = {
    "accelerate": {
        "label": "如何最快推进项目",
        "system": "你是一位资深硬件项目管理专家，擅长识别项目瓶颈并给出可执行的加速方案。",
        "template": """基于以下项目状态，分析如何最快推进项目。

{context}

请回答：
1. 当前最大的瓶颈是什么？
2. 哪些任务可以并行推进来缩短工期？
3. 阻塞问题的具体解决建议？
4. 资源如何优化分配？
5. 给出一个具体的未来两周行动计划。""",
    },

    "architecture": {
        "label": "架构是否合理",
        "system": "你是一位资深电子产品系统架构师，擅长评估硬件/软件/结构的架构合理性。",
        "template": """基于以下项目状态，评估当前项目架构和流程是否合理。

{context}

请回答：
1. 当前的任务依赖关系是否合理？有没有不必要的串行依赖？
2. 关键路径是否可以优化？
3. 风险最高的环节是否有足够的缓冲？
4. 资源分配是否均衡？
5. 有没有遗漏的关键任务或评审节点？""",
    },

    "risk": {
        "label": "风险分析与缓解",
        "system": "你是一位硬件项目风险管理专家，擅长识别潜在风险并制定缓解方案。",
        "template": """基于以下项目状态，进行深度风险分析。

{context}

请回答：
1. 最可能导致项目延期的 3 个风险是什么？
2. 每个风险的缓解方案？
3. 需要提前准备什么来降低风险？
4. 如果最坏情况发生，应急方案是什么？""",
    },

    "status": {
        "label": "项目状态汇报",
        "system": "你是一位项目管理助手，擅长将复杂的项目数据整理成清晰的汇报材料。",
        "template": """基于以下项目数据，生成一份简洁的项目状态汇报（适合给领导看）。

{context}

要求：
1. 一句话总结当前状态
2. 关键进展（已完成的重要事项）
3. 当前风险和阻塞
4. 下一步计划
5. 需要协调的资源或决策""",
    },

    "custom": {
        "label": "自定义问题",
        "system": "你是一位资深硬件项目管理专家。基于提供的项目数据回答问题。",
        "template": """以下是项目的当前状态：

{context}

用户问题：{question}""",
    },
}


def generate_prompt(question: str, project: dict = None, flow: dict = None) -> dict:
    """根据问题和项目状态生成完整 prompt

    Returns:
        {
            "system": str,
            "prompt": str,
            "template_used": str,
            "context_summary": str,
        }
    """
    # 自动匹配模板
    template_key = match_template(question)

    template = PROMPT_TEMPLATES[template_key]

    # 收集上下文
    if project and flow:
        ctx = gather_project_context(project, flow)
        context_block = format_context_block(ctx)
        context_summary = f"项目: {ctx['project_name']} | 阶段: {ctx['current_phase']} | 进度: {ctx['global_progress']}"
    else:
        context_block = "(无活跃项目)"
        context_summary = "无项目上下文"

    # 生成 prompt
    prompt = template["template"].format(
        context=context_block,
        question=question,
    )

    return {
        "system": template["system"],
        "prompt": prompt,
        "template_used": template_key,
        "template_label": template["label"],
        "context_summary": context_summary,
    }


def match_template(question: str) -> str:
    """根据问题内容匹配最合适的模板"""
    q = question.lower()

    accelerate_kw = ["快", "加速", "推进", "缩短", "提速", "赶", "工期", "进度", "瓶颈",
                     "accelerate", "speed", "faster", "bottleneck"]
    arch_kw = ["架构", "合理", "设计", "依赖", "结构", "方案", "architecture", "design"]
    risk_kw = ["风险", "延期", "问题", "隐患", "risk", "delay", "issue"]
    status_kw = ["汇报", "报告", "总结", "状态", "report", "status", "summary"]

    for kw in accelerate_kw:
        if kw in q:
            return "accelerate"
    for kw in arch_kw:
        if kw in q:
            return "architecture"
    for kw in risk_kw:
        if kw in q:
            return "risk"
    for kw in status_kw:
        if kw in q:
            return "status"

    return "custom"


def list_templates() -> list[dict]:
    """列出所有可用模板"""
    return [{"key": k, "label": v["label"]} for k, v in PROMPT_TEMPLATES.items()]
