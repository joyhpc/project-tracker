"""Prompt 导出引擎 v4 — BM25 知识检索 + 角色聚焦

设计理念：
- 用 BM25 检索替代信号词匹配，自动适应任何项目
- 保留 v3 的角色设定和问题类型聚焦
- 从 note_file 中按标题切块，保留表格等结构化数据
- 输出可直接复制给超级 LLM
"""
from pathlib import Path
from .engine import compute_cpm, build_graph, classify_tasks, count_downstream
from .risk import assess_project_risk
from .knowledge import retrieve_context


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
