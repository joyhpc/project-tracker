"""Requirements scaffold / binding / validation helpers."""

from __future__ import annotations

import copy
import re
from datetime import datetime
from pathlib import Path

import yaml


DEFAULT_PROFILE = "hardware-platform"
DEFAULT_ROOT = "01_需求阶段_Requirements"
PROJECT_LEVEL_DIR = "00_项目级需求_Project_Level"
MANIFEST_REL_PATH = Path(".pt") / "requirements_manifest.yaml"

TRACE_MATRIX_COLUMNS = [
    "需求ID",
    "版本",
    "状态",
    "Baseline",
    "Supersedes",
    "来源层级",
    "子项目/场景",
    "目标文档",
    "验证文档",
    "当前结论",
]
APP_MATRIX_COLUMNS = ["应用目标ID", "应用场景", "用户价值", "平台能力", "约束/风险", "当前结论"]
VALID_DOC_STATUSES = {"Draft", "Reviewing", "Active", "Frozen", "Obsoleted"}
REQUIRED_DOC_METADATA = ("pt_role", "id", "version", "status", "baseline")


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
            if isinstance(raw, dict):
                name = str(raw.get("name", "")).strip()
                directory = str(raw.get("dir", "")).strip()
            else:
                name = str(raw).strip()
                directory = ""
            if name:
                result.append({"name": name, "dir": directory or _slug_dir(index, name)})
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


def _manifest_path(repo: Path) -> Path:
    return repo / MANIFEST_REL_PATH


def _default_repo_manifest(profile: str = DEFAULT_PROFILE, root: str = DEFAULT_ROOT) -> dict:
    return {
        "profile": profile,
        "root": root,
        "subprojects": [],
        "bindings": {},
    }


def load_repo_manifest(repo: Path) -> dict:
    path = _manifest_path(repo)
    if not path.exists():
        return _default_repo_manifest()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    manifest = _default_repo_manifest(
        profile=str(loaded.get("profile", DEFAULT_PROFILE) or DEFAULT_PROFILE),
        root=str(loaded.get("root", DEFAULT_ROOT) or DEFAULT_ROOT),
    )
    manifest["subprojects"] = normalize_subprojects(None, loaded.get("subprojects", []))
    bindings = loaded.get("bindings", {}) or {}
    if isinstance(bindings, dict):
        manifest["bindings"] = copy.deepcopy(bindings)
    return manifest


def _save_repo_manifest(repo: Path, manifest: dict, *, dry_run: bool = False) -> Path:
    path = _manifest_path(repo)
    if dry_run:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _base_template_vars(project: dict, role_id: str, *, subproject: dict | None = None) -> dict[str, str]:
    role_token = re.sub(r"[^A-Za-z0-9]+", "_", role_id).strip("_").upper()
    if subproject:
        subject = f"{project['id']}-{subproject['name']}-{role_token}"
    else:
        subject = f"{project['id']}-{role_token}"
    variables = {
        "PROJECT_ID": project["id"],
        "PROJECT_NAME": project["name"],
        "DATE": _today(),
        "ROLE_ID": role_id,
        "DOC_ID": subject,
        "DOC_VERSION": "1.0",
        "DOC_STATUS": "Draft",
        "DOC_BASELINE": "draft",
        "DOC_SUPERSEDES": "",
    }
    if subproject:
        variables["SUBPROJECT"] = subproject["name"]
        variables["SUBPROJECT_DIR"] = subproject["dir"]
        variables["DOC_ID"] = subject
    return variables


def _parse_frontmatter(path: Path) -> tuple[dict, str]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        return {}, content
    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, content
    raw_meta = parts[0][4:]
    body = parts[1]
    try:
        metadata = yaml.safe_load(raw_meta) or {}
    except yaml.YAMLError:
        return {}, content
    if not isinstance(metadata, dict):
        return {}, content
    return metadata, body


def _dump_frontmatter(metadata: dict, body: str) -> str:
    header = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{header}\n---\n\n{body.lstrip()}"


def _required_metadata(variables: dict[str, str], *, project_id: str, role_id: str, subproject: str | None = None) -> dict:
    metadata = {
        "pt_role": role_id,
        "pt_project": project_id,
        "id": variables["DOC_ID"],
        "version": variables["DOC_VERSION"],
        "status": variables["DOC_STATUS"],
        "baseline": variables["DOC_BASELINE"],
        "supersedes": variables["DOC_SUPERSEDES"] or None,
    }
    if subproject:
        metadata["pt_subproject"] = subproject
    return metadata


def _ensure_doc_metadata(path: Path, required: dict, *, dry_run: bool) -> bool:
    current_meta, body = _parse_frontmatter(path)
    changed = False

    if not current_meta:
        next_meta = copy.deepcopy(required)
        changed = True
    else:
        next_meta = copy.deepcopy(current_meta)
        for key, value in required.items():
            if key.startswith("pt_"):
                if next_meta.get(key) != value:
                    next_meta[key] = value
                    changed = True
                continue
            if next_meta.get(key) in (None, ""):
                next_meta[key] = value
                changed = True

    if changed and not dry_run:
        path.write_text(_dump_frontmatter(next_meta, body if current_meta else path.read_text(encoding="utf-8")), encoding="utf-8")
    return changed


def _patterns_for_item(item: dict, variables: dict[str, str]) -> list[str]:
    result = []
    for pattern in item.get("patterns", []) or []:
        rendered = pattern
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", value)
        result.append(rendered.lower())
    return result


def _discover_by_metadata(directory: Path, role_id: str, *, project_id: str, subproject: str | None = None) -> Path | None:
    if not directory.exists():
        return None
    matches = []
    for path in sorted(directory.rglob("*.md")):
        metadata, _ = _parse_frontmatter(path)
        if metadata.get("pt_role") != role_id:
            continue
        if str(metadata.get("pt_project", "")).strip() not in {"", project_id}:
            continue
        if subproject is not None and str(metadata.get("pt_subproject", "")).strip() not in {"", subproject}:
            continue
        matches.append(path)
    return matches[0] if matches else None


def _discover_by_patterns(directory: Path, patterns: list[str]) -> Path | None:
    if not directory.exists() or not patterns:
        return None
    for path in sorted(directory.rglob("*.md")):
        candidate = str(path.relative_to(directory)).lower()
        if any(pattern in candidate for pattern in patterns):
            return path
    return None


def _binding_key(role_id: str, subproject: str | None = None) -> str:
    return f"{role_id}@{subproject}" if subproject else role_id


def _binding_rel_path(root: str, item: dict, variables: dict[str, str]) -> str:
    rel_str = item["path"]
    for key, value in variables.items():
        rel_str = rel_str.replace(f"{{{{{key}}}}}", value)
    return str(Path(root) / rel_str)


def _discover_existing_binding(
    repo: Path,
    root: str,
    item: dict,
    variables: dict[str, str],
    *,
    project_id: str,
    subproject: str | None = None,
) -> Path | None:
    scope_dir = repo / root / PROJECT_LEVEL_DIR if subproject is None else repo / root / variables["SUBPROJECT_DIR"]
    by_meta = _discover_by_metadata(scope_dir, item["id"], project_id=project_id, subproject=subproject)
    if by_meta:
        return by_meta
    return _discover_by_patterns(scope_dir, _patterns_for_item(item, variables))


def _build_binding_entry(item: dict, rel_path: str, *, subproject: dict | None = None, discovered_by: str = "manifest") -> dict:
    entry = {
        "role_id": item["id"],
        "path": rel_path,
        "scope": "subproject" if subproject else "project",
        "discovered_by": discovered_by,
    }
    if subproject:
        entry["subproject"] = subproject["name"]
    return entry


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


def _build_root_index(project: dict, root_dir: Path, subproject_entries: list[dict], bindings: dict[str, dict]) -> str:
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

    project_bindings = [item for item in bindings.values() if item.get("scope") == "project"]
    if project_bindings:
        for entry in sorted(project_bindings, key=lambda item: item.get("role_id", "")):
            path = Path(entry["path"])
            lines.append(f"- [{entry['role_id']}]({_relative_link(path)})")
    elif project_blocks:
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
        f"- 角色绑定真理源: `{MANIFEST_REL_PATH.as_posix()}`",
        "- `pt req init` 会在首次接入时自动发现并固化绑定。",
        "- `pt req check / index` 运行期只认显式绑定，不再靠文件名猜测。",
        "",
    ])
    return "\n".join(lines)


def _build_directory_readme(title: str, files: list[Path]) -> str:
    lines = [f"# {title}", "", f"- 更新日期: {_today()}", "", "## 文档", ""]
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


def init_requirements(
    project: dict,
    repo: Path,
    *,
    profile: str = DEFAULT_PROFILE,
    root: str = DEFAULT_ROOT,
    subprojects: list[dict] | None = None,
    dry_run: bool = False,
) -> dict:
    manifest_def = _load_manifest(profile)
    repo_manifest = load_repo_manifest(repo)
    repo_manifest["profile"] = profile
    repo_manifest["root"] = root
    repo_manifest["subprojects"] = normalize_subprojects(subprojects, repo_manifest.get("subprojects", []))
    root_dir = repo / root

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    bindings = copy.deepcopy(repo_manifest.get("bindings", {}))

    for item in manifest_def.get("project_level", []):
        variables = _base_template_vars(project, item["id"])
        required_meta = _required_metadata(variables, project_id=project["id"], role_id=item["id"])
        key = _binding_key(item["id"])
        existing = bindings.get(key, {})
        bound_path = str(existing.get("path", "")).strip()
        if bound_path and (repo / bound_path).exists():
            if _ensure_doc_metadata(repo / bound_path, required_meta, dry_run=dry_run):
                updated.append(bound_path)
            skipped.append(bound_path)
            continue

        discovered = _discover_existing_binding(repo, root, item, variables, project_id=project["id"])
        if discovered:
            rel_path = str(discovered.relative_to(repo))
            if _ensure_doc_metadata(discovered, required_meta, dry_run=dry_run):
                updated.append(rel_path)
            bindings[key] = _build_binding_entry(item, rel_path, discovered_by="auto_discover")
            skipped.append(rel_path)
            continue

        rel_path = _binding_rel_path(root, item, variables)
        content = _render_template(profile, item["template"], variables)
        status = _write_file(repo / rel_path, content, overwrite=False, dry_run=dry_run)
        bindings[key] = _build_binding_entry(item, rel_path, discovered_by="generated")
        if status == "created":
            created.append(rel_path)
        elif status == "updated":
            updated.append(rel_path)
        else:
            skipped.append(rel_path)

    for subproject in repo_manifest["subprojects"]:
        for item in manifest_def.get("subproject", []):
            variables = _base_template_vars(project, item["id"], subproject=subproject)
            required_meta = _required_metadata(
                variables,
                project_id=project["id"],
                role_id=item["id"],
                subproject=subproject["name"],
            )
            key = _binding_key(item["id"], subproject["name"])
            existing = bindings.get(key, {})
            bound_path = str(existing.get("path", "")).strip()
            if bound_path and (repo / bound_path).exists():
                if _ensure_doc_metadata(repo / bound_path, required_meta, dry_run=dry_run):
                    updated.append(bound_path)
                skipped.append(bound_path)
                continue

            discovered = _discover_existing_binding(
                repo,
                root,
                item,
                variables,
                project_id=project["id"],
                subproject=subproject["name"],
            )
            if discovered:
                rel_path = str(discovered.relative_to(repo))
                if _ensure_doc_metadata(discovered, required_meta, dry_run=dry_run):
                    updated.append(rel_path)
                bindings[key] = _build_binding_entry(item, rel_path, subproject=subproject, discovered_by="auto_discover")
                skipped.append(rel_path)
                continue

            rel_path = _binding_rel_path(root, item, variables)
            content = _render_template(profile, item["template"], variables)
            status = _write_file(repo / rel_path, content, overwrite=False, dry_run=dry_run)
            bindings[key] = _build_binding_entry(item, rel_path, subproject=subproject, discovered_by="generated")
            if status == "created":
                created.append(rel_path)
            elif status == "updated":
                updated.append(rel_path)
            else:
                skipped.append(rel_path)

    repo_manifest["bindings"] = bindings
    _save_repo_manifest(repo, repo_manifest, dry_run=dry_run)
    index_result = rebuild_indexes(project, repo, root=root, subprojects=repo_manifest["subprojects"], dry_run=dry_run)
    created.extend(index_result["created"])
    updated.extend(index_result["updated"])

    return {
        "root": str(root_dir),
        "profile": profile,
        "manifest": str(_manifest_path(repo).relative_to(repo)),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "subprojects": repo_manifest["subprojects"],
        "bindings": bindings,
    }


def rebuild_indexes(
    project: dict,
    repo: Path,
    *,
    root: str = DEFAULT_ROOT,
    subprojects: list[dict] | None = None,
    dry_run: bool = False,
) -> dict:
    repo_manifest = load_repo_manifest(repo)
    if subprojects is not None:
        repo_manifest["subprojects"] = normalize_subprojects(None, subprojects)
    if root:
        repo_manifest["root"] = root

    root_dir = repo / repo_manifest["root"]
    project_level_dir = root_dir / PROJECT_LEVEL_DIR
    entries = normalize_subprojects(None, repo_manifest.get("subprojects", []))
    created: list[str] = []
    updated: list[str] = []

    root_status = _write_file(
        root_dir / "README.md",
        _build_root_index(project, root_dir, entries, repo_manifest.get("bindings", {})),
        overwrite=True,
        dry_run=dry_run,
    )
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

    _save_repo_manifest(repo, repo_manifest, dry_run=dry_run)
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


def _validate_binding_metadata(
    repo: Path,
    binding: dict,
    *,
    project_id: str,
) -> list[dict]:
    issues = []
    rel_path = str(binding.get("path", "")).strip()
    if not rel_path:
        return [{
            "type": "binding_missing_path",
            "severity": "error",
            "message": f"binding[{binding.get('role_id', '?')}] 缺少 path",
        }]

    target = repo / rel_path
    if not target.exists():
        return [{
            "type": "binding_target_missing",
            "severity": "error",
            "file": rel_path,
            "message": f"绑定文档不存在: {rel_path}",
        }]

    metadata, _ = _parse_frontmatter(target)
    if not metadata:
        return [{
            "type": "missing_frontmatter",
            "severity": "error",
            "file": rel_path,
            "message": f"{rel_path} 缺少 frontmatter 元数据",
        }]

    for field in REQUIRED_DOC_METADATA:
        value = metadata.get(field)
        if value in (None, ""):
            issues.append({
                "type": "missing_doc_metadata",
                "severity": "error",
                "file": rel_path,
                "message": f"{rel_path} 缺少元数据字段: {field}",
            })

    if metadata.get("pt_role") != binding.get("role_id"):
        issues.append({
            "type": "role_metadata_mismatch",
            "severity": "error",
            "file": rel_path,
            "message": f"{rel_path} 的 pt_role={metadata.get('pt_role')!r} 与绑定角色 {binding.get('role_id')!r} 不一致",
        })

    if str(metadata.get("pt_project", "")).strip() not in {"", project_id}:
        issues.append({
            "type": "project_metadata_mismatch",
            "severity": "error",
            "file": rel_path,
            "message": f"{rel_path} 的 pt_project={metadata.get('pt_project')!r} 与项目 {project_id!r} 不一致",
        })

    if binding.get("subproject") and str(metadata.get("pt_subproject", "")).strip() not in {"", str(binding.get("subproject", ""))}:
        issues.append({
            "type": "subproject_metadata_mismatch",
            "severity": "error",
            "file": rel_path,
            "message": f"{rel_path} 的 pt_subproject={metadata.get('pt_subproject')!r} 与绑定子项目 {binding.get('subproject')!r} 不一致",
        })

    status = str(metadata.get("status", "")).strip()
    if status and status not in VALID_DOC_STATUSES:
        issues.append({
            "type": "invalid_doc_status",
            "severity": "error",
            "file": rel_path,
            "message": f"{rel_path} 的 status={status!r} 非法",
        })

    version = str(metadata.get("version", "")).strip()
    if version and not re.fullmatch(r"\d+(?:\.\d+)*", version):
        issues.append({
            "type": "invalid_doc_version",
            "severity": "error",
            "file": rel_path,
            "message": f"{rel_path} 的 version={version!r} 非法，应为数字版本号",
        })

    return issues


def check_requirements(project: dict, repo: Path, *, strict: bool = False) -> dict:
    repo_manifest = load_repo_manifest(repo)
    profile = str(repo_manifest.get("profile", DEFAULT_PROFILE) or DEFAULT_PROFILE)
    root = str(repo_manifest.get("root", DEFAULT_ROOT) or DEFAULT_ROOT)
    root_dir = repo / root
    subproject_entries = normalize_subprojects(None, repo_manifest.get("subprojects", []))
    issues: list[dict] = []

    if not _manifest_path(repo).exists():
        issues.append({
            "type": "missing_requirements_manifest",
            "severity": "error",
            "message": f"缺少 requirements manifest: {MANIFEST_REL_PATH.as_posix()}",
        })
        return _summarize_check(root, profile, issues)

    if not root_dir.exists():
        issues.append({
            "type": "missing_requirements_root",
            "severity": "error",
            "message": f"需求根目录不存在: {root}",
        })
        return _summarize_check(root, profile, issues)

    manifest_def = _load_manifest(profile)
    bindings = repo_manifest.get("bindings", {}) or {}

    for item in manifest_def.get("project_level", []):
        if not item.get("required"):
            continue
        key = _binding_key(item["id"])
        binding = bindings.get(key)
        if not binding:
            issues.append({
                "type": "missing_required_binding",
                "severity": "error",
                "message": f"缺少必需角色绑定: {item['id']}",
            })
            continue
        issues.extend(_validate_binding_metadata(repo, binding, project_id=project["id"]))

    for subproject in subproject_entries:
        for item in manifest_def.get("subproject", []):
            if not item.get("required"):
                continue
            key = _binding_key(item["id"], subproject["name"])
            binding = bindings.get(key)
            if not binding:
                issues.append({
                    "type": "missing_required_subproject_binding",
                    "severity": "error",
                    "message": f"{subproject['name']} 缺少必需角色绑定: {item['id']}",
                })
                continue
            issues.extend(_validate_binding_metadata(repo, binding, project_id=project["id"]))

    if not (root_dir / "README.md").exists():
        issues.append({
            "type": "missing_root_index",
            "severity": "error",
            "file": str(Path(root) / "README.md"),
            "message": "需求阶段索引页不存在",
        })

    for item in manifest_def.get("project_level", []):
        key = _binding_key(item["id"])
        binding = bindings.get(key)
        if binding and item["id"] == "req_trace_matrix":
            issues.extend(_check_required_columns(repo / binding["path"], TRACE_MATRIX_COLUMNS, "trace_matrix_missing_columns"))
        if binding and item["id"] == "req_current_conclusion":
            if not (repo / binding["path"]).exists():
                issues.append({
                    "type": "missing_current_conclusion",
                    "severity": "error",
                    "file": binding["path"],
                    "message": "缺少当前有效结论文档",
                })

    for subproject in subproject_entries:
        key = _binding_key("req_app_goal_matrix", subproject["name"])
        binding = bindings.get(key)
        if binding:
            issues.extend(_check_required_columns(repo / binding["path"], APP_MATRIX_COLUMNS, "app_matrix_missing_columns"))

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
