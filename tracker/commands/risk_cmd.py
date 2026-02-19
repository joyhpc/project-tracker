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

    print(f"\n📋 {p['name']} ({p['id']}) — 风险评估\n")

    result = assess_project_risk(flow, task_status, custom_estimates)
    print(format_risk_report(result))
