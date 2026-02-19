"""Prompt 导出命令"""
import sys
from .. import core
from ..prompt import generate_prompt, list_templates, auto_generate_questions


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

    # --auto 模式：自动生成问题
    if getattr(args, "auto", False):
        questions = auto_generate_questions(p, flow)
        if not questions:
            print("✅ 当前没有需要推进的问题。")
            return

        print(f"\n🧠 {p['name']} — 当前最有价值的 {len(questions)} 个问题\n")
        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q['priority']} {q['question']}")
            print(f"     ↳ 原因: {q['why']}")
            if q.get("hint"):
                print(f"     ↳ 提示: {q['hint']}")
            print()

        # 提示用户选择
        print("💡 使用方法:")
        print('   pt prompt "复制上面的问题" --full    → 生成完整 prompt')
        print('   pt prompt "复制上面的问题" --full --save prompt.md')
        return

    question = args.question
    if not question:
        print('❌ 请输入问题，或使用 --auto 自动生成')
        print('   pt prompt "概念设计怎么做" --full')
        print('   pt prompt --auto')
        sys.exit(1)

    result = generate_prompt(question, p, flow)

    if getattr(args, "full", False):
        print("=" * 60)
        print("  📋 复制以下内容到超级 LLM")
        print("=" * 60)
        print()
        print(f"[System Prompt]\n{result['system']}")
        print()
        print(f"[User Prompt]\n{result['prompt']}")
        print()
        print("=" * 60)
    else:
        if args.system:
            print(f"--- System ---\n{result['system']}\n")
        print(f"--- Prompt ---\n{result['prompt']}")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(f"[System Prompt]\n{result['system']}\n\n[User Prompt]\n{result['prompt']}\n")
        print(f"\n💾 已保存: {args.save}")
