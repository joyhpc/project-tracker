"""引导命令: guide"""
import sys
from ..guide import format_guide_overview, run_guide_interactive, generate_guide_report, get_phase_questions


def cmd_guide(args):
    product = args.product or ""

    if args.phase:
        phase_data = get_phase_questions(args.phase.upper(), product)
        if not phase_data:
            print(f"❌ 未找到阶段: {args.phase}")
            sys.exit(1)
        print(f"\n📍 {args.phase.upper()}: {phase_data['title']}\n")
        for i, q in enumerate(phase_data.get("questions", []), 1):
            cat = f"[{q.get('category', '')}] " if q.get("category") else ""
            print(f"  {i}. {cat}{q['q']}")
        hints = phase_data.get("risk_hints", [])
        if hints:
            print("\n  ⚠️ 风险提示:")
            for h in hints:
                print(f"     • {h}")
        print()
        return

    if args.overview:
        print(format_guide_overview(product))
        return

    result = run_guide_interactive(product, args.flow)
    report = generate_guide_report(result)
    print(f"\n{report}")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n💾 报告已保存: {args.save}")
