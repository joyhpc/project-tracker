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
            # 自动生成文件名：按序号递增
            prompt_dir = os.path.join(str(repo), "docs", "prompts")
            os.makedirs(prompt_dir, exist_ok=True)
            # 找下一个序号
            existing = [f for f in os.listdir(prompt_dir) if f.endswith("-prompt.md")]
            next_num = len(existing) + 1
            # 从问题中提取简短文件名
            slug = _slugify(question)
            save_path = os.path.join(prompt_dir, f"{next_num:02d}-{slug}-prompt.md")

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
