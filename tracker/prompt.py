"""Prompt 导出引擎 v2

核心思路：从问题中提取实体（任务/人员/阶段），围绕实体收集上下文。
不依赖关键词分类，而是实体驱动。
"""
from . import core, flow as flowmod
from .engine import find_critical_path, build_dep_graph, classify_tasks, _count_downstream
from .timeline import compute_full_schedule, estimate_task_days
from .risk import assess_project_risk


# ── 实体提取 ──────────────────────────────────────────

def _build_task_index(flow):
    """构建任务索引：名称/ID/关键词 → task_id"""
    index = {}  # keyword → (phase, task)
    for phase in flow.get("phases", []):
        for t in phase.get("tasks", []):
            # 精确匹配
            index[t["id"]] = (phase, t)
            index[t["name"]] = (phase, t)
            # 中文：滑动窗口提取子串作为关键词
            name = t["name"]
            for wlen in range(min(len(name), 6), 2, -1):  # 先长后短，最短3字
                for i in range(len(name) - wlen + 1):
                    sub = name[i:i+wlen]
                    if sub not in index:
                        index[sub] = (phase, t)
    return index


def _build_owner_index(flow):
    """构建人员索引：owner名 → [tasks]"""
    index = {}
    for phase in flow.get("phases", []):
        for t in phase.get("tasks", []):
            owners = t.get("owner", "").replace("/", ",").replace("、", ",").split(",")
            for o in owners:
                o = o.strip()
                if o:
                    index.setdefault(o, []).append((phase, t))
    return index


def _build_phase_index(flow):
    """构建阶段索引"""
    index = {}
    for phase in flow.get("phases", []):
        index[phase["id"]] = phase
        index[phase.get("name", "")] = phase
    return index


def extract_entities(question, flow):
    """从问题中提取所有实体"""
    entities = {"tasks": [], "owners": [], "phases": []}

    task_idx = _build_task_index(flow)
    owner_idx = _build_owner_index(flow)
    phase_idx = _build_phase_index(flow)

    seen_tasks = set()

    # 停用词：太泛的词不用于匹配
    stop_words = {"什么", "怎么", "如何", "是否", "可以", "需要", "现在",
                  "时候", "多久", "哪些", "为什么", "能不能", "应该",
                  "做什么", "准备", "进度", "状态", "问题", "方案",
                  "今天", "明天", "项目", "阶段", "任务", "工程"}

    # 1. 索引关键词 in 问题（3字以上，长词优先）
    candidates = sorted(task_idx.keys(), key=len, reverse=True)
    for keyword in candidates:
        if len(keyword) >= 3 and keyword in question:
            phase, task = task_idx[keyword]
            if task["id"] not in seen_tasks:
                entities["tasks"].append((phase, task))
                seen_tasks.add(task["id"])

    # 2. 反向匹配：问题中的 2 字词是否是某个任务名的子串
    #    只在第一轮没匹配到时启用，限制最多 2 个避免过度匹配
    if not entities["tasks"]:
        reverse_matches = []
        for phase in flow.get("phases", []):
            for t in phase.get("tasks", []):
                if t["id"] in seen_tasks:
                    continue
                name = t["name"]
                best_len = 0
                for wlen in range(4, 1, -1):
                    for i in range(len(question) - wlen + 1):
                        sub = question[i:i+wlen]
                        if sub in stop_words or len(sub) < 2:
                            continue
                        if sub in name and wlen > best_len:
                            best_len = wlen
                            break
                if best_len > 0:
                    reverse_matches.append((best_len, phase, t))
        # 按匹配长度排序，取前 2 个
        reverse_matches.sort(key=lambda x: x[0], reverse=True)
        for _, phase, t in reverse_matches[:2]:
            entities["tasks"].append((phase, t))
            seen_tasks.add(t["id"])

    # 人员匹配
    seen_owners = set()
    for owner_name in sorted(owner_idx.keys(), key=len, reverse=True):
        if owner_name in question and owner_name not in seen_owners:
            entities["owners"].append(owner_name)
            seen_owners.add(owner_name)

    # 阶段匹配
    for phase_key in sorted(phase_idx.keys(), key=len, reverse=True):
        if phase_key in question:
            entities["phases"].append(phase_idx[phase_key])
            break  # 一个就够

    return entities


# ── 意图信号检测 ──────────────────────────────────────

def detect_signals(question):
    """检测问题中的意图信号，返回需要补充的上下文维度"""
    q = question.lower()
    signals = set()

    time_kw = ["时间", "多久", "什么时候", "工期", "交付", "deadline",
               "预计", "完成", "来得及"]
    block_kw = ["阻塞", "block", "卡住", "等待", "停滞", "替代", "绕过", "先做"]
    speed_kw = ["加速", "缩短", "提速", "赶工期", "瓶颈", "并行"]
    risk_kw = ["风险", "延期", "隐患", "担心"]
    arch_kw = ["架构", "合理", "依赖", "流程", "优化"]
    status_kw = ["汇报", "报告", "总结", "进展"]
    what_kw = ["做什么", "应该", "下一步", "接下来", "优先"]
    push_kw = ["快", "推进"]

    if any(kw in q for kw in time_kw):
        signals.add("timeline")
    if any(kw in q for kw in block_kw):
        signals.add("blockers")
        signals.add("alternatives")
    if any(kw in q for kw in speed_kw):
        signals.add("critical_path")
        signals.add("alternatives")
        signals.add("bottlenecks")
    if any(kw in q for kw in risk_kw):
        signals.add("risks")
    if any(kw in q for kw in arch_kw):
        signals.add("phase_overview")
        signals.add("dependencies")
    if any(kw in q for kw in status_kw):
        signals.add("phase_overview")
        signals.add("blockers")
    if any(kw in q for kw in what_kw):
        signals.add("alternatives")
    # "推进"/"快" — 轻量信号，补替代方案和关键路径
    if any(kw in q for kw in push_kw):
        signals.add("alternatives")
        signals.add("critical_path")

    return signals


# ── 上下文构建 ──────────────────────────────────────────

def _task_context(task, phase, task_status, blockers, graph):
    """单个任务的上下文文本"""
    tid = task["id"]
    entry = task_status.get(tid, {})
    status = entry.get("status", "pending")
    status_map = {"done": "✅已完成", "in_progress": "🔄进行中",
                  "pending": "⏳待开始", "blocked": "🚫已阻塞"}

    lines = [f"[{tid}] {task['name']}"]
    lines.append(f"  状态: {status_map.get(status, status)}")
    if task.get("owner"):
        lines.append(f"  负责人: {task['owner']}")
    lines.append(f"  阶段: {phase.get('name', '')}")

    # 阻塞
    active = [b for b in blockers if b["task_id"] == tid and not b.get("resolved")]
    if active:
        lines.append(f"  ⚠️ 阻塞: {active[0]['reason']}")

    # 依赖
    deps = task.get("depends", [])
    if deps:
        dep_info = []
        for d in deps:
            ds = task_status.get(d, {}).get("status", "pending")
            dep_info.append(f"{d}({status_map.get(ds, ds)})")
        lines.append(f"  依赖: {', '.join(dep_info)}")

    # 下游
    if graph:
        downstream = _count_downstream(tid, graph["rdeps"], set())
        if downstream > 0:
            direct = [f"{graph['tasks'][oid]['name']}"
                      for oid, ot in graph["tasks"].items()
                      if tid in ot.get("depends", [])]
            lines.append(f"  下游({downstream}个): {', '.join(direct)}")

    # 交付件/准入
    if task.get("deliverables"):
        lines.append(f"  交付件: {', '.join(task['deliverables'])}")
    if task.get("gate"):
        lines.append(f"  准入: {task['gate']}")

    return "\n".join(lines)


def _owner_context(owner, flow, task_status, current_phase_id):
    """某个人员的任务列表"""
    lines = [f"## {owner} 的任务"]
    for phase in flow.get("phases", []):
        for t in phase.get("tasks", []):
            owners = t.get("owner", "").replace("/", ",").replace("、", ",").split(",")
            if owner in [o.strip() for o in owners]:
                status = task_status.get(t["id"], {}).get("status", "pending")
                if status != "done":
                    marker = " ◀当前阶段" if phase["id"] == current_phase_id else ""
                    status_map = {"in_progress": "🔄", "pending": "⏳", "blocked": "🚫"}
                    lines.append(f"  {status_map.get(status, '⏳')} [{t['id']}] {t['name']} ({phase.get('name', '')}){marker}")
    return "\n".join(lines)


def build_context(question, project, flow):
    """根据问题构建精准上下文"""
    task_status = project.get("tasks", {})
    blockers = project.get("blockers", [])
    current_phase_id = project["current_phase"]
    phases = flow.get("phases", [])
    phase_map = {p["id"]: p for p in phases}
    current_phase = phase_map.get(current_phase_id, {})
    graph = build_dep_graph(current_phase)

    entities = extract_entities(question, flow)
    signals = detect_signals(question)

    lines = []

    # 一行项目概要（始终给）
    total = sum(len(p.get("tasks", [])) for p in phases)
    done = sum(1 for p in phases for t in p.get("tasks", [])
               if task_status.get(t["id"], {}).get("status") == "done")
    lines.append(f"项目: {project['name']} | 阶段: {current_phase.get('name', '')} | 进度: {done}/{total}")
    lines.append("")

    has_content = False

    # ── 实体驱动的上下文 ──

    # 任务详情
    if entities["tasks"]:
        for phase, task in entities["tasks"]:
            # 如果任务在当前阶段，用当前阶段的 graph；否则构建对应阶段的
            if phase["id"] == current_phase_id:
                g = graph
            else:
                g = build_dep_graph(phase)
            lines.append(_task_context(task, phase, task_status, blockers, g))
            lines.append("")
        has_content = True

    # 人员任务
    if entities["owners"]:
        for owner in entities["owners"]:
            lines.append(_owner_context(owner, flow, task_status, current_phase_id))
            lines.append("")
        has_content = True

    # ── 信号驱动的补充上下文 ──

    # 时间线
    if "timeline" in signals:
        sched = compute_full_schedule(flow, current_phase_id, task_status,
                                      custom_estimates=project.get("estimates", {}))
        lines.append(f"预计总工期: {sched.get('total_days', '?')} 天")
        if sched.get("end_date"):
            lines.append(f"预计完成: {sched['end_date'].strftime('%Y-%m-%d')}")

        # 如果问的是具体任务的时间，给该任务的工时
        for _, task in entities["tasks"]:
            days = estimate_task_days(task)
            lines.append(f"[{task['id']}] 预估工时: {days} 天")
        lines.append("")
        has_content = True

    # 阻塞 + 替代方案
    if "blockers" in signals or "alternatives" in signals:
        active = [b for b in blockers if not b.get("resolved")]
        # 只在没有具体任务实体时列出所有阻塞
        if active and not entities["tasks"]:
            lines.append("当前阻塞:")
            for b in active:
                lines.append(f"  [{b['task_id']}] {b['reason']}")
            lines.append("")

        if "alternatives" in signals:
            classified = classify_tasks(current_phase, task_status)
            ready = classified.get("ready", [])
            blocked_ids = {b["task_id"] for b in active}
            available = [t for t in ready if t["id"] not in blocked_ids]
            if available:
                lines.append("可立即推进的任务:")
                for t in available:
                    lines.append(f"  [{t['id']}] {t['name']} ← {t.get('owner', '未分配')}")
                lines.append("")
        has_content = True

    # 关键路径
    if "critical_path" in signals:
        cp = find_critical_path(current_phase, task_status)
        if cp:
            lines.append(f"关键路径: {' → '.join(cp)}")
            lines.append("")
        has_content = True

    # 风险
    if "risks" in signals:
        risk = assess_project_risk(flow, current_phase_id, task_status,
                                   project.get("estimates", {}))
        top = risk.get("top_risks", [])[:3]
        if top:
            lines.append("高风险任务:")
            for r in top:
                lines.append(f"  {r['name']} (风险分: {r['score']}): {'; '.join(r['factors'])}")
            lines.append("")
        has_content = True

    # 资源瓶颈
    if "bottlenecks" in signals:
        risk = assess_project_risk(flow, current_phase_id, task_status,
                                   project.get("estimates", {}))
        bn = risk.get("bottlenecks", [])[:3]
        if bn:
            lines.append("资源瓶颈:")
            for owner, count in bn:
                lines.append(f"  {owner}: {count} 个待办")
            lines.append("")
        has_content = True

    # 阶段概览
    if "phase_overview" in signals:
        lines.append("各阶段进度:")
        for p in phases:
            d = sum(1 for t in p.get("tasks", [])
                    if task_status.get(t["id"], {}).get("status") == "done")
            marker = " ◀" if p["id"] == current_phase_id else ""
            lines.append(f"  {p['name']}: {d}/{len(p.get('tasks', []))}{marker}")
        lines.append("")
        has_content = True

    # ── 兜底：没有任何实体或信号命中 ──
    if not has_content:
        # 给当前阶段概要
        classified = classify_tasks(current_phase, task_status)
        phase_tasks = current_phase.get("tasks", [])
        phase_done = sum(1 for t in phase_tasks
                         if task_status.get(t["id"], {}).get("status") == "done")
        lines.append(f"当前阶段: {current_phase.get('name', '')} ({phase_done}/{len(phase_tasks)})")

        active = [b for b in blockers if not b.get("resolved")]
        if active:
            lines.append(f"阻塞: {len(active)} 个")
            for b in active:
                lines.append(f"  [{b['task_id']}] {b['reason']}")

        in_prog = classified.get("in_progress", [])
        if in_prog:
            lines.append(f"进行中: {', '.join(t['name'] for t in in_prog)}")

        ready = classified.get("ready", [])
        if ready:
            lines.append(f"可启动: {', '.join(t['name'] for t in ready)}")
        lines.append("")

    return "\n".join(lines)


def generate_prompt(question, project=None, flow=None):
    """生成精准 prompt"""
    if project and flow:
        context = build_context(question, project, flow)
    else:
        context = "(无活跃项目)"

    prompt = f"""{context}
问题：{question}"""

    return {
        "system": "你是一位资深硬件项目管理专家。基于提供的项目数据回答问题。只使用给定数据，不编造。给出具体可执行的建议。",
        "prompt": prompt,
    }


def list_templates():
    """列出支持的问题类型示例"""
    return [
        {"key": "task", "label": "任务相关", "example": "PCB Layout 被阻塞了怎么办？"},
        {"key": "person", "label": "人员相关", "example": "硬件工程师现在应该做什么？"},
        {"key": "time", "label": "时间相关", "example": "下个月能不能交付？"},
        {"key": "speed", "label": "加速推进", "example": "怎么才能最快推进项目？"},
        {"key": "risk", "label": "风险分析", "example": "当前最大的风险是什么？"},
        {"key": "status", "label": "状态汇报", "example": "帮我写一份项目状态汇报"},
        {"key": "any", "label": "任意问题", "example": "原理图设计需要注意什么？"},
    ]
