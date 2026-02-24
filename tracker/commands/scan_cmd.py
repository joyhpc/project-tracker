"""扫描仓库文档 — 中途接入项目的自动识别与导入"""
import os
import re
import sys
from pathlib import Path
from .. import core


# 判定关键词
VERDICT_PATTERNS = re.compile(
    r'\b(GO|NO-GO|CAUTION|CONDITIONAL\s*GO|HIGH\s*RISK|HIGHLY\s*FEASIBLE)\b',
    re.IGNORECASE
)
DECISION_PATTERNS = re.compile(
    r'(决策|拍板|Decision|D[1-9]|已决定|确定方案|选定)',
    re.IGNORECASE
)
POC_PATTERNS = re.compile(
    r'(PoC|验证|红线|Go.No.Go|原型|Prototype|MVP)',
    re.IGNORECASE
)


def _scan_file(path):
    """扫描单个 markdown 文件，返回分类信息"""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return None

    lines = content.split("\n")
    title = ""
    for line in lines[:10]:
        m = re.match(r'^#\s+(.*)', line)
        if m:
            title = m.group(1).strip()
            break

    verdicts = VERDICT_PATTERNS.findall(content)
    has_decisions = bool(DECISION_PATTERNS.search(content))
    has_poc = bool(POC_PATTERNS.search(content))

    # 统计判定
    verdict_counts = {}
    for v in verdicts:
        v_upper = v.upper().replace(" ", "-")
        if v_upper == "CONDITIONAL-GO":
            v_upper = "CONDITIONAL GO"
        verdict_counts[v_upper] = verdict_counts.get(v_upper, 0) + 1

    file_type = "doc"
    if verdict_counts:
        file_type = "review"
    elif has_decisions:
        file_type = "decision"
    elif has_poc:
        file_type = "poc"

    return {
        "path": str(path),
        "title": title,
        "type": file_type,
        "size": len(content),
        "lines": len(lines),
        "verdicts": verdict_counts,
        "has_decisions": has_decisions,
        "has_poc": has_poc,
    }


def cmd_scan(args):
    # 确定仓库路径
    repo = args.repo
    if not repo:
        try:
            p = core.require_active()
            repo = p.get("repo", "")
        except RuntimeError:
            pass

    if not repo:
        print("❌ 请指定仓库路径: pt scan --repo /path/to/repo")
        sys.exit(1)

    repo = Path(repo)
    if not repo.exists():
        print(f"❌ 路径不存在: {repo}")
        sys.exit(1)

    # 扫描所有 markdown 文件
    md_files = sorted(repo.rglob("*.md"))
    # 排除 .git, node_modules, .pt 等
    md_files = [f for f in md_files if not any(
        p in f.parts for p in [".git", "node_modules", ".pt", "__pycache__"]
    )]

    if not md_files:
        print(f"📂 {repo} 中没有找到 markdown 文件")
        return

    results = []
    for f in md_files:
        info = _scan_file(f)
        if info:
            results.append(info)

    # 分类统计
    reviews = [r for r in results if r["type"] == "review"]
    decisions = [r for r in results if r["has_decisions"]]
    pocs = [r for r in results if r["has_poc"]]
    docs = [r for r in results if r["type"] == "doc"]

    print(f"\n📂 扫描: {repo}")
    print(f"   文件总数: {len(results)}")
    print()

    # 显示发现的 review 文件
    if reviews:
        print(f"📋 发现 {len(reviews)} 个可能的 review 文件（含 GO/NO-GO/CAUTION 判定）:\n")
        for r in reviews:
            rel = os.path.relpath(r["path"], repo)
            v_str = " ".join(f"{k}:{v}" for k, v in r["verdicts"].items())
            icon = "🔴" if "NO-GO" in r["verdicts"] else "🟡" if "CAUTION" in r["verdicts"] else "🟢"
            print(f"  {icon} {rel}")
            if r["title"]:
                print(f"     标题: {r['title']}")
            print(f"     判定: {v_str}")
            print()

    # 显示含决策的文件
    if decisions:
        print(f"📌 发现 {len(decisions)} 个含决策内容的文件:\n")
        for d in decisions:
            rel = os.path.relpath(d["path"], repo)
            print(f"  📄 {rel} — {d['title'] or '(无标题)'}")
        print()

    # 显示含 PoC 的文件
    if pocs:
        print(f"🧪 发现 {len(pocs)} 个含 PoC/验证内容的文件:\n")
        for p_item in pocs:
            rel = os.path.relpath(p_item["path"], repo)
            print(f"  🔬 {rel} — {p_item['title'] or '(无标题)'}")
        print()

    # 其他文档
    other = [d for d in docs if not d["has_decisions"] and not d["has_poc"]]
    if other:
        print(f"📄 其他文档 ({len(other)}):\n")
        for d in other[:10]:
            rel = os.path.relpath(d["path"], repo)
            print(f"  📄 {rel} — {d['title'] or '(无标题)'} ({d['lines']}行)")
        if len(other) > 10:
            print(f"  ... 还有 {len(other) - 10} 个")
        print()

    # --auto-register: 自动注册 review 文件
    if getattr(args, "auto_register", False) and reviews:
        try:
            p = core.require_active()
        except RuntimeError as e:
            print(f"❌ 自动注册需要先激活项目: {e}")
            return

        registered = 0
        existing = {r["file"] for r in p.get("reviews", [])}
        for r in reviews:
            rel = os.path.relpath(r["path"], repo)
            if rel not in existing:
                # 调用 review --add 的逻辑
                from .review_cmd import _register_review
                ok = _register_review(p, rel)
                if ok:
                    registered += 1

        if registered:
            core.save_project(p)
            print(f"\n✅ 自动注册了 {registered} 个 review 文件")
        else:
            print("\n✅ 所有 review 文件已注册，无需操作")

    # --onboard: 生成项目导入 prompt
    if getattr(args, "onboard", False):
        _generate_onboard_prompt(repo, results, reviews, decisions, pocs)

    # 提示下一步
    if not getattr(args, "auto_register", False) and reviews:
        print("💡 下一步:")
        print("  pt scan --auto-register  — 自动注册所有 review 文件")
        print("  pt scan --onboard        — 生成项目导入 prompt（喂给 LLM 生成项目配置）")


def _generate_onboard_prompt(repo, results, reviews, decisions, pocs):
    """生成项目导入 prompt"""
    lines = []
    lines.append("**角色**：你是一位项目管理专家，精通硬件产品开发全流程。")
    lines.append("你的任务是：基于以下已有项目文档，生成一个 project-tracker 项目配置文件（YAML 格式）。")
    lines.append("")
    lines.append("## 已有文档清单")
    lines.append("")

    for r in results:
        rel = os.path.relpath(r["path"], repo)
        type_icon = {"review": "📋", "decision": "📌", "poc": "🧪", "doc": "📄"}.get(r["type"], "📄")
        extra = ""
        if r["verdicts"]:
            extra = f" [{' '.join(f'{k}:{v}' for k, v in r['verdicts'].items())}]"
        lines.append(f"- {type_icon} `{rel}` — {r['title'] or '(无标题)'}{extra}")

    lines.append("")

    # 注入 review 文件的摘要内容
    if reviews:
        lines.append("## Review 文件内容摘要")
        lines.append("")
        for r in reviews[:5]:
            rel = os.path.relpath(r["path"], repo)
            try:
                content = Path(r["path"]).read_text(encoding="utf-8")
                # 取前 1500 字符
                if len(content) > 1500:
                    content = content[:1500] + "\n... (截断)"
                lines.append(f"<file path=\"{rel}\">")
                lines.append(content)
                lines.append("</file>")
                lines.append("")
            except Exception:
                pass

    lines.append("## 你的任务")
    lines.append("")
    lines.append("基于以上文档，生成以下内容：")
    lines.append("")
    lines.append("1. **项目名称和 ID**")
    lines.append("2. **当前阶段判断**（概念/设计/原型/测试/量产）")
    lines.append("3. **已完成任务列表**（每个任务附 note 摘要）")
    lines.append("4. **已拍板决策列表**（从文档中提取）")
    lines.append("5. **PoC 验证项**（如果有）")
    lines.append("6. **下一步建议**")
    lines.append("")
    lines.append("输出格式：直接给出可执行的 pt 命令序列，例如：")
    lines.append("```bash")
    lines.append("pt init PROJECT_ID --name \"项目名称\" --repo /path/to/repo")
    lines.append("pt done market_research --note \"市场调研完成:...\" --force")
    lines.append("pt review --add docs/feasibility/01-xxx-result.md")
    lines.append("pt decision --add \"决策标题\" --source feasibility-01 --impact \"影响\"")
    lines.append("pt poc --add \"验证项\" --metric \"红线指标\"")
    lines.append("```")

    prompt_text = "\n".join(lines)
    print("\n" + "=" * 60)
    print("  📋 项目导入 Prompt（复制给 LLM）")
    print("=" * 60)
    print()
    print(prompt_text)

    # 保存
    save_path = repo / "docs" / "onboard-prompt.md"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(prompt_text, encoding="utf-8")
    print(f"\n📄 已保存: {os.path.relpath(save_path, repo)}")
