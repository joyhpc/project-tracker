"""启发式项目引导引擎

核心逻辑：
1. 读取流程定义 → 反向推导每个阶段需要提前想清楚的问题
2. 读取 guide_questions.yaml 问题模板
3. 交互式引导用户回答，收集信息
4. 生成：项目初始 YAML + 风险清单 + 待确认事项 + 建议行动
"""
import yaml
from pathlib import Path
from datetime import datetime
from . import flow as flowmod

GUIDES_DIR = Path(__file__).parent.parent / "flows"


def load_guide_questions() -> dict:
    """加载启发式问题模板"""
    guide_file = GUIDES_DIR / "guide_questions.yaml"
    if not guide_file.exists():
        raise FileNotFoundError(f"引导问题模板不存在: {guide_file}")
    with open(guide_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_phase_questions(phase_id: str, product: str = "") -> dict | None:
    """获取指定阶段的引导问题"""
    guide = load_guide_questions()
    # 别名映射
    aliases = guide.get("aliases", {})
    resolved_id = aliases.get(phase_id, phase_id)
    phase_data = guide.get("phases", {}).get(resolved_id)
    if not phase_data:
        return None

    # 替换 {product} 占位符
    if product:
        questions = []
        for q in phase_data.get("questions", []):
            q_copy = dict(q)
            q_copy["q"] = q_copy["q"].replace("{product}", product)
            questions.append(q_copy)
        phase_data = dict(phase_data)
        phase_data["questions"] = questions

    return phase_data


def get_all_guide_phases(product: str = "") -> list[dict]:
    """获取所有阶段的引导问题（按顺序）"""
    guide = load_guide_questions()
    phases = []
    for phase_id, phase_data in guide.get("phases", {}).items():
        pd = dict(phase_data)
        pd["id"] = phase_id
        if product:
            questions = []
            for q in pd.get("questions", []):
                q_copy = dict(q)
                q_copy["q"] = q_copy["q"].replace("{product}", product)
                questions.append(q_copy)
            pd["questions"] = questions
        phases.append(pd)
    return phases


def map_guide_to_flow(flow_name: str = "duxin") -> dict:
    """将引导问题映射到流程定义的阶段

    返回 {guide_phase_id: [flow_phase_id, ...]}
    引导问题的阶段可能覆盖多个流程阶段（如 TEST 覆盖 TEST_A/TEST_B/TEST_C）
    """
    fl = flowmod.load_flow(flow_name)
    flow_phases = flowmod.get_phase_order(fl)
    guide = load_guide_questions()
    guide_phases = list(guide.get("phases", {}).keys())

    mapping = {}
    for gp in guide_phases:
        matched = []
        for fp in flow_phases:
            # 精确匹配或前缀匹配
            if fp == gp or fp.startswith(gp + "_") or fp.startswith(gp):
                matched.append(fp)
        if not matched:
            # 特殊映射
            if gp == "TEST":
                matched = [fp for fp in flow_phases if "TEST" in fp]
        mapping[gp] = matched if matched else [gp]

    return mapping


def run_guide_interactive(product: str = "", flow_name: str = "duxin") -> dict:
    """交互式引导（CLI 模式）

    返回收集到的所有答案和生成的报告
    """
    phases = get_all_guide_phases(product)
    answers = {}
    skipped = []
    risks = []

    print(f"\n{'='*60}")
    print(f"  🧭 项目启发式引导")
    if product:
        print(f"  📦 产品: {product}")
    print(f"{'='*60}\n")
    print("对每个问题输入你的想法。")
    print("输入 's' 跳过，'q' 退出当前阶段，'qq' 退出全部。\n")

    for phase in phases:
        print(f"\n{'─'*50}")
        print(f"📍 {phase['id']}: {phase['title']}")
        print(f"{'─'*50}\n")

        phase_answers = {}
        quit_all = False

        for i, q in enumerate(phase.get("questions", []), 1):
            print(f"  {i}. {q['q']}")
            try:
                answer = input("     → ").strip()
            except (EOFError, KeyboardInterrupt):
                quit_all = True
                break

            if answer.lower() == "qq":
                quit_all = True
                break
            if answer.lower() == "q":
                break
            if answer.lower() == "s" or not answer:
                skipped.append({
                    "phase": phase["id"],
                    "question": q["q"],
                    "key": q["key"],
                    "category": q.get("category", ""),
                })
                print("     (已跳过)\n")
                continue

            phase_answers[q["key"]] = {
                "answer": answer,
                "category": q.get("category", ""),
                "question": q["q"],
            }
            print()

        answers[phase["id"]] = phase_answers

        # 显示阶段风险提示
        hints = phase.get("risk_hints", [])
        if hints:
            print(f"\n  ⚠️ 风险提示:")
            for h in hints:
                print(f"     • {h}")
                risks.append({"phase": phase["id"], "hint": h})

        if quit_all:
            break

    return {
        "product": product,
        "answers": answers,
        "skipped": skipped,
        "risks": risks,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def format_guide_overview(product: str = "") -> str:
    """非交互模式：输出所有阶段的问题概览（用于展示/打印）"""
    phases = get_all_guide_phases(product)
    lines = []

    lines.append(f"{'='*60}")
    lines.append(f"  🧭 项目启发式引导 — 问题总览")
    if product:
        lines.append(f"  📦 产品: {product}")
    lines.append(f"{'='*60}")
    lines.append("")

    total_q = 0
    for phase in phases:
        questions = phase.get("questions", [])
        total_q += len(questions)

        lines.append(f"{'─'*50}")
        lines.append(f"📍 {phase['id']}: {phase['title']}")
        lines.append(f"{'─'*50}")
        lines.append("")

        for i, q in enumerate(questions, 1):
            cat = f"[{q.get('category', '')}] " if q.get("category") else ""
            lines.append(f"  {i}. {cat}{q['q']}")
        lines.append("")

        hints = phase.get("risk_hints", [])
        if hints:
            lines.append("  ⚠️ 风险提示:")
            for h in hints:
                lines.append(f"     • {h}")
            lines.append("")

    lines.append(f"{'='*60}")
    lines.append(f"  共 {len(phases)} 个阶段，{total_q} 个关键问题")
    lines.append(f"{'='*60}")

    return "\n".join(lines)


def generate_guide_report(result: dict) -> str:
    """从引导结果生成报告"""
    lines = []
    product = result.get("product", "未命名产品")

    lines.append(f"{'='*60}")
    lines.append(f"  📋 {product} — 项目引导报告")
    lines.append(f"  🕐 {result.get('timestamp', '')}")
    lines.append(f"{'='*60}")
    lines.append("")

    # 已回答的问题
    total_answered = 0
    for phase_id, phase_answers in result.get("answers", {}).items():
        if not phase_answers:
            continue
        lines.append(f"📍 {phase_id}:")
        for key, data in phase_answers.items():
            lines.append(f"  Q: {data['question']}")
            lines.append(f"  A: {data['answer']}")
            lines.append("")
            total_answered += 1

    # 跳过的问题（待确认事项）
    skipped = result.get("skipped", [])
    if skipped:
        lines.append(f"{'─'*50}")
        lines.append(f"❓ 待确认事项 ({len(skipped)} 项):")
        lines.append("")
        for s in skipped:
            lines.append(f"  • [{s['phase']}] {s['question']}")
        lines.append("")

    # 风险清单
    risks = result.get("risks", [])
    if risks:
        lines.append(f"{'─'*50}")
        lines.append(f"⚠️ 风险清单 ({len(risks)} 项):")
        lines.append("")
        for r in risks:
            lines.append(f"  • [{r['phase']}] {r['hint']}")
        lines.append("")

    # 统计
    lines.append(f"{'─'*50}")
    lines.append(f"📊 统计: 已回答 {total_answered} 项 | 待确认 {len(skipped)} 项 | 风险 {len(risks)} 项")

    return "\n".join(lines)
