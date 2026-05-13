"""Read-only health checks for the pt workspace."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import core
from ..repo_boundary import find_root_boundary_violations


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _aggregate_counts(results: list[dict]) -> dict:
    counts = {"critical": 0, "error": 0, "warning": 0, "info": 0}
    for result in results:
        for key in counts:
            counts[key] += result.get("counts", {}).get(key, 0)
    return counts


def collect_doctor_report(*, strict: bool = False) -> dict:
    """Collect read-only repo and project health checks."""
    root = _repo_root()
    boundary_violations = find_root_boundary_violations(root)
    project_results = core.validate_all_projects()
    counts = _aggregate_counts(project_results)

    active_id = core._get_active()
    active = {"id": active_id, "loaded": False, "repo": "", "repo_exists": False}
    if active_id:
        project = core._load(active_id)
        active["loaded"] = bool(project)
        if project:
            active["repo"] = project.get("repo", "") or ""
            active["repo_exists"] = bool(core.get_repo_path(project))

    has_errors = bool(boundary_violations) or counts["critical"] > 0 or counts["error"] > 0
    has_warnings = counts["warning"] > 0
    return {
        "version": 1,
        "root": str(root),
        "strict": strict,
        "valid": not has_errors and not (strict and has_warnings),
        "active": active,
        "repo_boundary": {
            "valid": not boundary_violations,
            "violations": boundary_violations,
        },
        "projects": {
            "count": len(project_results),
            "counts": counts,
            "results": project_results,
        },
    }


def _print_doctor_report(report: dict, *, verbose: bool = False) -> None:
    counts = report["projects"]["counts"]
    boundary = report["repo_boundary"]
    active = report["active"]

    print(f"pt doctor | root={report['root']}")
    print(f"repo boundary: {'OK' if boundary['valid'] else 'FAIL'}")
    for violation in boundary["violations"][:10]:
        print(f"  - {violation['message']}")

    active_bits = [active.get("id") or "-"]
    if active.get("repo"):
        active_bits.append(f"repo={active['repo']}")
        active_bits.append("repo_exists=yes" if active.get("repo_exists") else "repo_exists=no")
    print("active project: " + " | ".join(active_bits))

    print(
        "projects: "
        f"{report['projects']['count']} | "
        f"critical={counts['critical']} error={counts['error']} "
        f"warning={counts['warning']} info={counts['info']}"
    )

    issue_projects = [
        item for item in report["projects"]["results"]
        if item.get("counts", {}).get("critical", 0) or item.get("counts", {}).get("error", 0)
    ]
    for item in issue_projects:
        item_counts = item.get("counts", {})
        print(
            f"  - {item.get('project_id')}: "
            f"critical={item_counts.get('critical', 0)} error={item_counts.get('error', 0)}"
        )

    if verbose:
        for item in report["projects"]["results"]:
            issues = item.get("issues", [])
            if not issues:
                continue
            print(f"\n{item.get('project_id')}:")
            for issue in issues[:10]:
                print(f"  [{issue.get('severity')}] {issue.get('message', issue)}")

    print("status: " + ("OK" if report["valid"] else "FAIL"))


def cmd_doctor(args) -> None:
    report = collect_doctor_report(strict=getattr(args, "strict", False))
    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_doctor_report(report, verbose=getattr(args, "verbose", False))
    if not report["valid"]:
        counts = report["projects"]["counts"]
        has_errors = (
            not report["repo_boundary"]["valid"]
            or counts.get("critical", 0) > 0
            or counts.get("error", 0) > 0
        )
        sys.exit(2 if has_errors else 1)
