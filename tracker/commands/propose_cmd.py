"""propose 命令: 基于已完成阶段的 review 回复，生成设计方案推荐 prompt

方向2架构：pt 负责组装上下文（BM25检索），LLM 负责理解和结构化。
工作流: pt review (收录完毕) → pt propose [--full] → 复制给超级LLM → 得到结构化方案 → 人工拍板
"""
import sys
import os
from pathlib import Path
from .. import core
from ..knowledge import parse_markdown, BM25


def cmd_propose(args):
    """propose 命令入口"""
    try:
        p = core.require_active()
        repo = core.get_repo_path(p)
        if not repo:
            print("❌ 未关联仓库。使用: pt docs --link <path>")
            sys.exit(1)

        reviews = p.get("reviews", [])
        decisions = p.get("decisions", [])
        pocs = p.get("pocs", [])

        if not reviews:
            print("❌ 没有已收录的回复。先用 pt review --add 收录。")
            sys.exit(1)

        # 1. 找出下一阶段待执行的任务
        nodes = p.get("nodes", [])
        ready_tasks = _find_ready_tasks(nodes)

        if not ready_tasks:
            print("❌ 没有可执行的任务。")
            sys.exit(1)

        # 2. 构建知识库（所有已收录回复）
        all_chunks = []
        for r in reviews:
            fpath = Path(repo) / r["file"]
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8")
                fname = os.path.basename(r["file"])
                task_id = r.get("task", "")
                chunks = parse_markdown(task_id, fname, content)
                all_chunks.extend(chunks)

        if not all_chunks:
            print("❌ 回复文件为空或不存在。")
            sys.exit(1)

        engine = BM25(all_chunks)

        # 3. 组装 prompt
        prompt = _build_prompt(p, ready_tasks, engine, reviews, decisions, pocs)

        # 4. 自动保存
        save_path = getattr(args, "save", None)
        if not save_path:
            phase = ready_tasks[0].get("phase", "").lower() if ready_tasks else ""
            phase_dir_map = {
                "concept": "docs/concept", "design": "docs/design",
                "proto": "docs/prototype", "test": "docs/test",
                "mass": "docs/production",
            }
            phase_dir = phase_dir_map.get(phase, "docs/design")
            save_path = os.path.join(str(repo), phase_dir, "propose-prompt.md")
        if not os.path.isabs(save_path):
            save_path = os.path.join(str(repo), save_path)
        parent_dir = os.path.dirname(save_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(prompt + "\n")
        rel = os.path.relpath(save_path, str(repo))

        # 5. 输出
        if getattr(args, "full", False):
            print("=" * 60)
            print("  📋 复制以下内容到超级 LLM")
            print("=" * 60)
            print()
            print(prompt)
            print()
            print("=" * 60)
        else:
            print(prompt)

        # 统计
        print(f"\n📄 已保存: {rel}")
        print(f"📊 基于 {len(reviews)} 份回复, {len(decisions)} 个已拍板决策")
        print(f"   待决策任务: {', '.join(t['name'] for t in ready_tasks)}")

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _find_ready_tasks(nodes):
    """找出可执行的任务（依赖已完成 or in_progress）"""
    done_ids = {n["id"] for n in nodes if n.get("status") == "done"}
    ready = []
    for n in nodes:
        if n.get("type") == "milestone":
            continue
        if n.get("status") == "in_progress":
            ready.append(n)
        elif n.get("status") == "pending":
            deps = n.get("depends", [])
            if deps and all(d in done_ids for d in deps):
                ready.append(n)
            elif not deps and done_ids:
                ready.append(n)
    return ready


def _build_prompt(project, ready_tasks, engine, reviews, decisions, pocs):
    """组装完整的 propose prompt"""
    lines = []

    # ── 角色 ──
    lines.append("**角色**：你是一位资深硬件产品架构师，精通从概念到量产的全流程技术选型。")
    lines.append("你的任务是基于前期可行性分析的多份 LLM 回复，为每个待决策项提取并整理所有备选方案，形成结构化的方案推荐文档。")
    lines.append("")

    # ── 项目背景 ──
    lines.append(f"**项目**：{project['name']}")
    lines.append("")

    # ── 已拍板决策（约束条件）──
    if decisions:
        lines.append("**已拍板决策（约束条件，方案必须兼容）**：")
        for d in decisions:
            status = d.get("status", "active")
            if status != "active":
                continue
            lines.append(f"- D{d['id']}: {d['title']} — {d.get('impact', '')}")
        lines.append("")

    # ── PoC 状态 ──
    if pocs:
        lines.append("**PoC 验证状态**：")
        for poc in pocs:
            icon = {"go": "🟢", "no-go": "🔴", "pending": "⏳", "caution": "🟡"}.get(poc["status"], "⚪")
            lines.append(f"- {icon} P{poc['id']}: {poc['title']} — 红线: {poc.get('metric', '')} — 状态: {poc['status']}")
        lines.append("")

    # ── 每个待决策任务的上下文 ──
    lines.append("---")
    lines.append("")
    lines.append("以下是每个待执行任务的相关 LLM 回复摘录（BM25 检索，按相关度排序）。")
    lines.append("请从中提取所有提到的备选方案、器件型号、架构选择、替代方案。")
    lines.append("")

    task_queries = []
    for task in ready_tasks:
        task_name = task.get("name", task["id"])
        deliverables = task.get("deliverables", [])
        lines.append(f"### 任务: {task_name}")
        if deliverables:
            lines.append(f"交付件: {', '.join(deliverables)}")
        lines.append("")

        # BM25 检索 — 多维度查询，合并去重
        queries = [
            f"{task_name} {' '.join(deliverables)} 方案 选型 架构",
            f"{task_name} 替代 备选 对比 推荐",
            f"{task_name} 成本 BOM 风险 对策",
        ]
        seen_contents = set()
        merged_results = []
        for q in queries:
            results = engine.search(q, top_k=6)
            for chunk in results:
                # 用内容前100字去重
                key = chunk.content[:100]
                if key not in seen_contents:
                    seen_contents.add(key)
                    merged_results.append(chunk)

        if merged_results:
            for i, chunk in enumerate(merged_results[:10], 1):
                source = f"[{chunk.task_name}]"
                if chunk.path:
                    source += f" {' > '.join(chunk.path)}"
                lines.append(f"<reference id=\"{task['id']}-ref{i}\" source=\"{source}\">")
                # 保留完整内容，让 LLM 理解上下文
                content = chunk.content
                if len(content) > 800:
                    content = content[:800] + "\n... (截断)"
                lines.append(content)
                lines.append("</reference>")
                lines.append("")
        else:
            lines.append("*未检索到相关内容。*")
            lines.append("")

        task_queries.append(task_name)

    # ── 输出要求 ──
    lines.append("---")
    lines.append("")
    lines.append("**你的任务**：")
    lines.append(f"基于以上 {len(reviews)} 份 LLM 回复的检索结果，为以下每个任务生成设计方案推荐。")
    lines.append("")
    lines.append("**待决策任务**：")
    for task in ready_tasks:
        lines.append(f"- {task.get('name', task['id'])}")
    lines.append("")
    lines.append("**输出格式要求**（严格遵守）：")
    lines.append("")
    lines.append("对每个任务，拆解为多个决策维度（如：主控选型、音频方案、传感器方案、阻尼材料...），每个维度：")
    lines.append("")
    lines.append("```")
    lines.append("### Qx: [决策维度名称]")
    lines.append("")
    lines.append("**方案 A: [方案名称]**")
    lines.append("- 来源: [哪份回复推荐的]")
    lines.append("- 关键参数: [具体型号/规格/数值]")
    lines.append("- 成本: ¥xx")
    lines.append("- 优势: ...")
    lines.append("- 劣势/风险: ...")
    lines.append("- 与已拍板决策的兼容性: [兼容/冲突/需调整]")
    lines.append("")
    lines.append("**方案 B: [方案名称]**")
    lines.append("- （同上格式）")
    lines.append("")
    lines.append("**推荐: 方案 X**")
    lines.append("理由: [结合已拍板决策、PoC状态、成本、风险的综合判断]")
    lines.append("```")
    lines.append("")
    lines.append("**关键规则**：")
    lines.append("1. 每个决策维度至少给出 2 种方案，尽量 3-4 种")
    lines.append("2. 方案必须来自回复原文，不要凭空编造。如果回复中只提到 1 种，标注\"回复中仅此方案，建议补充调研\"")
    lines.append("3. 必须标注来源（哪份回复、哪个章节）")
    lines.append("4. 成本必须给具体数字（从回复中提取），没有则标\"待确认\"")
    lines.append("5. 推荐理由必须引用已拍板决策编号（如 D1、D3）和 PoC 状态")
    lines.append("6. 最后给出待决策汇总表")
    lines.append("")
    lines.append("要求：中文回答，结论先行，方案对比必须有具体数值而非定性描述。")

    return "\n".join(lines)
