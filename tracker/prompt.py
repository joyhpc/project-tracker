"""Prompt 导出引擎 v2 — 适配全局 DAG

核心思路：从问题中提取实体（任务/人员/阶段），围绕实体收集上下文。
"""
from .engine import compute_cpm, build_graph, classify_tasks, count_downstream
from .risk import assess_project_risk


# ── 实体提取 ──────────────────────────────────────────

def _build_task_index(flow):
    """构建任务索引：名称/ID/关键词 → node"""
    index = {}
    for n in flow.get("nodes", []):
        index[n["id"]] = n
        index[n["name"]] = n
        name = n["name"]
        for wlen in range(min(len(name), 6), 2, -1):
            for i in range(len(name) - wlen + 1):
                sub = name[i:i+wlen]
                if sub not in index:
                    index[sub] = n
    return index


def _build_owner_index(flow):
    """构建人员索引"""
    index = {}
    for n in flow.get("nodes", []):
        owners = n.get("owner", "").replace("/", ",").replace("、", ",").split(",")
        for o in owners:
            o = o.strip()
            if o:
                index.setdefault(o, []).append(n)
    return index


def extract_entities(question, flow):
    """从问题中提取所有实体"""
    entities = {"tasks": [], "owners": [], "phases": []}

    task_idx = _build_task_index(flow)
    owner_idx = _build_owner_index(flow)

    seen_tasks = set()
    stop_words = {"什么", "怎么", "如何", "是否", "可以", "需要", "现在",
                  "时候", "多久", "哪些", "为什么", "能不能", "应该",
                  "做什么", "准备", "进度", "状态", "问题", "方案",
                  "今天", "明天", "项目", "阶段", "任务", "工程"}

    # 1. 索引关键词 in 问题
    candidates = sorted(task_idx.keys(), key=len, reverse=True)
    for keyword in candidates:
        if len(keyword) >= 3 and keyword in question:
            node = task_idx[keyword]
            if node["id"] not in seen_tasks:
                entities["tasks"].append(node)
                seen_tasks.add(node["id"])

    # 2. 反向匹配
    if not entities["tasks"]:
        reverse_matches = []
        for n in flow.get("nodes", []):
            if n["id"] in seen_tasks:
                continue
            name = n["name"]
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
                reverse_matches.append((best_len, n))
        reverse_matches.sort(key=lambda x: x[0], reverse=True)
        for _, n in reverse_matches[:2]:
            entities["tasks"].append(n)
            seen_tasks.add(n["id"])

    # 人员匹配
    seen_owners = set()
    for owner_name in sorted(owner_idx.keys(), key=len, reverse=True):
        if owner_name in question and owner_name not in seen_owners:
            entities["owners"].append(owner_name)
            seen_owners.add(owner_name)

    # 阶段匹配
    for phase in flow.get("phases", []):
        if phase["id"] in question or phase.get("name", "") in question:
            entities["phases"].append(phase)
            break

    return entities


# ── 意图信号检测 ──────────────────────────────────────

def detect_signals(question):
    """检测问题中的意图信号"""
    q = question.lower()
    signals = set()

    time_kw = ["时间", "多久", "什么时候", "工期", "交付", "deadline", "预计", "完成", "来得及"]
    block_kw = ["阻塞", "block", "卡住", "等待", "停滞", "替代", "绕过", "先做"]
    speed_kw = ["加速", "缩短", "提速", "赶工期", "瓶颈", "并行"]
    risk_kw = ["风险", "延期", "隐患", "担心"]
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
    if any(kw in q for kw in status_kw):
        signals.add("phase_overview")
        signals.add("blockers")
    if any(kw in q for kw in what_kw):
        signals.add("alternatives")
    if any(kw in q for kw in push_kw):
        signals.add("alternatives")
        signals.add("critical_path")

    return signals


# ── 上下文构建 ──────────────────────────────────────────

def _task_context(node, task_status, blockers, graph, cpm_result):
    """单个任务的上下文"""
    nid = node["id"]
    status = node.get("status", "pending")
    status_map = {"done": "✅已完成", "in_progress": "🔄进行中",
                  "pending": "⏳待开始", "blocked": "🚫已阻塞"}

    lines = [f"[{nid}] {node['name']}"]
    lines.append(f"  状态: {status_map.get(status, status)}")
    if node.get("owner"):
        lines.append(f"  负责人: {node['owner']}")
    if node.get("phase"):
        lines.append(f"  阶段: {node['phase']}")

    # CPM 数据
    cpm_node = cpm_result["nodes"].get(nid, {})
    if cpm_node:
        lines.append(f"  工时: {cpm_node.get('days', 0):.0f}天 | ES={cpm_node.get('es',0):.0f} EF={cpm_node.get('ef',0):.0f} | slack={cpm_node.get('slack',0):.0f}天")
        if cpm_node.get("critical"):
            lines.append("  ⚠️ 关键路径上")

    # 阻塞
    active = [b for b in blockers if b["task_id"] == nid and not b.get("resolved")]
    if active:
        lines.append(f"  ⚠️ 阻塞: {active[0]['reason']}")

    # 依赖
    deps = node.get("depends", [])
    if deps:
        dep_info = []
        for d in deps:
            dn = graph["nodes"].get(d, {})
            ds = dn.get("status", "pending") if isinstance(dn, dict) else "pending"
            dep_info.append(f"{d}({status_map.get(ds, ds)})")
        lines.append(f"  依赖: {', '.join(dep_info)}")

    # 下游
    downstream = count_downstream(nid, graph["rdeps"])
    if downstream > 0:
        direct = [graph["nodes"][s]["name"] for s in graph["rdeps"].get(nid, [])
                  if s in graph["nodes"]]
        lines.append(f"  下游({downstream}个): {', '.join(direct[:5])}")

    if node.get("deliverables"):
        lines.append(f"  交付件: {', '.join(node['deliverables'])}")
    if node.get("gate"):
        lines.append(f"  准入: {node['gate']}")

    return "\n".join(lines)


def _owner_context(owner, flow, task_status):
    """某个人员的任务列表"""
    lines = [f"## {owner} 的任务"]
    for n in flow.get("nodes", []):
        owners = n.get("owner", "").replace("/", ",").replace("、", ",").split(",")
        if owner in [o.strip() for o in owners]:
            status = n.get("status", "pending")
            if status != "done":
                status_map = {"in_progress": "🔄", "pending": "⏳", "blocked": "🚫"}
                lines.append(f"  {status_map.get(status, '⏳')} [{n['id']}] {n['name']} ({n.get('phase', '')})")
    return "\n".join(lines)


def build_context(question, project, flow):
    """根据问题构建精准上下文"""
    task_status = {n["id"]: {"status": n.get("status", "pending")} for n in flow.get("nodes", [])}
    blockers = project.get("blockers", [])
    graph = build_graph(flow)
    cpm = compute_cpm(flow, task_status)

    entities = extract_entities(question, flow)
    signals = detect_signals(question)

    lines = []

    # 项目概要
    total = len(flow.get("nodes", []))
    done = sum(1 for n in flow["nodes"] if n.get("status") == "done")
    lines.append(f"项目: {project['name']} | 进度: {done}/{total} | 总工期: {cpm['total_days']:.0f}天")
    lines.append("")

    has_content = False

    # 任务详情
    if entities["tasks"]:
        for node in entities["tasks"]:
            lines.append(_task_context(node, task_status, blockers, graph, cpm))
            lines.append("")
        has_content = True

    # 人员任务
    if entities["owners"]:
        for owner in entities["owners"]:
            lines.append(_owner_context(owner, flow, task_status))
            lines.append("")
        has_content = True

    # 时间线
    if "timeline" in signals:
        lines.append(f"总工期: {cpm['total_days']:.0f} 天")
        for node in entities["tasks"]:
            r = cpm["nodes"].get(node["id"], {})
            lines.append(f"[{node['id']}] ES={r.get('es',0):.0f} EF={r.get('ef',0):.0f} ({r.get('days',0):.0f}天)")
        lines.append("")
        has_content = True

    # 阻塞 + 替代
    if "blockers" in signals or "alternatives" in signals:
        active = [b for b in blockers if not b.get("resolved")]
        if active and not entities["tasks"]:
            lines.append("当前阻塞:")
            for b in active:
                lines.append(f"  [{b['task_id']}] {b['reason']}")
            lines.append("")

        if "alternatives" in signals:
            classified = classify_tasks(flow, task_status)
            ready = classified.get("ready", [])
            blocked_ids = {b["task_id"] for b in active}
            available = [t for t in ready if t["id"] not in blocked_ids]
            if available:
                lines.append("可立即推进的任务:")
                for t in available[:5]:
                    lines.append(f"  [{t['id']}] {t['name']} ← {t.get('owner', '未分配')}")
                lines.append("")
        has_content = True

    # 关键路径
    if "critical_path" in signals:
        if cpm["critical_path"]:
            lines.append(f"关键路径: {' → '.join(cpm['critical_path'][:8])}")
            lines.append("")
        has_content = True

    # 风险
    if "risks" in signals:
        risk = assess_project_risk(flow, task_status)
        top = risk.get("top_risks", [])[:3]
        if top:
            lines.append("高风险任务:")
            for r in top:
                lines.append(f"  {r['name']} (风险分: {r['score']}): {'; '.join(r['factors'])}")
            lines.append("")
        has_content = True

    # 资源瓶颈
    if "bottlenecks" in signals:
        risk = assess_project_risk(flow, task_status)
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
        for phase in flow.get("phases", []):
            pid = phase["id"]
            phase_nodes = [n for n in flow["nodes"] if n.get("phase") == pid]
            d = sum(1 for n in phase_nodes if n.get("status") == "done")
            lines.append(f"  {phase.get('name', pid)}: {d}/{len(phase_nodes)}")
        lines.append("")
        has_content = True

    # 兜底
    if not has_content:
        classified = classify_tasks(flow, task_status)
        active = [b for b in blockers if not b.get("resolved")]
        if active:
            lines.append(f"阻塞: {len(active)} 个")
            for b in active:
                lines.append(f"  [{b['task_id']}] {b['reason']}")
        in_prog = classified.get("in_progress", [])
        if in_prog:
            lines.append(f"进行中: {', '.join(t['name'] for t in in_prog[:5])}")
        ready = classified.get("ready", [])
        if ready:
            lines.append(f"可启动: {', '.join(t['name'] for t in ready[:5])}")
        lines.append("")

    return "\n".join(lines)


def generate_prompt(question, project=None, flow=None):
    """生成高质量 prompt — 可直接丢给超级 LLM"""
    if project and flow:
        context = build_context(question, project, flow)
        deep = _build_deep_prompt(question, project, flow)
    else:
        context = "(无活跃项目)"
        deep = ""

    system = _build_system_prompt(project, flow)

    prompt = f"""{context}
{deep}
问题：{question}"""

    return {
        "system": system,
        "prompt": prompt,
    }


def _build_system_prompt(project, flow):
    """构建高质量 system prompt"""
    if not project:
        return "你是一位资深硬件产品专家。"

    # 获取项目阶段
    task_status = {n["id"]: {"status": n.get("status", "pending")} for n in flow.get("nodes", [])}
    cpm = compute_cpm(flow, task_status)
    total = len(flow.get("nodes", []))
    done = sum(1 for n in flow["nodes"] if n.get("status") == "done")

    # 判断当前阶段
    current_phase = None
    for phase in flow.get("phases", []):
        pid = phase["id"]
        phase_nodes = [n for n in flow["nodes"] if n.get("phase") == pid]
        phase_done = sum(1 for n in phase_nodes if n.get("status") == "done")
        if phase_done < len(phase_nodes):
            current_phase = phase
            break

    phase_name = current_phase.get("name", "") if current_phase else "未知"

    return f"""你是一位同时精通硬件产品开发、商业策略和供应链管理的顶级产品操盘手。

你的思维框架：
1. 先判断问题的本质 — 是技术问题、商业问题还是执行问题
2. 给出结论性判断，不要模棱两可
3. 每个建议必须可执行（谁做、做什么、多久、交付物是什么）
4. 主动识别提问者可能忽略的盲区和风险
5. 如果涉及决策，给出选项对比表（优劣势 + 推荐）

当前项目背景：
- 产品：{project['name']}
- 进度：{done}/{total}（当前在{phase_name}）
- 总工期：{cpm['total_days']:.0f}天
- 关键路径：{len(cpm['critical_path'])}个节点

回答要求：
- 用中文回答
- 结构清晰，用标题分层
- 给出具体数据和参考（而非空泛建议）
- 如果信息不足以做判断，明确指出需要补充什么"""


def _build_deep_prompt(question, project, flow):
    """根据项目状态生成深度上下文 — 让超级 LLM 有足够信息做深度分析"""
    lines = []
    task_status = {n["id"]: {"status": n.get("status", "pending")} for n in flow.get("nodes", [])}
    cpm = compute_cpm(flow, task_status)

    # 注入已完成任务的决策记录（note + note_file）
    completed_notes = []
    for n in flow.get("nodes", []):
        if n.get("status") == "done" and (n.get("note") or n.get("note_file")):
            note_text = n.get("note", "")
            if n.get("note_file"):
                # 尝试读取备注文件内容
                repo = project.get("repo", "")
                if repo:
                    from pathlib import Path
                    note_path = Path(repo) / n["note_file"]
                    if note_path.exists():
                        content = note_path.read_text(encoding="utf-8")
                        # 截取前 2000 字符避免过长
                        if len(content) > 2000:
                            content = content[:2000] + "\n... (截断)"
                        note_text = content
            if note_text:
                completed_notes.append(f"[{n['name']}] {note_text}")

    if completed_notes:
        lines.append("\n--- 已完成阶段的关键结论 ---")
        for note in completed_notes:
            lines.append(note)
        lines.append("")

    # 注入下一步待决策的任务
    classified = classify_tasks(flow, task_status)
    ready = classified.get("ready", [])
    if ready:
        lines.append("--- 当前待推进的任务 ---")
        for t in ready[:5]:
            slack = cpm["nodes"].get(t["id"], {}).get("slack", 0)
            crit = " 🔴关键路径" if slack == 0 else f" (slack={slack:.0f}天)"
            delivs = ", ".join(t.get("deliverables", []))
            gate = t.get("gate", "")
            line = f"[{t['name']}]{crit}"
            if delivs:
                line += f" — 交付物: {delivs}"
            if gate:
                line += f" — 准入: {gate}"
            lines.append(line)
        lines.append("")

    # 注入风险提示
    risk = assess_project_risk(flow, task_status)
    top_risks = risk.get("top_risks", [])[:3]
    if top_risks:
        lines.append("--- 当前 Top 风险 ---")
        for r in top_risks:
            lines.append(f"[{r['name']}] 风险分{r['score']}: {'; '.join(r['factors'][:2])}")
        lines.append("")

    return "\n".join(lines)


def list_templates():
    return [
        {"key": "task", "label": "任务相关", "example": "PCB Layout 被阻塞了怎么办？"},
        {"key": "person", "label": "人员相关", "example": "硬件工程师现在应该做什么？"},
        {"key": "time", "label": "时间相关", "example": "下个月能不能交付？"},
        {"key": "speed", "label": "加速推进", "example": "怎么才能最快推进项目？"},
        {"key": "risk", "label": "风险分析", "example": "当前最大的风险是什么？"},
        {"key": "status", "label": "状态汇报", "example": "帮我写一份项目状态汇报"},
        {"key": "any", "label": "任意问题", "example": "原理图设计需要注意什么？"},
    ]
