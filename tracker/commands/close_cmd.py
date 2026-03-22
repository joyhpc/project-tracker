"""关闭门禁命令: close / close-check"""

from __future__ import annotations

import json
import sys

from .. import core


def _parse_evidence(values: list[str] | None) -> list[str]:
    result = []
    for value in values or []:
        for item in value.split(","):
            item = item.strip()
            if item:
                result.append(item)
    return result


def _print_check(result: dict):
    counts = result.get("counts", {})
    icon = "✅" if result.get("valid") else "❌"
    required = "yes" if result.get("required") else "no"
    print(f"{icon} close-check | task={result.get('task_id')} | required={required}")
    print(
        f"   critical={counts.get('critical', 0)}  error={counts.get('error', 0)}  warning={counts.get('warning', 0)}  info={counts.get('info', 0)}"
    )
    for issue in result.get("issues", []):
        issue_icon = {"critical": "🔴", "error": "❌", "warning": "⚠️", "info": "💡"}.get(issue.get("severity"), "•")
        print(f"   {issue_icon} {issue.get('message', issue)}")
    if result.get("valid") and result.get("required"):
        closure = result.get("closure", {})
        print(f"   formal_object_id: {closure.get('formal_object_id')}")
        if closure.get("sample_entity_id"):
            print(f"   sample_entity_id: {closure.get('sample_entity_id')}")
        if closure.get("borrowed_object_id"):
            print(f"   borrowed_object_id: {closure.get('borrowed_object_id')}")
        if closure.get("docs_anchor"):
            print(f"   docs_anchor: {closure.get('docs_anchor')}")
        print(f"   docs_backwrite_path: {closure.get('docs_backwrite_path')}")


def cmd_close(args):
    if args.close_command == "set":
        _set(args)
    elif args.close_command == "show":
        _show(args)
    elif args.close_command == "list":
        _list(args)
    elif args.close_command == "human":
        _human(args)
    elif args.close_command == "check":
        _check(args)
    else:
        print("❌ close 需要子命令：set / show / list / human / check")
        sys.exit(1)


def cmd_close_check(args):
    _check(args)


def _set(args):
    try:
        project = core.require_active()
        updates = {}
        mappings = {
            "conclusion": args.conclusion,
            "formal_object_id": args.formal_object_id,
            "formal_object": args.formal_object,
            "formal_object_class": args.formal_object_class,
            "borrowed_object_id": args.borrowed_object_id,
            "borrowed_object": args.borrowed_object,
            "borrowed_object_class": args.borrowed_object_class,
            "borrowed_purpose": args.borrowed_purpose,
            "scope": args.scope,
            "sample_entity_id": args.sample_entity_id,
            "sample_id": args.sample_id,
            "protocol_object_id": args.protocol_object_id,
            "protocol_object": args.protocol_object,
            "protocol_object_class": args.protocol_object_class,
            "firmware_version": args.firmware_version,
            "fpga_version": args.fpga_version,
            "pcb_version": args.pcb_version,
            "bom_version": args.bom_version,
            "docs_anchor": args.docs_anchor,
            "docs_backwrite_path": args.docs_backwrite_path,
            "docs_backwrite": args.docs_backwrite,
            "close_mode": args.close_mode,
        }
        for key, value in mappings.items():
            if value is not None:
                updates[key] = value
        evidence = _parse_evidence(args.evidence)
        if evidence:
            updates["evidence_paths"] = evidence
        need_human_check_fields = _parse_evidence(getattr(args, "need_human_check_fields", None))
        if need_human_check_fields:
            updates["need_human_check_fields"] = need_human_check_fields

        require = None
        if getattr(args, "require", False):
            require = True
        elif getattr(args, "optional", False):
            require = False

        result = core.update_task_closure(
            project["id"],
            args.task_id,
            updates=updates,
            clear_fields=args.clear,
            require=require,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"✅ close set | task={args.task_id}")
        if updates:
            print("   updated: " + ", ".join(sorted(updates.keys())))
        if args.clear:
            print("   cleared: " + ", ".join(args.clear))
        if require is True:
            print("   close_required: true")
        elif require is False:
            print("   close_required: false")
        _print_check(result["check"])


def _show(args):
    try:
        project = core.require_active()
        result = core.get_task_closure(project["id"], args.task_id)
    except (RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"📋 close show | task={args.task_id} | required={'yes' if result.get('required') else 'no'}")
        closure = result.get("closure", {})
        if closure:
            for key in (
                "conclusion",
                "formal_object_id",
                "formal_object",
                "formal_object_class",
                "sample_entity_id",
                "protocol_object_id",
                "protocol_object_class",
                "borrowed_object_id",
                "borrowed_object",
                "borrowed_object_class",
                "borrowed_purpose",
                "scope",
                "sample_id",
                "protocol_object",
                "firmware_version",
                "fpga_version",
                "pcb_version",
                "bom_version",
                "docs_anchor",
                "docs_backwrite_path",
                "docs_backwrite",
                "close_mode",
            ):
                if key in closure:
                    print(f"   {key}: {closure.get(key)}")
            if closure.get("evidence_paths"):
                print("   evidence_paths: " + ", ".join(closure["evidence_paths"]))
        if closure.get("need_human_check_fields"):
            print("   need_human_check_fields: " + ", ".join(closure["need_human_check_fields"]))
        human_fields = result.get("check", {}).get("closure", {}).get("need_human_check_fields", [])
        if human_fields:
            print("   human_fields: " + ", ".join(human_fields))
        else:
            print("   closure: {}")
        _print_check(result["check"])


def _list(args):
    try:
        project = core.require_active()
        result = core.list_close_gates(project["id"])
    except (RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    entries = result.get("entries", [])
    if getattr(args, "invalid_only", False):
        entries = [entry for entry in entries if not entry.get("valid")]

    if args.json:
        payload = dict(result)
        payload["entries"] = entries
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(
        f"📋 close list | required={result.get('required_count', 0)} | valid={result.get('valid_count', 0)} | invalid={result.get('invalid_count', 0)}"
    )
    if not entries:
        print("   暂无匹配任务")
        return
    for entry in entries:
        icon = "✅" if entry.get("valid") else "❌"
        print(
            f"   {icon} [{entry['task_id']}] {entry['name']} | phase={entry.get('phase')} | status={entry.get('status')} | issues={entry.get('issue_count')}"
        )
        if entry.get("close_mode"):
            print(f"      close_mode: {entry['close_mode']}")
        if entry.get("formal_object_id"):
            print(f"      formal_object_id: {entry['formal_object_id']}")
        if entry.get("sample_entity_id"):
            print(f"      sample_entity_id: {entry['sample_entity_id']}")
        if entry.get("protocol_object_id"):
            print(f"      protocol_object_id: {entry['protocol_object_id']}")
        if entry.get("docs_anchor"):
            print(f"      docs_anchor: {entry['docs_anchor']}")
        if entry.get("docs_backwrite_path"):
            print(f"      docs_backwrite_path: {entry['docs_backwrite_path']}")
        if entry.get("need_human_fields"):
            print("      need_human_fields: " + ", ".join(entry["need_human_fields"]))
        if entry.get("top_issues"):
            print("      top_issues: " + " | ".join(entry["top_issues"]))


def _human(args):
    try:
        project = core.require_active()
        result = core.get_close_human_template(project["id"], args.task_id)
    except (RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"🧩 close human | task={args.task_id} | valid={'yes' if result.get('valid') else 'no'}")
    if result.get("docs_anchor"):
        print(f"   docs_anchor: {result['docs_anchor']}")
    if result.get("docs_backwrite_path"):
        print(f"   docs_backwrite_path: {result['docs_backwrite_path']}")
    fields = result.get("fields", [])
    if not fields:
        print("   无需人工补充字段")
        return
    print("   need:")
    for field in fields:
        print(f"   - {field}")
    print("   template:")
    for field in fields:
        value = result.get("values", {}).get(field, "")
        if isinstance(value, list):
            print(f"   {field}:")
            for item in value or [""]:
                print(f"     - {item}")
        else:
            print(f"   {field}: {value}")


def _check(args):
    try:
        project = core.require_active()
        result = core.check_close_gate(project["id"], args.task_id)
    except (RuntimeError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_check(result)
    if not result.get("valid"):
        sys.exit(1)
