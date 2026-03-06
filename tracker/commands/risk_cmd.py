"""风险命令: risk"""
import sys
from .. import core
from ..risk import assess_project_risk, format_risk_report


def _require():
    try:
        return core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_risk(args):
    p = _require()
    flow = core._project_as_flow(p)
    task_status = core._get_task_status(p)
    custom_estimates = p.get("estimates", {})
    result = assess_project_risk(flow, task_status, custom_estimates)

    phase_id = getattr(args, "phase", None)
    if phase_id:
        phase_id = phase_id.upper()
        phase_data = result["phase_risks"].get(phase_id)
        if not phase_data:
            print(f"❌ 阶段不存在或当前无风险数据: {phase_id}")
            sys.exit(1)

        print(f"\n📋 {p['name']} ({p['id']}) — 风险评估 [{phase_id}]\n")
        print(f"🔴 高风险: {phase_data['high']} 个  🟡 中风险: {phase_data['medium']} 个\n")
        for i, r in enumerate(phase_data["risks"][:10], 1):
            print(f"  {i}. {r['level']} [{r['task_id']}] {r['name']}  (分数: {r['score']})")
            if r["factors"]:
                print(f"     原因: {'; '.join(r['factors'])}")
        print()
        return

    print(f"\n📋 {p['name']} ({p['id']}) — 风险评估\n")
    print(format_risk_report(result))
