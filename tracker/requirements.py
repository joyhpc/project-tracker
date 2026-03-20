"""Requirements scaffold / index / validation helpers."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml


DEFAULT_PROFILE = "hardware-platform"
DEFAULT_ROOT = "01_需求阶段_Requirements"
PROJECT_LEVEL_DIR = "00_项目级需求_Project_Level"
TRACE_MATRIX_COLUMNS = ["需求ID", "来源层级", "子项目/场景", "目标文档", "验证文档", "当前结论"]
APP_MATRIX_COLUMNS = ["应用目标ID", "应用场景", "用户价值", "平台能力", "约束/风险", "当前结论"]


def _template_dirs() -> list[Path]:
    candidates = [Path(__file__).resolve().parent / "templates" / "requirements"]
    return [path for path in candidates if path.exists()]


def _profile_dir(profile: str) -> Path:
    profile_key = profile.replace("-", "_")
    for base in _template_dirs():
        path = base / profile_key
        if path.exists():
            return path
    raise FileNotFoundError(f"requirements profile 不存在: {profile}")


def _load_manifest(profile: str) -> dict:
    manifest_path = _profile_dir(profile) / "manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"requirements manifest 不存在: {manifest_path}")
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}


def _render_template(profile: str, template_name: str, variables: dict[str, str]) -> str:
    template_path = _profile_dir(profile) / template_name
    content = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _slug_dir(index: int, name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]+", "_", name.strip()).strip("_") or f"subproject_{index:02d}"
    return f"{index:02d}_{safe.upper()}"


def normalize_subprojects(subprojects: list[str] | None, existing: list[dict] | None = None) -> list[dict]:
    if subprojects:
        result = []
        for index, raw in enumerate(subprojects, 1):
            name = raw.strip()
            if name:
                result.append({"name": name, "dir": _slug_dir(index, name)})
        return result
    if existing:
        result = []
        for index, item in enumerate(existing, 1):
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                directory = str(item.get("dir", "")).strip()
            else:
                name = str(item).strip()
                directory = ""
            if name:
                result.append({"name": name, "dir": directory or _slug_dir(index, name)})
        return result
    return []


def _relative_link(path: Path) -> str:
    return path.as_posix()


def _write_file(path: Path, content: str, *, overwrite: bool, dry_run: bool) -> str:
    existed = path.exists()
    if existed and not overwrite:
        return "skipped"
    if dry_run:
        return "updated" if existed and overwrite else "created"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return "updated" if existed and overwrite else "created"


def _build_root_index(project: dict, root_dir: Path, subproject_entries: list[dict]) -> str:
    project_blocks, other_blocks, loose_files = _scan_root_blocks(root_dir, subproject_entries)
    lines = [
        f"# {project['id']} 需求阶段索引",
        "",
        f"- 项目: {project['name']}",
        f"- Profile: {project.get('requirements', {}).get('profile', DEFAULT_PROFILE)}",
        f"- 更新日期: {_today()}",
        "",
        "## 项目级需求",
        "",
    ]
    if project_blocks:
        for block in project_blocks:
            lines.append(f"- [{block['name']}]({_relative_link(block['target'])})")
    else:
        lines.append(f"- [项目级目录]({_relative_link(Path(PROJECT_LEVEL_DIR) / 'README.md')})")
    lines.append("")
    if subproject_entries:
        lines.extend(["## 子项目", ""])
        for item in subproject_entries:
            lines.append(f"- [{item['name']}]({_relative_link(Path(item['dir']) / 'README.md')})")
        lines.append("")
    if other_blocks:
        lines.extend(["## 其他需求块", ""])
        for block in other_blocks:
            lines.append(f"- [{block['name']}]({_relative_link(block['target'])})")
        lines.append("")
    if loose_files:
        lines.extend(["## 根目录文档", ""])
        for file_path in loose_files:
            lines.append(f"- [{file_path.name}]({_relative_link(file_path)})")
        lines.append("")
    lines.extend([
        "## 说明",
        "",
        "- 本索引由 `pt req index` 自动维护。",
        "- 项目正文文档归属当前项目 repo。",
        "",
    ])
    return "\n".join(lines)


def _build_directory_readme(title: str, files: list[Path]) -> str:
    lines = [f"# {title}", "", f"- 更新日期: {_today()}", ""]
    lines.extend(["## 文档", ""])
    if files:
        for path in files:
            lines.append(f"- [{path.name}]({_relative_link(path)})")
    else:
        lines.append("- 暂无文档")
    lines.append("")
    return "\n".join(lines)


def _iter_markdown_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path.relative_to(directory) for path in directory.rglob("*.md") if path.name != "README.md")


def _patterns_for_item(item: dict, variables: dict[str, str]) -> list[str]:
    result = []
    for pattern in item.get("patterns", []) or []:
        rendered = pattern
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", value)
        result.append(rendered.lower())
    return result


def _find_by_patterns(directory: Path, patterns: list[str]) -> Path | None:
    if not directory.exists() or not patterns:
        return None
    for path in sorted(directory.rglob("*.md")):
        candidate = str(path.relative_to(directory)).lower()
        if any(pattern in candidate for pattern in patterns):
            return path
    return None


def _scan_root_blocks(root_dir: Path, subproject_entries: list[dict]) -> tuple[list[dict], list[dict], list[Path]]:
    project_blocks = []
    other_blocks = []
    loose_files = []
    known_sub_dirs = {entry["dir"] for entry in subproject_entries}
    if not root_dir.exists():
        return project_blocks, other_blocks, loose_files
    for child in sorted(root_dir.iterdir()):
        if child.name == PROJECT_LEVEL_DIR:
            target = child / "README.md" if (child / "README.md").exists() else child
            project_blocks.append({"name": child.name, "target": target.relative_to(root_dir)})
            continue
        if child.is_dir():
            if child.name in known_sub_dirs:
                continue
            target = child / "README.md" if (child / "README.md").exists() else child
            other_blocks.append({"name": child.name, "target": target.relative_to(root_dir)})
            continue
        if child.is_file() and child.suffix.lower() == ".md" and child.name != "README.md":
            loose_files.append(child.relative_to(root_dir))
    return project_blocks, other_blocks, loose_files


def init_requirements(
    project: dict,
    repo: Path,
    *,
    profile: str = DEFAULT_PROFILE,
    root: str = DEFAULT_ROOT,
    subprojects: list[dict] | None = None,
    dry_run: bool = False,
) -> dict:
    manifest = _load_manifest(profile)
    root_dir = repo / root
    project_level_dir = root_dir / PROJECT_LEVEL_DIR
    subproject_entries = normalize_subprojects(None, subprojects)
    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []

    base_vars = {
        "PROJECT_ID": project["id"],
        "PROJECT_NAME": project["name"],
        "DATE": _today(),
    }

    for item in manifest.get("project_level", []):
        rel_str = item["path"].replace("{{PROJECT_ID}}", project["id"])
        target = root_dir / rel_str
        alias = _find_by_patterns(project_level_dir, _patterns_for_item(item, base_vars))
        if alias and alias != target and not target.exists():
            skipped.append(str(alias.relative_to(root_dir)))
            continue
        content = _render_template(profile, item["template"], base_vars)
        status = _write_file(target, content, overwrite=False, dry_run=dry_run)
        if status == "created":
            created.append(rel_str)
        elif status == "updated":
            updated.append(rel_str)
        else:
            skipped.append(rel_str)

    for item in manifest.get("subproject", []):
        for entry in subproject_entries:
            variables = {
                **base_vars,
                "SUBPROJECT": entry["name"],
                "SUBPROJECT_DIR": entry["dir"],
            }
            rel_str = item["path"].replace("{{SUBPROJECT_DIR}}", entry["dir"]).replace("{{SUBPROJECT}}", entry["name"])
            target = root_dir / rel_str
            alias = _find_by_patterns(root_dir / entry["dir"], _patterns_for_item(item, variables))
            if alias and alias != target and not target.exists():
                skipped.append(str(alias.relative_to(root_dir)))
                continue
            content = _render_template(profile, item["template"], variables)
            status = _write_file(target, content, overwrite=False, dry_run=dry_run)
            if status == "created":
                created.append(rel_str)
            elif status == "updated":
                updated.append(rel_str)
            else:
                skipped.append(rel_str)

    index_result = rebuild_indexes(project, repo, root=root, subprojects=subproject_entries, dry_run=dry_run)
    created.extend(index_result["created"])
    updated.extend(index_result["updated"])

    return {
        "root": str(root_dir),
        "profile": profile,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "subprojects": subproject_entries,
    }


def rebuild_indexes(
    project: dict,
    repo: Path,
    *,
    root: str = DEFAULT_ROOT,
    subprojects: list[dict] | None = None,
    dry_run: bool = False,
) -> dict:
    root_dir = repo / root
    project_level_dir = root_dir / PROJECT_LEVEL_DIR
    entries = normalize_subprojects(None, subprojects)
    created: list[str] = []
    updated: list[str] = []

    root_status = _write_file(root_dir / "README.md", _build_root_index(project, root_dir, entries), overwrite=True, dry_run=dry_run)
    (updated if root_status == "updated" else created).append(str((root_dir / "README.md").relative_to(repo)))

    project_readme = project_level_dir / "README.md"
    project_status = _write_file(
        project_readme,
        _build_directory_readme(f"{project['id']} 项目级需求", _iter_markdown_files(project_level_dir)),
        overwrite=True,
        dry_run=dry_run,
    )
    (updated if project_status == "updated" else created).append(str(project_readme.relative_to(repo)))

    for entry in entries:
        sub_dir = root_dir / entry["dir"]
        readme = sub_dir / "README.md"
        sub_status = _write_file(
            readme,
            _build_directory_readme(f"{entry['name']} 需求索引", _iter_markdown_files(sub_dir)),
            overwrite=True,
            dry_run=dry_run,
        )
        (updated if sub_status == "updated" else created).append(str(readme.relative_to(repo)))

    return {"root": str(root_dir), "created": created, "updated": updated}


def _check_link_targets(root_dir: Path) -> list[dict]:
    issues = []
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in sorted(root_dir.rglob("*.md")):
        content = path.read_text(encoding="utf-8")
        for raw_target in pattern.findall(content):
            target = raw_target.strip()
            if not target or target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            plain_target = target.split("#", 1)[0]
            if not plain_target:
                continue
            resolved = (path.parent / plain_target).resolve()
            if not resolved.exists():
                issues.append({
                    "type": "broken_markdown_link",
                    "severity": "error",
                    "file": str(path.relative_to(root_dir)),
                    "message": f"{path.relative_to(root_dir)} 存在断链: {target}",
                })
    return issues


def _check_required_columns(path: Path, columns: list[str], issue_type: str) -> list[dict]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8")
    missing = [column for column in columns if column not in content]
    if not missing:
        return []
    return [{
        "type": issue_type,
        "severity": "error",
        "file": str(path.name),
        "message": f"{path.name} 缺少必需列: {', '.join(missing)}",
    }]


def check_requirements(project: dict, repo: Path, *, strict: bool = False) -> dict:
    req_state = project.get("requirements", {}) or {}
    profile = req_state.get("profile", DEFAULT_PROFILE)
    root = req_state.get("root", DEFAULT_ROOT)
    root_dir = repo / root
    subproject_entries = normalize_subprojects(None, req_state.get("subprojects", []))
    issues: list[dict] = []

    if not root_dir.exists():
        issues.append({
            "type": "missing_requirements_root",
            "severity": "error",
            "message": f"需求根目录不存在: {root}",
        })
        return _summarize_check(root, profile, issues)

    manifest = _load_manifest(profile)
    base_vars = {
        "PROJECT_ID": project["id"],
        "PROJECT_NAME": project["name"],
        "DATE": _today(),
    }
    for item in manifest.get("project_level", []):
        if not item.get("required"):
            continue
        rel_str = item["path"].replace("{{PROJECT_ID}}", project["id"])
        alias = _find_by_patterns(root_dir / PROJECT_LEVEL_DIR, _patterns_for_item(item, base_vars))
        if not (root_dir / rel_str).exists() and alias is None:
            issues.append({
                "type": "missing_required_doc",
                "severity": "error",
                "file": rel_str,
                "message": f"缺少必需文档: {rel_str}",
            })

    for entry in subproject_entries:
        for item in manifest.get("subproject", []):
            if not item.get("required"):
                continue
            rel_str = item["path"].replace("{{SUBPROJECT_DIR}}", entry["dir"]).replace("{{SUBPROJECT}}", entry["name"])
            alias = _find_by_patterns(
                root_dir / entry["dir"],
                _patterns_for_item(item, {**base_vars, "SUBPROJECT": entry["name"], "SUBPROJECT_DIR": entry["dir"]}),
            )
            if not (root_dir / rel_str).exists() and alias is None:
                issues.append({
                    "type": "missing_required_subproject_doc",
                    "severity": "error",
                    "file": rel_str,
                    "message": f"{entry['name']} 缺少必需文档: {rel_str}",
                })

    if not (root_dir / "README.md").exists():
        issues.append({
            "type": "missing_root_index",
            "severity": "error",
            "file": str(Path(root) / "README.md"),
            "message": "需求阶段索引页不存在",
        })

    trace_matrix = root_dir / PROJECT_LEVEL_DIR / f"{project['id']}_项目级需求追溯矩阵.md"
    issues.extend(_check_required_columns(trace_matrix, TRACE_MATRIX_COLUMNS, "trace_matrix_missing_columns"))

    current_conclusion = root_dir / PROJECT_LEVEL_DIR / f"{project['id']}_当前有效结论.md"
    if not current_conclusion.exists():
        issues.append({
            "type": "missing_current_conclusion",
            "severity": "error",
            "file": str(current_conclusion.relative_to(root_dir)),
            "message": "缺少当前有效结论文档",
        })

    for entry in subproject_entries:
        app_matrix = root_dir / entry["dir"] / f"{entry['name']}_应用目标矩阵.md"
        issues.extend(_check_required_columns(app_matrix, APP_MATRIX_COLUMNS, "app_matrix_missing_columns"))

    if strict:
        issues.extend(_check_link_targets(root_dir))

    return _summarize_check(root, profile, issues)


def _summarize_check(root: str, profile: str, issues: list[dict]) -> dict:
    counts = {
        "critical": sum(1 for item in issues if item.get("severity") == "critical"),
        "error": sum(1 for item in issues if item.get("severity") == "error"),
        "warning": sum(1 for item in issues if item.get("severity") == "warning"),
        "info": sum(1 for item in issues if item.get("severity") == "info"),
    }
    return {
        "root": root,
        "profile": profile,
        "issues": issues,
        "counts": counts,
        "valid": counts["critical"] == 0 and counts["error"] == 0,
    }
