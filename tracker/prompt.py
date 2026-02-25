"""Prompt 导出引擎 v4 — BM25 知识检索 + 角色聚焦

设计理念：
- 用 BM25 检索替代信号词匹配，自动适应任何项目
- 保留 v3 的角色设定和问题类型聚焦
- 从 note_file 中按标题切块，保留表格等结构化数据
- 输出可直接复制给超级 LLM
- v5: --deep 模式 — 生成 meta-prompt，让 LLM 做矛盾识别+盲区发现+深度 prompt 生成
"""
import os
from pathlib import Path
from . import core
from .engine import compute_cpm, build_graph, classify_tasks, count_downstream
from .risk import assess_project_risk
from .knowledge import retrieve_context, build_knowledge_base, BM25


# ── 主入口 ──────────────────────────────────────────

def _detect_question_type(question):
    """检测问题类型"""
    q = question.lower()
    if any(w in q for w in ["决策", "拍板", "a/b/c", "推荐组合"]):
        return "decision"
    if "选" in q and "选型" not in q:
        return "decision"
    if any(w in q for w in ["方案", "怎么做", "架构", "选型", "设计"]):
        return "solution"
    if any(w in q for w in ["风险", "失败", "避坑", "教训"]):
        return "risk"
    if any(w in q for w in ["战略", "方向", "定位", "长期"]):
        return "strategy"
    return "general"


def generate_prompt(question, project=None, flow=None):
    """生成高质量 prompt — 可直接丢给超级 LLM"""
    if not project or not flow:
        return {"system": "", "prompt": question}

    task_status = {n["id"]: {"status": n.get("status", "pending")} for n in flow.get("nodes", [])}
    cpm = compute_cpm(flow, task_status)
    qtype = _detect_question_type(question)

    role = _get_role(qtype)
    background = _build_product_background(question, project, flow, cpm)
    focused = _build_focused_context(question, project, flow, cpm, task_status, qtype)
    instruction = _build_task_instruction(question, qtype)

    prompt = f"{role}\n\n{background}\n{focused}\n{instruction}"

    return {"system": "", "prompt": prompt}
# ── 角色 ──────────────────────────────────────────

def _get_role(qtype):
    return {
        "decision": "**角色**：你是一位顶级硬件产品战略顾问，专长于新品类的市场切入与定位。",
        "solution": "**角色**：你是一位资深硬件产品架构师，精通从概念到量产的全流程技术选型。",
        "risk": "**角色**：你是一位产品风险评估专家。扮演红队角色，对计划做压力测试，找出盲区。",
        "strategy": "**角色**：你是一位产品战略顾问，擅长从市场趋势和竞争格局中找到差异化定位。",
        "general": "**角色**：你是一位资深硬件产品专家。",
    }[qtype]


# ── 产品背景（自然语言）──────────────────────────────

def _build_product_background(question, project, flow, cpm):
    """用自然语言构建产品背景 + BM25 检索相关知识"""
    lines = ["**项目背景**："]
    lines.append(f"我们正在开发一款「{project['name']}」。")

    repo = project.get("repo", "")

    # 提取产品定义（引用块 — 仍用规则，因为这是固定格式）
    product_def = ""
    for n in flow.get("nodes", []):
        if n.get("status") != "done" or not n.get("note_file") or not repo:
            continue
        path = Path(repo) / n["note_file"]
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if not product_def:
            quote_count = 0
            for line in content.split("\n"):
                if line.strip().startswith(">") and len(line.strip()) > 15:
                    clean = line.strip().lstrip("> ").strip()
                    if any(w in clean for w in ["等待", "⏳", "⚡", "Slack", "任务"]):
                        continue
                    if product_def:
                        product_def += "；" + clean
                    else:
                        product_def = clean
                    quote_count += 1
                    if quote_count >= 2:
                        break
        if product_def:
            break

    if product_def:
        lines.append(f"- **核心定义**：{product_def}")

    # BM25 检索相关知识块
    current_task = None
    for n in flow.get("nodes", []):
        if n.get("status") == "in_progress":
            current_task = n
            break

    chunks = retrieve_context(question, project, flow, current_task, top_k=5)
    if chunks:
        lines.append("- **相关历史结论**：")
        for chunk in chunks:
            path_str = " > ".join(chunk.path) if chunk.path else ""
            source = f"[{chunk.task_name}]"
            if path_str:
                source += f" {path_str}"
            # 截取内容摘要（保留结构但限制长度）
            content = chunk.content
            if len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"\n<reference source=\"{source}\">")
            lines.append(content)
            lines.append("</reference>")

    # 当前阶段
    total = len(flow.get("nodes", []))
    done = sum(1 for n in flow["nodes"] if n.get("status") == "done")
    phase_name = "未知"
    for phase in flow.get("phases", []):
        phase_nodes = [n for n in flow["nodes"] if n.get("phase") == phase["id"]]
        if sum(1 for n in phase_nodes if n.get("status") == "done") < len(phase_nodes):
            phase_name = phase.get("name", "")
            break
    lines.append(f"\n- **当前阶段**：{phase_name}（进度 {done}/{total}，总工期 {cpm['total_days']:.0f}天）")

    return "\n".join(lines)


# ── 聚焦上下文 ──────────────────────────────────────

def _build_focused_context(question, project, flow, cpm, task_status, qtype):
    """根据问题类型注入聚焦上下文"""
    lines = []

    if qtype == "decision":
        decisions = _extract_decisions(project, flow)
        if decisions:
            lines.append("\n**待决策事项**：")
            lines.append(decisions)

    elif qtype == "solution":
        ready = [t for t in flow.get("nodes", [])
                 if t.get("status") != "done"
                 and all(_find_done(flow, d) for d in t.get("depends", []))]
        for t in ready[:2]:
            if cpm["nodes"].get(t["id"], {}).get("slack", 1) == 0:
                delivs = ", ".join(t.get("deliverables", []))
                lines.append(f"\n**当前任务**：{t['name']}（关键路径，延迟直接影响总工期）")
                if delivs:
                    lines.append(f"**需要输出**：{delivs}")

    elif qtype == "risk":
        graph = build_graph(flow)
        crit = [t for t in flow.get("nodes", [])
                if t.get("status") != "done"
                and cpm["nodes"].get(t["id"], {}).get("slack", 1) == 0]
        if crit:
            lines.append("\n**关键路径任务**：")
            for t in crit[:5]:
                ds = count_downstream(t["id"], graph["rdeps"])
                lines.append(f"- {t['name']}（阻塞下游 {ds} 个任务）")

    elif qtype == "strategy":
        # 战略类也需要市场洞察，但已在 background 中包含
        pass

    return "\n".join(lines)


def _find_done(flow, dep_id):
    for n in flow.get("nodes", []):
        if n["id"] == dep_id:
            return n.get("status") == "done"
    return False


# ── 任务指令 ──────────────────────────────────────

def _build_task_instruction(question, qtype):
    """构建聚焦的任务指令"""
    base = f"\n**你的任务**：\n{question}\n"

    # 如果用户问题本身已包含具体输出要求，生成匹配的格式引导
    has_explicit_requirements = any(p in question for p in [
        "1)", "2)", "3)", "1）", "2）", "需要：", "需要:", "给出：", "给出:",
        "评估：", "评估:", "包含：", "包含:",
    ])

    if has_explicit_requirements:
        # 根据问题内容生成匹配的输出引导
        guide = "\n**输出要求**：\n"
        guide += "请针对上述每个评估点逐一给出明确结论，格式如下：\n"
        guide += "- 每个评估点：结论（GO/CAUTION/NO-GO） + 关键数据/依据 + 风险与对策\n"
        guide += "- 最终给出综合判定和下一步行动建议\n"
        guide += "\n要求：中文回答，结论先行，必须给出具体数值而非定性描述。"
        return base + guide

    suffix = {
        "decision": "\n请推荐最优组合，并提供：\n1. 选择该组合的核心逻辑\n2. 潜在风险与对策\n\n要求分析犀利、客观，直接切入商业本质。",
        "solution": "\n请给出具体方案，包含：\n1. 技术选型对比表（优劣势 + 推荐）\n2. 初步 BOM 成本预估\n3. 关键风险点\n\n要求方案可落地，不要泛泛而谈。",
        "risk": "\n请从以下维度分析：\n1. 最可能导致项目失败的 Top 3 风险\n2. 每个风险的严重程度和发生概率\n3. 具体的应对方案\n\n要求犀利直接，不要报喜不报忧。",
        "strategy": "\n请给出战略建议，包含：\n1. 推荐的战略定位和理由\n2. 需要避开的战略陷阱\n3. 分阶段执行路径\n\n要求有全局视野，不要只看眼前。",
        "general": "\n要求：中文回答，结论先行，每个建议必须可执行。",
    }

    return base + suffix.get(qtype, suffix["general"])


# ── 提取器 ──────────────────────────────────────

def _extract_decisions(project, flow):
    """从已完成任务的 note_file 中提取待决策段落"""
    repo = project.get("repo", "")
    if not repo:
        return ""

    for n in flow.get("nodes", []):
        if n.get("status") != "done" or not n.get("note_file"):
            continue
        path = Path(repo) / n["note_file"]
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")

        lines = content.split("\n")
        capture = False
        result = []
        for line in lines:
            if any(w in line for w in ["决策", "待拍板", "Q1", "Q2", "Q3"]):
                capture = True
            if capture:
                result.append(line)
                if line.startswith("---") and len(result) > 3:
                    break
                if line.startswith("## ") and len(result) > 5:
                    break
        if result:
            text = "\n".join(result)
            return text[:1000] if len(text) > 1000 else text
    return ""


# ── 自动生成问题 ──────────────────────────────────

def auto_generate_questions(project, flow):
    """根据项目当前状态，自动生成最有价值的问题列表"""
    task_status = {n["id"]: {"status": n.get("status", "pending")} for n in flow.get("nodes", [])}
    cpm = compute_cpm(flow, task_status)
    classified = classify_tasks(flow, task_status)
    risk = assess_project_risk(flow, task_status)

    ready = classified.get("ready", [])
    blocked = classified.get("blocked", [])
    questions = []

    # 1. 待决策项
    for n in flow.get("nodes", []):
        if n.get("status") == "done" and n.get("note"):
            if any(w in n["note"] for w in ["待拍板", "待决策"]):
                questions.append({
                    "priority": "🔴 决策阻塞",
                    "question": f"基于{n['name']}的结论，需要做出哪些关键决策？请给出每个选项的优劣势对比和明确推荐。",
                    "why": f"{n['name']}已完成但有待拍板决策，不决策则下游任务无法启动",
                })

    # 2. 关键路径任务
    for t in ready[:2]:
        if cpm["nodes"].get(t["id"], {}).get("slack", 0) > 0:
            continue
        delivs = ", ".join(t.get("deliverables", []))
        questions.append({
            "priority": "🔴 关键路径",
            "question": f"[{t['name']}] 的具体执行方案是什么？需要输出：技术选型对比、执行步骤、时间估算、交付物清单（{delivs}）、潜在风险及应对。",
            "why": "关键路径任务，slack=0，延迟直接影响总工期",
        })

    # 3. 高风险任务
    for r in risk.get("top_risks", [])[:2]:
        if any(r["name"] in q["question"] for q in questions):
            continue
        questions.append({
            "priority": "🟡 风险预警",
            "question": f"[{r['name']}] 风险分 {r['score']}，主要因素：{'; '.join(r['factors'][:2])}。如何降低风险？",
            "why": "高风险任务，失败会阻塞下游",
        })

    # 4. 阻塞任务
    for b in blocked[:2]:
        questions.append({
            "priority": "🟠 阻塞中",
            "question": f"[{b['name']}] 被阻塞，原因：{b.get('block_reason', '依赖未完成')}。如何绕过或加速？",
            "why": "阻塞任务不解决会拖延整体进度",
        })

    # 5. 战略思考（项目早期）
    total = len(flow.get("nodes", []))
    done = sum(1 for n in flow["nodes"] if n.get("status") == "done")
    if total > 0 and done / total < 0.1:
        questions.append({
            "priority": "💡 战略思考",
            "question": f"作为{project['name']}项目，在当前阶段最容易犯的战略错误是什么？有哪些同类产品的失败教训？",
            "why": "项目早期，战略方向错误的代价最大",
        })

    return questions


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


# ── Deep Prompt (v5) ──────────────────────────────────

def generate_deep_prompt(question, project, flow):
    """生成 meta-prompt — 让 LLM 做矛盾识别+盲区发现，输出深度 prompt"""
    if not project or not flow:
        return {"prompt": question}

    repo = project.get("repo", "")
    reviews = project.get("reviews", [])
    decisions = project.get("decisions", [])
    pocs = project.get("pocs", [])

    task_status = {n["id"]: {"status": n.get("status", "pending")} for n in flow.get("nodes", [])}
    cpm = compute_cpm(flow, task_status)

    lines = []

    # ── 角色 ──
    lines.append("**角色**：你是一位顶级 Prompt 工程专家，同时精通硬件产品开发全流程。")
    lines.append("你的任务是：基于以下项目的完整分析上下文，生成一个极具深度和针对性的 prompt，")
    lines.append("用于向另一个超级 LLM 提问，以获得最高质量的回答。")
    lines.append("")

    # ── 项目概况 ──
    total = len(flow.get("nodes", []))
    done = sum(1 for n in flow["nodes"] if n.get("status") == "done")
    lines.append(f"## 项目：{project['name']}")
    lines.append(f"进度：{done}/{total}，总工期 {cpm['total_days']:.0f} 天")
    lines.append("")

    # ── 已拍板决策 ──
    if decisions:
        lines.append("## 已拍板决策")
        for d in decisions:
            if d.get("status", "active") == "active":
                lines.append(f"- **D{d['id']}: {d['title']}** — {d.get('impact', '')} (来源: {d.get('source', '')})")
        lines.append("")

    # ── PoC 状态 ──
    if pocs:
        lines.append("## PoC 验证状态")
        for poc in pocs:
            icon = {"go": "🟢", "no-go": "🔴", "pending": "⏳", "caution": "🟡"}.get(poc["status"], "⚪")
            lines.append(f"- {icon} P{poc['id']}: {poc['title']} — 红线: {poc.get('metric', '')} — {poc['status']}")
        lines.append("")

    # ── 所有 review 判定汇总 ──
    if reviews:
        lines.append("## 已完成的可行性分析（判定汇总）")
        lines.append("")
        all_verdicts = []
        for r in reviews:
            fname = os.path.basename(r["file"]).replace("-result.md", "")
            verdict_list = core.normalize_verdicts(r.get("verdicts", []))
            for v in verdict_list:
                icon = {"GO": "🟢", "CAUTION": "🟡", "NO-GO": "🔴",
                        "HIGH RISK": "🔴", "CONDITIONAL GO": "🟡",
                        "HIGHLY FEASIBLE": "🟢"}.get(v["verdict"], "⚪")
                lines.append(f"- {icon} [{fname}] {v['topic']}: **{v['verdict']}**")
                all_verdicts.append({**v, "source": fname})

        go = sum(1 for v in all_verdicts if v["verdict"] in ("GO", "HIGHLY FEASIBLE"))
        caution = sum(1 for v in all_verdicts if v["verdict"] in ("CAUTION", "CONDITIONAL GO"))
        nogo = sum(1 for v in all_verdicts if v["verdict"] in ("NO-GO", "HIGH RISK"))
        lines.append(f"\n统计：🟢 GO: {go}  🟡 CAUTION: {caution}  🔴 NO-GO: {nogo}")
        lines.append("")

        # ── 矛盾检测提示 ──
        # 找出同一主题在不同回复中判定不一致的情况
        nogo_topics = [v for v in all_verdicts if v["verdict"] in ("NO-GO", "HIGH RISK")]
        go_topics = [v for v in all_verdicts if v["verdict"] in ("GO", "HIGHLY FEASIBLE")]
        if nogo_topics:
            lines.append("## ⚠️ 需要特别关注的 NO-GO 项")
            for v in nogo_topics:
                lines.append(f"- [{v['source']}] {v['topic']}")
            lines.append("")

    # ── 完整 review 原文（深度模式核心：把所有分析原文喂给 LLM）──
    if reviews and repo:
        lines.append("## 完整分析原文")
        lines.append("")
        for r in reviews:
            fpath = Path(repo) / r["file"]
            if not fpath.exists():
                continue
            fname = os.path.basename(r["file"]).replace("-result.md", "")
            content = fpath.read_text(encoding="utf-8")
            # 截取合理长度（每份最多 3000 字符，保留核心内容）
            if len(content) > 3000:
                content = content[:3000] + "\n\n... (截断，完整内容见原文件)"
            lines.append(f"<review source=\"{fname}\">")
            lines.append(content)
            lines.append("</review>")
            lines.append("")

    # ── BM25 检索：补充 note_file / docs 中与问题相关的上下文 ──
    all_chunks = build_knowledge_base(project, flow)
    if all_chunks:
        engine = BM25(all_chunks)
        queries = [
            question,
            f"{question} 矛盾 冲突 不一致",
            f"{question} 风险 盲区 未验证",
        ]
        seen = set()
        merged = []
        # 排除已在 review 原文中出现的内容
        review_files = {os.path.basename(r["file"]) for r in reviews} if reviews else set()
        for q in queries:
            for chunk in engine.search(q, top_k=8):
                key = chunk.content[:80]
                if key not in seen:
                    seen.add(key)
                    merged.append(chunk)

        if merged:
            lines.append("## 补充上下文（BM25 检索，来自项目文档）")
            lines.append("")
            for i, chunk in enumerate(merged[:8], 1):
                source = f"[{chunk.task_name}]"
                if chunk.path:
                    source += f" {' > '.join(chunk.path)}"
                lines.append(f"<reference id=\"ctx-{i}\" source=\"{source}\">")
                content = chunk.content
                if len(content) > 800:
                    content = content[:800] + "\n... (截断)"
                lines.append(content)
                lines.append("</reference>")
                lines.append("")

    # ── 已完成任务的结论摘要 ──
    done_notes = []
    for n in flow.get("nodes", []):
        if n.get("status") == "done" and n.get("note"):
            done_notes.append(f"- [{n['name']}] {n['note']}")
    if done_notes:
        lines.append("## 已完成任务结论")
        lines.extend(done_notes)
        lines.append("")

    # ── 关键路径信息 ──
    crit = [t for t in flow.get("nodes", [])
            if t.get("status") != "done"
            and cpm["nodes"].get(t["id"], {}).get("slack", 0) == 0]
    if crit:
        lines.append("## 关键路径（slack=0，延迟直接影响总工期）")
        for t in crit[:5]:
            lines.append(f"- {t['name']} ({t.get('phase', '')})")
        lines.append("")

    # ── 核心指令 ──
    lines.append("---")
    lines.append("")
    lines.append(f"## 用户想要深入探讨的问题")
    lines.append(f"**{question}**")
    lines.append("")
    lines.append("## 你的任务")
    lines.append("基于以上完整项目上下文，生成一个极具深度的 prompt，用于向超级 LLM 提问。")
    lines.append("")
    lines.append("**生成 prompt 时必须做到：**")
    lines.append("")
    lines.append("1. **矛盾识别**：找出不同回复之间的结论冲突（如 A 报告说 GO，B 报告说 NO-GO），在 prompt 中明确指出这些矛盾，要求超级 LLM 调和或给出取舍建议")
    lines.append("2. **盲区发现**：找出所有回复都没有讨论但对项目成败至关重要的问题（如可靠性、量产一致性、供应链风险、法规合规等），在 prompt 中要求超级 LLM 补充分析")
    lines.append("3. **数据锚定**：prompt 中必须引用具体数据（型号、价格、参数、判定结论），不允许泛泛而谈")
    lines.append("4. **决策约束**：prompt 中必须引用已拍板决策（D1/D2/...）作为约束条件，要求回答在这些约束下给出方案")
    lines.append("5. **量化要求**：要求超级 LLM 的回答必须包含具体数值、对比表格、GO/NO-GO 判定，不接受定性描述")
    lines.append("6. **可执行性**：prompt 的最终输出必须是可直接执行的行动计划，不是分析报告")
    lines.append("")
    lines.append("**输出格式**：直接输出生成的深度 prompt（不需要解释你的思考过程），prompt 开头设定角色，结尾明确输出格式要求。")

    return {"prompt": "\n".join(lines)}
