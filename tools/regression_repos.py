#!/usr/bin/env python3
"""跨仓只读回归检查工具。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tracker import core, onboard  # noqa: E402

EXCLUDE_FILES = {
    "onboard-prompt.md",
    "arch-prompt.md",
    "propose-prompt.md",
    "feasibility-report.md",
}
LOAD_SKIP_MARKERS = (
    "仓库中没有 .pt/ 目录",
    ".pt/ 目录中没有项目文件",
)


@contextmanager
def isolated_project_storage():
    old_projects_dir = core.PROJECTS_DIR
    old_config_file = core.CONFIG_FILE
    old_history_dir = core.HISTORY_DIR
    with tempfile.TemporaryDirectory(prefix="pt-regression-") as td:
        projects_dir = Path(td) / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        core.PROJECTS_DIR = projects_dir
        core.CONFIG_FILE = projects_dir / ".active"
        core.HISTORY_DIR = projects_dir / ".pt_history"
        try:
            yield projects_dir
        finally:
            core.PROJECTS_DIR = old_projects_dir
            core.CONFIG_FILE = old_config_file
            core.HISTORY_DIR = old_history_dir


def git_status_short(repo: Path) -> str | None:
    if not (repo / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--short"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def run_repo_checks(repo_path: str | Path) -> dict:
    repo = Path(repo_path).expanduser().resolve()
    result: dict = {
        "repo": repo.name,
        "path": str(repo),
        "ok": False,
    }
    if not repo.exists():
        result["error"] = f"路径不存在: {repo}"
        return result

    before_status = git_status_short(repo)
    result["git_repo"] = before_status is not None
    result["git_status_before"] = before_status or ""

    try:
        scan = onboard.scan_repo(str(repo))
        scan_paths = [Path(item["path"]) for item in scan["files"]]
        excluded_leaks = [
            str(path.relative_to(repo))
            for path in scan_paths
            if path.name in EXCLUDE_FILES or "prompts" in path.parts
        ]
        result["scan"] = {
            "files": len(scan["files"]),
            "reviews": len(scan["reviews"]),
            "decisions": len(scan["decisions"]),
            "pocs": len(scan["pocs"]),
            "docs": len(scan["docs"]),
            "excluded_leaks": excluded_leaks,
        }
        onboard_prompt = onboard.generate_onboard_prompt(str(repo), scan)
        arch_prompt = onboard.generate_arch_prompt(str(repo), scan)
        result["prompts"] = {
            "onboard_len": len(onboard_prompt),
            "arch_len": len(arch_prompt),
        }
    except Exception as exc:
        result["scan_error"] = f"{type(exc).__name__}: {exc}"

    pt_dir = repo / ".pt"
    result["pt_yaml_files"] = sorted(p.name for p in pt_dir.glob("*.yaml")) if pt_dir.exists() else []

    try:
        with isolated_project_storage() as projects_dir:
            project = core.load_from_repo(str(repo))
            project_id = project.get("id", "")
            saved_schema_version = None
            saved_reviews_type = None
            if project_id:
                saved_path = projects_dir / f"{project_id}.yaml"
                if saved_path.exists():
                    saved = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
                    saved_schema_version = saved.get("schema_version")
                    if saved.get("reviews"):
                        saved_reviews_type = type(saved["reviews"][0].get("verdicts", [])).__name__
            result["load_from_repo"] = {
                "status": "ok",
                "id": project.get("id"),
                "schema_version": project.get("schema_version"),
                "phase": project.get("phase"),
                "nodes": len(project.get("nodes", [])),
                "saved_schema_version": saved_schema_version,
                "saved_reviews_type": saved_reviews_type,
            }
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        status = "skip" if any(marker in str(exc) for marker in LOAD_SKIP_MARKERS) else "error"
        result["load_from_repo"] = {
            "status": status,
            "error": message,
        }

    after_status = git_status_short(repo)
    result["git_status_after"] = after_status or ""
    result["git_status_changed"] = before_status != after_status

    result["ok"] = (
        "scan_error" not in result
        and not result.get("scan", {}).get("excluded_leaks")
        and result["load_from_repo"]["status"] in {"ok", "skip"}
        and not result["git_status_changed"]
    )
    return result


def format_text(results: list[dict]) -> str:
    lines: list[str] = []
    passed = 0
    for item in results:
        status = "PASS" if item.get("ok") else "FAIL"
        if item.get("ok"):
            passed += 1
        load = item.get("load_from_repo", {})
        scan = item.get("scan", {})
        lines.append(
            f"[{status}] {item['repo']} scan={scan.get('files', 0)} reviews={scan.get('reviews', 0)} "
            f"decisions={scan.get('decisions', 0)} pocs={scan.get('pocs', 0)} "
            f"pt={len(item.get('pt_yaml_files', []))} load={load.get('status', 'n/a')}"
        )
        if "scan_error" in item:
            lines.append(f"  scan_error: {item['scan_error']}")
        if scan.get("excluded_leaks"):
            lines.append(f"  excluded_leaks: {', '.join(scan['excluded_leaks'])}")
        if load.get("status") == "error":
            lines.append(f"  load_error: {load['error']}")
        elif load.get("status") == "skip":
            lines.append(f"  load_skip: {load['error']}")
        elif load.get("status") == "ok":
            lines.append(
                f"  load_ok: id={load.get('id')} schema={load.get('schema_version')} "
                f"saved_schema={load.get('saved_schema_version')} nodes={load.get('nodes')}"
            )
        if item.get("git_status_changed"):
            lines.append("  git_status_changed: true")
    lines.append(f"SUMMARY {passed}/{len(results)} repos passed")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="对多个仓库执行 project-tracker 只读回归检查")
    parser.add_argument("repos", nargs="+", help="待检查的本地仓库路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = parser.parse_args()

    results = [run_repo_checks(repo) for repo in args.repos]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(format_text(results))
    return 0 if all(item.get("ok") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
