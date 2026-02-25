"""review 命令: 管理超级 LLM 回复的收录与交叉验证

工作流: pt prompt → 投喂 LLM → 将回复保存为 {name}-result.md → pt review add → pt review analyze
"""
import sys
import os
import re
from pathlib import Path
from .. import core
from ..knowledge import parse_markdown, BM25, tokenize


def cmd_review(args):
    """review 命令入口"""
    if args.add:
        _add(args)
    elif args.approve:
        _approve(args)
    elif args.report:
        _report(args)
    elif args.analyze:
        _analyze(args)
    elif args.list:
        _list_reviews(args)
    else:
        _list_reviews(args)


def _add(args):
    """收录一份 LLM 回复到项目"""
    try:
        p = core.require_active()
        repo = core.get_repo_path(p)
        if not repo:
            print("❌ 未关联仓库。使用: pt docs --link <path>")
            sys.exit(1)

        filepath = args.add
        if not os.path.isabs(filepath):
            filepath = os.path.join(repo, filepath)

        if not os.path.exists(filepath):
            print(f"❌ 文件不存在: {filepath}")
            sys.exit(1)

        content = Path(filepath).read_text(encoding="utf-8")
        rel_path = os.path.relpath(filepath, repo)

        # 提取判定结论
        verdicts = _extract_verdicts(content)

        # 关联到任务
        task_id = args.task if hasattr(args, "task") and args.task else None

        review = {
            "file": rel_path,
            "task": task_id,
            "verdicts": verdicts,
            "source": args.source or "super-llm",
        }
        if hasattr(args, "unreviewed") and args.unreviewed:
            review["reviewed"] = False

        if "reviews" not in p:
            p["reviews"] = []
        # 去重
        p["reviews"] = [r for r in p["reviews"] if r["file"] != rel_path]
        p["reviews"].append(review)
        core._save(p)

        print(f"✅ 已收录: {rel_path}")
        if review.get("reviewed") is False:
            print(f"  ⚠️ 未审核 (--unreviewed)")
        if verdicts:
            for v in verdicts:
                icon = {"go": "🟢", "caution": "🟡", "no-go": "🔴"}.get(v["verdict"].lower(), "⚪")
                print(f"  {icon} {v['topic']}: {v['verdict']}")
        if task_id:
            print(f"  📎 关联任务: {task_id}")

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _approve(args):
    """批准审核一份回复"""
    try:
        p = core.require_active()
        reviews = p.get("reviews", [])
        target = args.approve

        found = False
        for r in reviews:
            if target in r["file"] or target == r["file"]:
                if r.get("reviewed") is False:
                    r.pop("reviewed")
                    core._save(p)
                    print(f"✅ 已审核通过: {r['file']}")
                else:
                    print(f"ℹ️ 已是审核状态: {r['file']}")
                found = True
                break

        if not found:
            # 尝试匹配序号
            if target.isdigit():
                idx = int(target) - 1
                if 0 <= idx < len(reviews):
                    r = reviews[idx]
                    if r.get("reviewed") is False:
                        r.pop("reviewed")
                        core._save(p)
                        print(f"✅ 已审核通过: {r['file']}")
                    else:
                        print(f"ℹ️ 已是审核状态: {r['file']}")
                    found = True

        if not found:
            print(f"❌ 未找到匹配的回复: {target}")
            print("  使用 pt review --list 查看所有回复")
            sys.exit(1)

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _extract_verdicts(content):
    """从回复内容中提取 GO/CAUTION/NO-GO 判定"""
    verdicts = []
    lines = content.split("\n")


    for i, line in enumerate(lines):
        # 匹配 "结论：GO" / "结论：【GO】" / "结论：CAUTION（...）" 等
        m = re.search(r'结论[：:]\s*[【\[]?\s*(GO|CAUTION|NO-GO|NO GO|HIGH RISK|CONDITIONAL GO|HIGHLY FEASIBLE)', line, re.IGNORECASE)
        if m:
            verdict = m.group(1).upper().replace("NO GO", "NO-GO")
            # 往上找最近的标题作为 topic
            topic = ""
            for j in range(i - 1, max(i - 10, -1), -1):
                if lines[j].strip().startswith("#") or re.match(r'^\d+\.', lines[j].strip()):
                    topic = re.sub(r'^[#\d.、\s]+', '', lines[j]).strip()
                    break
            if not topic:
                # 从结论行本身提取
                topic = line[:60].strip()

            verdicts.append({"topic": topic, "verdict": verdict})

    # 提取综合判定
    for line in lines:
        m = re.search(r'综合判定[：:]\s*[【\[]?\s*(.+?)[】\]]?\s*[（(]', line)
        if not m:
            m = re.search(r'综合判定[：:]\s*(.+?)(?:\s*[—\-]|$)', line)
        if m:
            verdicts.append({"topic": "📊 综合判定", "verdict": m.group(1).strip()})
            break

    return verdicts


def _analyze(args):
    """交叉验证分析所有已收录的回复"""
    try:
        p = core.require_active()
        repo = core.get_repo_path(p)
        reviews = p.get("reviews", [])

        if not reviews:
            print("❌ 没有已收录的回复。使用: pt review --add <file>")
            sys.exit(1)

        print(f"\n🔬 交叉验证分析 — {p['name']} ({len(reviews)} 份回复)\n")

        # 1. 判定汇总
        print("━━━ 判定汇总 ━━━")
        all_verdicts = []
        for r in reviews:
            fname = os.path.basename(r["file"])
            print(f"\n📄 {fname}")
            for v in core.normalize_verdicts(r.get("verdicts", [])):
                icon = {"GO": "🟢", "CAUTION": "🟡", "NO-GO": "🔴",
                         "HIGH RISK": "🔴", "CONDITIONAL GO": "🟡",
                         "HIGHLY FEASIBLE": "🟢"}.get(v["verdict"], "⚪")
                print(f"  {icon} {v['topic']}: {v['verdict']}")
                all_verdicts.append(v)

        # 2. 统计
        go = sum(1 for v in all_verdicts if v["verdict"] in ("GO", "HIGHLY FEASIBLE"))
        caution = sum(1 for v in all_verdicts if v["verdict"] in ("CAUTION", "CONDITIONAL GO"))
        nogo = sum(1 for v in all_verdicts if v["verdict"] in ("NO-GO", "HIGH RISK"))

        print(f"\n━━━ 统计 ━━━")
        print(f"🟢 GO: {go}  🟡 CAUTION: {caution}  🔴 NO-GO: {nogo}")

        # 3. 共识检测（BM25 找相似 topic）
        if len(reviews) >= 2 and repo:
            print(f"\n━━━ 跨回复共识 ━━━")
            all_chunks = []
            for r in reviews:
                fpath = Path(repo) / r["file"]
                if fpath.exists():
                    content = fpath.read_text(encoding="utf-8")
                    chunks = parse_markdown(r["file"], os.path.basename(r["file"]), content)
                    all_chunks.extend(chunks)

            if all_chunks:
                engine = BM25(all_chunks)
                # 用 NO-GO 的 topic 搜索其他回复中的相关内容
                nogo_topics = [v for v in all_verdicts if v["verdict"] in ("NO-GO", "HIGH RISK")]
                seen = set()
                for v in nogo_topics:
                    results = engine.search(v["topic"], top_k=3)
                    for chunk in results:
                        key = f"{chunk.task_name}:{chunk.path}"
                        if key not in seen and chunk.task_name != v["topic"]:
                            seen.add(key)
                            path_str = " > ".join(chunk.path) if chunk.path else ""
                            print(f"  ⚡ [{chunk.task_name}] {path_str}")

        # 4. 关键风险
        nogo_items = [v for v in all_verdicts if v["verdict"] in ("NO-GO", "HIGH RISK")]
        if nogo_items:
            print(f"\n━━━ 🔴 需要立即处理 ━━━")
            for v in nogo_items:
                print(f"  ❗ {v['topic']}")

        print()

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _list_reviews(args):
    """列出已收录的回复"""
    try:
        p = core.require_active()
        reviews = p.get("reviews", [])

        if not reviews:
            print("没有已收录的回复。使用: pt review --add <file>")
            return

        print(f"\n📋 {p['name']} — 已收录回复 ({len(reviews)})\n")
        for r in reviews:
            verdict_list = core.normalize_verdicts(r.get("verdicts", []))
            go = sum(1 for v in verdict_list if v["verdict"] in ("GO", "HIGHLY FEASIBLE"))
            caution = sum(1 for v in verdict_list if v["verdict"] in ("CAUTION", "CONDITIONAL GO"))
            nogo = sum(1 for v in verdict_list if v["verdict"] in ("NO-GO", "HIGH RISK"))
            summary = f"🟢{go} 🟡{caution} 🔴{nogo}" if verdict_list else "未分析"
            task = f" → [{r['task']}]" if r.get("task") else ""
            status = " ⚠️未审核" if r.get("reviewed") is False else ""
            print(f"  📄 {r['file']}{task}  {summary}{status}")

        print()

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _report(args):
    """生成可行性分析报告（汇总所有 review 的判定+决策+PoC）"""
    try:
        p = core.require_active()
        repo = core.get_repo_path(p)
        reviews = p.get("reviews", [])
        decisions = p.get("decisions", [])
        pocs = p.get("pocs", [])

        if not reviews:
            print("❌ 没有已收录的回复。先用 pt review --add 收录。")
            sys.exit(1)

        lines = [f"# 可行性分析报告 — {p['name']}\n"]

        # 未审核警告
        unreviewed = [r for r in reviews if r.get("reviewed") is False]
        if unreviewed:
            lines.append(f"> ⚠️ **{len(unreviewed)} 份回复未经人工审核**，仅供参考\n")

        # 一、判定汇总表
        lines.append("## 一、评估判定汇总\n")
        lines.append("| # | 评估主题 | 评估点 | 判定 |")
        lines.append("|---|---------|--------|------|")

        all_verdicts = []
        for i, r in enumerate(reviews, 1):
            fname = os.path.basename(r["file"]).replace("-result.md", "")
            unrev = " ⚠️" if r.get("reviewed") is False else ""
            for v in core.normalize_verdicts(r.get("verdicts", [])):
                if v["topic"].startswith("📊"):
                    continue
                icon = {"GO": "🟢", "CAUTION": "🟡", "NO-GO": "🔴",
                         "HIGH RISK": "🔴", "CONDITIONAL GO": "🟡",
                         "HIGHLY FEASIBLE": "🟢"}.get(v["verdict"], "⚪")
                lines.append(f"| {i} | {fname}{unrev} | {v['topic']} | {icon} {v['verdict']} |")
                all_verdicts.append(v)

        go = sum(1 for v in all_verdicts if v["verdict"] in ("GO", "HIGHLY FEASIBLE"))
        caution = sum(1 for v in all_verdicts if v["verdict"] in ("CAUTION", "CONDITIONAL GO"))
        nogo = sum(1 for v in all_verdicts if v["verdict"] in ("NO-GO", "HIGH RISK"))
        lines.append(f"\n**统计**：🟢 GO: {go}  🟡 CAUTION: {caution}  🔴 NO-GO: {nogo}\n")

        # 综合判定
        for r in reviews:
            for v in core.normalize_verdicts(r.get("verdicts", [])):
                if v["topic"].startswith("📊"):
                    fname = os.path.basename(r["file"]).replace("-result.md", "")
                    lines.append(f"- **{fname}** 综合判定：{v['verdict']}")

        # 二、关键风险（NO-GO 项）
        nogo_items = [v for v in all_verdicts if v["verdict"] in ("NO-GO", "HIGH RISK")]
        if nogo_items:
            lines.append("\n## 二、🔴 关键风险（需立即处理）\n")
            for v in nogo_items:
                lines.append(f"- **{v['topic']}**")
        else:
            lines.append("\n## 二、关键风险\n")
            lines.append("无 NO-GO 项。")

        # 三、架构决策
        if decisions:
            lines.append(f"\n## 三、架构决策（{len(decisions)} 项）\n")
            lines.append("| # | 决策 | 来源 | 影响 | 状态 |")
            lines.append("|---|------|------|------|------|")
            for d in decisions:
                icon = {"active": "🟢", "superseded": "⚫", "reverted": "🔴", "pending": "🟡"}.get(d.get("status", "active"), "⚪")
                lines.append(f"| D{d['id']} | {d['title']} | {d.get('source', '')} | {d.get('impact', '')} | {icon} {d.get('status', 'active')} |")

        # 四、PoC 验证项
        if pocs:
            lines.append(f"\n## 四、PoC 验证项（{len(pocs)} 项）\n")
            lines.append("| # | 验证项 | Go/No-Go 红线 | 状态 | 结果 |")
            lines.append("|---|--------|--------------|------|------|")
            for poc in pocs:
                icon = {"go": "🟢", "no-go": "🔴", "pending": "⏳", "caution": "🟡"}.get(poc["status"], "⚪")
                result = poc.get("result", "—")
                lines.append(f"| P{poc['id']} | {poc['title']} | {poc.get('metric', '')} | {icon} {poc['status']} | {result} |")

            poc_go = sum(1 for x in pocs if x["status"] == "go")
            poc_nogo = sum(1 for x in pocs if x["status"] == "no-go")
            poc_pending = sum(1 for x in pocs if x["status"] == "pending")
            lines.append(f"\n**PoC 状态**：🟢 GO: {poc_go}  🔴 NO-GO: {poc_nogo}  ⏳ 待验证: {poc_pending}")

        # 五、回复文件索引
        lines.append(f"\n## 五、详细分析文件\n")
        for r in reviews:
            lines.append(f"- [{os.path.basename(r['file'])}]({r['file']})")

        content = "\n".join(lines)

        # 保存
        save_path = args.report
        if save_path == "auto":
            if repo:
                task_id = reviews[0].get("task", "") or ""
                phase_dir = "docs/feasibility" if "feasib" in task_id else "docs"
                save_path = os.path.join(str(repo), phase_dir, "feasibility-report.md")
            else:
                save_path = "feasibility-report.md"

        if not os.path.isabs(save_path) and repo:
            save_path = os.path.join(str(repo), save_path)

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)

        rel = os.path.relpath(save_path, str(repo)) if repo else save_path
        print(f"📄 可行性分析报告已生成: {rel}")
        print(f"   评估项: {len(all_verdicts)}  决策: {len(decisions)}  PoC: {len(pocs)}")
        print(f"   判定: 🟢{go} 🟡{caution} 🔴{nogo}")

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)