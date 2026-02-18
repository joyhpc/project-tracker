"""风险命令: risk"""
import sys
from .. import core, flow as flowmod
from ..risk import assess_project_risk, assess_phase_risk, format_risk_report


def _require():
    try:
        return core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_risk(args):
    p = _require()
    fl = flowmod.load_flow(p.get("flow", "duxin"))
    task_status = p.get("tasks", {})
    custom_estimates = p.get("estimates", {})

    print(f"\n📋 {p['name']} ({p['id']}) — 风险评估\n")

    if args.phase:
        phases = flowmod.get_phases(fl)
        phase = phases.get(args.phase.upper())
        if not phase:
            print(f"❌ 未找到阶段: {args.phase}")
            sys.exit(1)
        risks = assess_phase_risk(phase, task_status, custom_estimates)
        print(f"📍 {phase.get('name', '')}:\n")
        for r in risks:
            if r["score"] > 0:
                print(f"  {r['level']} [{r['task_id']}] {r['name']}  (分数: {r['score']})")
                if r["factors"]:
                    print(f"     {'; '.join(r['factors'])}")
    else:
        result = assess_project_risk(fl, p["current_phase"], task_status, custom_estimates)
        print(format_risk_report(result))
