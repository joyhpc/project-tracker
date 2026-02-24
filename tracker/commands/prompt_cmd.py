"""Prompt 导出命令"""
import sys
import os
import re
from .. import core
from ..prompt import generate_prompt, generate_deep_prompt, list_templates, auto_generate_questions


def cmd_prompt(args):
    if args.list:
        print("\n📋 支持的问题类型:\n")
        for t in list_templates():
            print(f"  [{t['key']}] {t['label']}")
            print(f"       例: pt prompt \"{t['example']}\"")
        return

    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    flow = core._project_as_flow(p)

    # --auto 模式
    if getattr(args, "auto", False):
        questions = auto_generate_questions(p, flow)
        if not questions:
            print("✅ 当前没有需要推进的问题。")
            return

        print(f"\n🧠 {p['name']} — 当前最有价值的 {len(questions)} 个问题\n")
        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q['priority']} {q['question']}")
            print(f"     ↳ 原因: {q['why']}")
            print()

        print("💡 使用: pt prompt \"复制上面的问题\" --full")
        return

    # --deep-all 模式：自动生成所有关键问题的 deep meta-prompt
    if getattr(args, "deep_all", False):
        _cmd_deep_all(p, flow, args)
        return

    question = args.question
    if not question:
        print('❌ 请输入问题，或使用 --auto 自动生成')
        sys.exit(1)

    result = generate_deep_prompt(question, p, flow) if getattr(args, "deep", False) else generate_prompt(question, p, flow)

    if getattr(args, "full", False):
        print("=" * 60)
        print("  📋 复制以下内容到超级 LLM")
        print("=" * 60)
        print()
        print(result["prompt"])
        print()
        print("=" * 60)
    else:
        print(result["prompt"])

    # 自动保存
    repo = core.get_repo_path(p)
    if repo:
        save_path = args.save if args.save else None
        if not save_path:
            # deep 模式保存到 meta/ 子目录
            is_deep = getattr(args, "deep", False)
            sub = "meta" if is_deep else ""
            prompt_dir = os.path.join(str(repo), "docs", "prompts", sub) if sub else os.path.join(str(repo), "docs", "prompts")
            os.makedirs(prompt_dir, exist_ok=True)
            # 找下一个序号
            existing = [f for f in os.listdir(prompt_dir) if f.endswith("-prompt.md") or f.endswith("-meta.md")]
            next_num = len(existing) + 1
            slug = _slugify(question)
            suffix = "meta" if is_deep else "prompt"
            save_path = os.path.join(prompt_dir, f"{next_num:02d}-{slug}-{suffix}.md")

        if not os.path.isabs(save_path):
            save_path = os.path.join(str(repo), save_path)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(result["prompt"] + "\n")
        rel = os.path.relpath(save_path, str(repo))
        print(f"\n📄 已保存: {rel}")


def _slugify(text, max_len=30):
    """从问题文本生成简短文件名"""
    # 去掉特殊字符，保留中文和英文
    text = re.sub(r'[^\w\u4e00-\u9fa5]', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    if len(text) > max_len:
        text = text[:max_len].rstrip('-')
    return text or "prompt"


def _cmd_deep_all(p, flow, args):
    """批量生成所有关键问题的 deep meta-prompt"""
    from ..prompt import generate_deep_prompt, auto_generate_questions

    questions = auto_generate_questions(p, flow)

    # 补充基于 review 的深度问题
    reviews = p.get("reviews", [])
    decisions = p.get("decisions", [])
    pocs = p.get("pocs", [])

    # 从 NO-GO 项生成问题
    for r in reviews:
        for v in r.get("verdicts", []):
            if v["verdict"] in ("NO-GO", "HIGH RISK"):
                q_text = f"{v['topic']}被判定为{v['verdict']}，如何解决？"
                if not any(v["topic"][:10] in q.get("question", "") for q in questions):
                    questions.append({
                        "priority": "🔴 NO-GO",
                        "question": q_text,
                        "why": f"来自 review: {v['verdict']}",
                    })

    # 从 PoC 生成问题
    for poc in pocs:
        if poc.get("status") == "pending":
            q_text = f"PoC验证项「{poc['title']}」的具体执行方案，红线: {poc.get('metric', '')}"
            if not any(poc["title"][:8] in q.get("question", "") for q in questions):
                questions.append({
                    "priority": "🧪 PoC",
                    "question": q_text,
                    "why": f"待验证 PoC",
                })

    # 去重，限制 5 个
    seen = set()
    unique = []
    for q in questions:
        key = q["question"][:30]
        if key not in seen:
            seen.add(key)
            unique.append(q)
    questions = unique[:5]

    if not questions:
        print("✅ 当前没有需要生成 deep prompt 的问题。")
        return

    repo = core.get_repo_path(p)
    if not repo:
        print("❌ 项目未关联仓库")
        return

    meta_dir = os.path.join(str(repo), "docs", "prompts", "meta")
    os.makedirs(meta_dir, exist_ok=True)

    # 清理旧的 meta 文件
    for f in os.listdir(meta_dir):
        if f.endswith("-meta.md"):
            os.remove(os.path.join(meta_dir, f))

    print(f"\n🧠 {p['name']} — 批量生成 {len(questions)} 个 deep meta-prompt\n")

    for i, q in enumerate(questions, 1):
        result = generate_deep_prompt(q["question"], p, flow)
        slug = _slugify(q["question"])
        save_path = os.path.join(meta_dir, f"{i:02d}-{slug}-meta.md")
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(result["prompt"] + "\n")
        rel = os.path.relpath(save_path, str(repo))
        print(f"  {i}. {q['priority']} {q['question'][:50]}...")
        print(f"     📄 {rel}")
        print()

    print(f"✅ 已生成 {len(questions)} 个 meta-prompt 到 docs/prompts/meta/")
    print(f"💡 下一步: 将 meta-prompt 喂给 LLM，生成 deep prompt 保存到 docs/prompts/deep/")
