"""Prompt 导出命令"""
import sys
from .. import core
from ..prompt import generate_prompt, list_templates


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
    question = args.question
    if not question:
        print('❌ 请输入问题: pt prompt "PCB Layout 被阻塞了怎么办？"')
        sys.exit(1)

    result = generate_prompt(question, p, flow)

    if getattr(args, "full", False):
        # 完整输出：system + prompt，方便直接复制
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
