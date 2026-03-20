"""需求体系命令: req"""

from __future__ import annotations

import json
import sys

from .. import core
from . import _require


def _parse_subprojects(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _require_repo(project: dict):
    repo = core.get_repo_path(project)
    if not repo:
        print("❌ 项目未关联仓库。先运行: pt docs --link <path>")
        sys.exit(1)
    return repo


def _print_check(result: dict):
    counts = result.get("counts", {})
    icon = "✅" if result.get("valid") else "❌"
    print(f"{icon} requirements check | root={result.get('root')} | profile={result.get('profile')}")
    print(
        f"   critical={counts.get('critical', 0)}  error={counts.get('error', 0)}  warning={counts.get('warning', 0)}  info={counts.get('info', 0)}"
    )
    for issue in result.get("issues", []):
        issue_icon = {"critical": "🔴", "error": "❌", "warning": "⚠️", "info": "💡"}.get(issue.get("severity"), "•")
        print(f"   {issue_icon} {issue.get('message', issue)}")
    if not result.get("issues"):
        print("   无问题")


def _print_trace(result: dict):
    counts = result.get("counts", {})
    summary = result.get("summary", {})
    icon = "✅" if result.get("valid") else "❌"
    print(f"{icon} requirements trace | path={result.get('path')}")
    print(
        "   "
        f"rows={summary.get('rows', 0)}  "
        f"active_or_frozen={summary.get('active_or_frozen', 0)}  "
        f"missing_verification={summary.get('missing_verification', 0)}  "
        f"missing_conclusion={summary.get('missing_conclusion', 0)}"
    )
    print(
        "   "
        f"error={counts.get('error', 0)}  "
        f"warning={counts.get('warning', 0)}  "
        f"info={counts.get('info', 0)}  "
        f"write={result.get('write_status')}"
    )
    for issue in result.get("issues", []):
        issue_icon = {"critical": "🔴", "error": "❌", "warning": "⚠️", "info": "💡"}.get(issue.get("severity"), "•")
        print(f"   {issue_icon} {issue.get('message', issue)}")
    if not result.get("issues"):
        print("   无问题")


def cmd_req(args):
    if args.req_command == "init":
        _init(args)
    elif args.req_command == "index":
        _index(args)
    elif args.req_command == "trace":
        _trace(args)
    elif args.req_command == "check":
        _check(args)
    else:
        print("❌ req 需要子命令：init / index / trace / check")
        sys.exit(1)


def _init(args):
    project = _require()
    _require_repo(project)
    try:
        result = core.init_requirements(
            project["id"],
            profile=args.profile,
            root=args.root,
            subprojects=_parse_subprojects(args.subprojects),
            dry_run=args.dry_run,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    print("🔍 req init 试运行" if args.dry_run else "✅ req init 完成")
    print(f"   root: {result['root']}")
    print(f"   profile: {result['profile']}")
    print(f"   manifest: {result['manifest']}")
    if result.get("subprojects"):
        print("   subprojects: " + ", ".join(item["name"] for item in result["subprojects"]))
    print(f"   created: {len(result['created'])}")
    print(f"   skipped: {len(result['skipped'])}")
    print(f"   bindings: {len(result.get('bindings', {}))}")
    for item in result["created"][:10]:
        print(f"   + {item}")


def _index(args):
    project = _require()
    _require_repo(project)
    try:
        result = core.rebuild_requirements_indexes(project["id"], dry_run=args.dry_run)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    print("🔍 req index 试运行" if args.dry_run else "✅ req index 完成")
    print(f"   root: {result['root']}")
    print(f"   written: {len(result['created']) + len(result['updated'])}")
    for item in result["created"][:10]:
        print(f"   + {item}")
    for item in result["updated"][:10]:
        print(f"   ~ {item}")


def _check(args):
    project = _require()
    _require_repo(project)
    try:
        result = core.check_requirements(project["id"], strict=args.strict, save=not args.no_save)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_check(result)
    if not result.get("valid"):
        sys.exit(1)


def _trace(args):
    project = _require()
    _require_repo(project)
    try:
        result = core.trace_requirements(project["id"], dry_run=args.dry_run, save=not args.no_save)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_trace(result)
    if not result.get("valid"):
        sys.exit(1)
