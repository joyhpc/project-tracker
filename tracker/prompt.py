"""Prompt 导出引擎

根据用户问题，从项目中提取恰好需要的上下文，生成精准 prompt。
原则：不多不少，只给 LLM 回答这个问题所需的信息。
"""
from . import core, flow as flowmod
from .engine import find_critical_path, build_dep_graph, classify_tasks, _count_downstream
from .timeline import compute_full_schedule, estimate_task_days
from .risk import assess_project_risk


# ── 上下文收集器（按需） ──────────────────────────────

def _find_task_in_flow(flow, task_id):
    """在流程中查找任务，返回 (phase, task) 或 (None, None)"""
    for phase in flow.get("phases", []):
        for t in phase.get("tasks", []):
            if t["id"] == task_id:
                return phase, t
    return None, None


def _find_task_by_name(flow, name):
    """按名称模糊匹配任务"""
    name_lower = name.lower()
    for phase in flow.get("phases", []):
        for t in phase.get("tasks", []):
            if name_lower in t["name"].lower() or name_lower in t["id"].lower():
                return phase, t
    return None, None


def _task_detail(task, phase, task_status, blockers, graph):
    """收集单个任务的详细信息"""
    tid = task["id"]
    entry = task_status.get(tid, {})
    status = entry.get("status", "pending")

    info = {
        "id": tid,
        "name": task["name"],
        "phase": phase.get("name", ""),
        "owner": task.get("owner", ""),
        "status": status,
        "depends": task.get("depends", []),
        "deliverables": task.get("deliverables", []),
    }

    if task.get("gate"):
        info["gate"] = task["gate"]
    if task.get("critical"):
        info["critical"] = True
    if entry.get("started"):
        info["started"] = entry["started"]

    # 阻塞信息
    active_blockers = [b for b in blockers if b["task_id"] == tid and not b.get("resolved")]
    if active_blockers:
        info["blocked_reason"] = active_blockers[0]["reason"]

    # 下游影响
    if graph:
        downstream = _count_downstream(tid, graph["rdeps"], set())
        if downstream > 0:
            info["downstream_count"] = downstream
            # 直接下游任务名
            direct = []
            for other_id, other_task in graph["tasks"].items():
                if tid in other_task.get("depends", []):
                    direct.append(f"{other_task['name']}({other_id})")
            if direct:
                info["direct_downstream"] = direct

    # 上游依赖状态
    if info["depends"]:
        dep_status = []
        for d in info["depends"]:
            ds = task_status.get(d, {}).get("status", "pending")
            dep_status.append(f"{d}={ds}")
        info["dep_status"] = dep_status

    return info


def _format_task_detail(info):
    """格式化单个任务详情"""
    lines = []
    status_map = {"done": "✅已完成", "in_progress": "🔄进行中", "pending": "⏳待开始", "blocked": "🚫已阻塞"}
    lines.append(f"[{info['id']}] {info['name']}")
    lines.append(f"  状态: {status_map.get(info['status'], info['status'])}")
    if info.get("owner"):
        lines.append(f"  负责人: {info['owner']}")
    if info.get("phase"):
        lines.append(f"  所属阶段: {info['phase']}")
    if info.get("blocked_reason"):
        lines.append(f"  ⚠️ 阻塞原因: {info['blocked_reason']}")
    if info.get("depends"):
        lines.append(f"  依赖: {', '.join(info['depends'])}")
    if info.get("dep_status"):
        lines.append(f"  依赖状态: {', '.join(info['dep_status'])}")
    if info.get("direct_downstream"):
        lines.append(f"  直接下游: {', '.join(info['direct_downstream'])}")
    if info.get("downstream_count"):
        lines.append(f"  影响下游: {info['downstream_count']} 个任务")
    if info.get("gate"):
        lines.append(f"  准入条件: {info['gate']}")
    if info.get("deliverables"):
        lines.append(f"  交付件: {', '.join(info['deliverables'])}")
    if info.get("critical"):
        lines.append(f"  🔴 关键路径任务")
    return "\n".join(lines)


# ── 问题分析 ──────────────────────────────────────────

def extract_task_refs(question, flow):
    """从问题中提取涉及的任务"""
    refs = []
    for phase in flow.get("phases", []):
        for t in phase.get("tasks", []):
            # 匹配 task_id 或任务名
            if t["id"] in question or t["name"] in question:
                refs.append(t["id"])
    return refs


def analyze_question(question):
    """分析问题的意图，决定需要哪些上下文。
    优先级：具体任务问题 > 全局问题。避免叠加过多上下文。"""
    q = question.lower()

    needs = set()
    primary = None  # 主要意图

    # 阻塞相关（最具体）
    block_kw = ["阻塞", "block", "卡住", "等待", "停滞", "替代", "绕过", "先做"]
    if any(kw in q for kw in block_kw):
        needs.update(["target_task", "blockers", "alternatives"])
        primary = "blocked"

    # 加速/推进（全局性）
    accel_kw = ["快", "加速", "推进", "缩短", "提速", "赶", "工期", "瓶颈"]
    if any(kw in q for kw in accel_kw):
        if primary != "blocked":  # 已有具体意图时不叠加全局
            needs.update(["critical_path", "ready_tasks", "blockers", "bottlenecks"])
            primary = primary or "accelerate"

    # 架构/设计
    arch_kw = ["架构", "合理", "依赖", "流程"]
    if any(kw in q for kw in arch_kw):
        needs.update(["phase_overview", "critical_path", "dependencies"])
        primary = primary or "architecture"

    # 风险
    risk_kw = ["风险", "延期", "隐患"]
    if any(kw in q for kw in risk_kw):
        needs.update(["risks", "critical_path"])
        primary = primary or "risk"

    # 状态/汇报
    status_kw = ["汇报", "报告", "总结", "状态"]
    if any(kw in q for kw in status_kw):
        needs.update(["phase_overview", "progress", "blockers", "ready_tasks"])
        primary = primary or "status"

    # 如果没匹配到任何意图，给基本上下文
    if not needs:
        needs.update(["progress", "current_phase"])

    return needs


# ── 精准上下文构建 ──────────────────────────────────────

def build_focused_context(question, project, flow):
    """根据问题构建精准上下文"""
    task_status = project.get("tasks", {})
    blockers = project.get("blockers", [])
    current_phase_id = project["current_phase"]
    phases = flow.get("phases", [])
    phase_map = {p["id"]: p for p in phases}
    current_phase = phase_map.get(current_phase_id, {})
    graph = build_dep_graph(current_phase)

    needs = analyze_question(question)
    task_refs = extract_task_refs(question, flow)

    lines = []

    # 始终给项目基本信息（一行）
    total = sum(len(p.get("tasks", [])) for p in phases)
    done = sum(1 for p in phases for t in p.get("tasks", [])
               if task_status.get(t["id"], {}).get("status") == "done")
    lines.append(f"项目: {project['name']} | 当前阶段: {current_phase.get('name', current_phase_id)} | 进度: {done}/{total}")
    lines.append("")

    # 目标任务详情
    if task_refs:
        lines.append("## 相关任务")
        for tid in task_refs:
            phase, task = _find_task_in_flow(flow, tid)
            if task:
                detail = _task_detail(task, phase, task_status, blockers, graph)
                lines.append(_format_task_detail(detail))
                lines.append("")

    # 阻塞 + 替代方案
    if "blockers" in needs or "alternatives" in needs:
        active_blockers = [b for b in blockers if not b.get("resolved")]
        if active_blockers:
            if not task_refs:  # 如果没有指定任务，列出所有阻塞
                lines.append("## 当前阻塞")
                for b in active_blockers:
                    phase_t, task_t = _find_task_in_flow(flow, b["task_id"])
                    if task_t:
                        detail = _task_detail(task_t, phase_t, task_status, blockers, graph)
                        lines.append(_format_task_detail(detail))
                        lines.append("")

        if "alternatives" in needs:
            classified = classify_tasks(current_phase, task_status)
            ready = classified.get("ready", [])
            if ready:
                lines.append("## 不受阻塞影响、可立即推进的任务")
                for t in ready:
                    blocked_ids = {b["task_id"] for b in active_blockers}
                    if t["id"] not in blocked_ids:
                        lines.append(f"- [{t['id']}] {t['name']} ← {t.get('owner', '未分配')}")
                lines.append("")

    # 关键路径
    if "critical_path" in needs:
        cp = find_critical_path(current_phase, task_status)
        if cp:
            lines.append(f"## 当前阶段关键路径")
            lines.append(f"{' → '.join(cp)}")
            lines.append("")

    # 可启动任务
    if "ready_tasks" in needs and "alternatives" not in needs:
        classified = classify_tasks(current_phase, task_status)
        ready = classified.get("ready", [])
        if ready:
            lines.append("## 可立即启动的任务")
            for t in ready:
                lines.append(f"- [{t['id']}] {t['name']} ← {t.get('owner', '未分配')}")
            lines.append("")

    # 阶段概览
    if "phase_overview" in needs:
        lines.append("## 各阶段进度")
        for p in phases:
            pid = p["id"]
            tasks = p.get("tasks", [])
            d = sum(1 for t in tasks if task_status.get(t["id"], {}).get("status") == "done")
            marker = " ◀当前" if pid == current_phase_id else ""
            lines.append(f"- {p['name']}({pid}): {d}/{len(tasks)}{marker}")
        lines.append("")

    # 风险
    if "risks" in needs:
        risk = assess_project_risk(flow, current_phase_id, task_status,
                                   project.get("estimates", {}))
        top = risk.get("top_risks", [])[:3]
        if top:
            lines.append("## 高风险任务")
            for r in top:
                lines.append(f"- {r['name']} (风险分: {r['score']}): {'; '.join(r['factors'])}")
            lines.append("")

    # 资源瓶颈
    if "bottlenecks" in needs:
        risk = assess_project_risk(flow, current_phase_id, task_status,
                                   project.get("estimates", {}))
        bn = risk.get("bottlenecks", [])[:3]
        if bn:
            lines.append("## 资源瓶颈")
            for owner, count in bn:
                lines.append(f"- {owner}: {count} 个待办")
            lines.append("")

    return "\n".join(lines)


def generate_prompt(question, project=None, flow=None):
    """根据问题和项目状态生成精准 prompt"""
    if project and flow:
        context = build_focused_context(question, project, flow)
    else:
        context = "(无活跃项目)"

    prompt = f"""以下是项目的相关信息：

{context}

问题：{question}

请基于以上数据给出具体、可执行的建议。"""

    return {
        "system": "你是一位资深硬件项目管理专家。基于提供的项目数据回答问题，只使用给定数据，不要编造信息。",
        "prompt": prompt,
    }


def list_templates():
    """列出支持的问题类型"""
    return [
        {"key": "blocked", "label": "阻塞分析", "example": "PCB Layout 被阻塞了怎么办？"},
        {"key": "accelerate", "label": "加速推进", "example": "怎么才能最快推进项目？"},
        {"key": "architecture", "label": "架构评估", "example": "这个项目的架构是否合理？"},
        {"key": "risk", "label": "风险分析", "example": "当前最大的风险是什么？"},
        {"key": "status", "label": "状态汇报", "example": "帮我写一份项目状态汇报"},
    ]
