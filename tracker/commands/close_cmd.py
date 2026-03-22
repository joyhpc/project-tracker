"""关闭门禁命令: close-check"""

from __future__ import annotations

import json
import sys

from .. import core


def cmd_close_check(args):
    try:
        project = core.require_active()
        result = core.check_close_gate(project["id"], args.task_id)
    except (RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        counts = result.get("counts", {})
        icon = "✅" if result.get("valid") else "❌"
        required = "yes" if result.get("required") else "no"
        print(f"{icon} close-check | task={args.task_id} | required={required}")
        print(
            f"   critical={counts.get('critical', 0)}  error={counts.get('error', 0)}  warning={counts.get('warning', 0)}  info={counts.get('info', 0)}"
        )
        for issue in result.get("issues", []):
            issue_icon = {"critical": "🔴", "error": "❌", "warning": "⚠️", "info": "💡"}.get(issue.get("severity"), "•")
            print(f"   {issue_icon} {issue.get('message', issue)}")
        if result.get("valid") and result.get("required"):
            closure = result.get("closure", {})
            print(f"   formal_object: {closure.get('formal_object')}")
            if closure.get("borrowed_object"):
                print(f"   borrowed_object: {closure.get('borrowed_object')}")
            print(f"   docs_backwrite: {closure.get('docs_backwrite')}")
    if not result.get("valid"):
        sys.exit(1)
