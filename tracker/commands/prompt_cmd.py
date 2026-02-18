"""Prompt 导出命令"""
import sys
from .. import core, flow as flowmod
from ..prompt import generate_prompt, list_templates


def _require():
    try:
        return core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_prompt(args):
    if args.list:
        print("\n📋 可用 Prompt 模板:\n")
        for t in list_templates():
            print(f"  [{t['key']}] {t['label']}")
        print(f"\n用法: pt prompt \"你的问题\"")
        print(f"      pt prompt -t accelerate")
        return

    p = _require()
    fl = flowmod.load_flow(p.get("flow", "duxin"))

    question = args.question or ""

    # 指定模板
    if args.template:
        question = question or args.template

    if not question:
        print("❌ 请输入问题: pt prompt \"如何最快推进项目？\"")
        sys.exit(1)

    result = generate_prompt(question, p, fl)

    print(f"\n{'='*60}")
    print(f"  🎯 Prompt 导出 — {result['template_label']}")
    print(f"  📋 {result['context_summary']}")
    print(f"{'='*60}")

    if args.system:
        print(f"\n--- System Prompt ---\n{result['system']}")

    print(f"\n--- Prompt ---\n{result['prompt']}")
    print(f"{'='*60}")

    # 复制到剪贴板（如果可用）
    if args.copy:
        try:
            import subprocess
            full = result['prompt']
            if args.system:
                full = f"System: {result['system']}\n\n{full}"
            subprocess.run(["xclip", "-selection", "clipboard"],
                          input=full.encode(), check=True, capture_output=True)
            print("📋 已复制到剪贴板")
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    # 保存到文件
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(f"System: {result['system']}\n\n{result['prompt']}")
        print(f"💾 已保存: {args.save}")
