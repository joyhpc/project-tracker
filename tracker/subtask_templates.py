"""Subtask template discovery, matching, and application helpers."""

from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml

from .project_model import _find_node_in_project


def candidate_subtask_template_dirs(package_dir: Path) -> list[Path]:
    return [
        package_dir / "flows" / "subtasks",
        package_dir.parent / "flows" / "subtasks",
    ]


def list_subtasks_in_project(project: dict, parent_id: str) -> list[dict]:
    return [node for node in project.get("nodes", []) if node.get("parent") == parent_id]


def list_subtask_templates(*, template_dirs: list[Path]) -> list[dict]:
    template_dir = next((path for path in template_dirs if path.exists()), None)
    if template_dir is None:
        return []

    result = []
    for template_file in sorted(template_dir.glob("*.yaml")):
        template = yaml.safe_load(template_file.read_text(encoding="utf-8")) or {}
        task_count = sum(len(phase.get("tasks", [])) for phase in template.get("phases", []))
        result.append({
            "id": template_file.stem,
            "name": template.get("name", ""),
            "description": template.get("description", ""),
            "attach_to": template.get("attach_to", []),
            "task_count": task_count,
            "phases": [phase.get("name", "") for phase in template.get("phases", [])],
        })
    return result


def match_subtask_templates(task_id: str, *, template_dirs: list[Path]) -> list[dict]:
    templates = list_subtask_templates(template_dirs=template_dirs)
    return [template for template in templates if task_id in template.get("attach_to", [])]


def load_subtask_template_definition(template_id: str, *, template_dirs: list[Path]) -> dict:
    for candidate in template_dirs:
        candidate_file = candidate / f"{template_id}.yaml"
        if candidate_file.exists():
            return yaml.safe_load(candidate_file.read_text(encoding="utf-8")) or {}

    template_dir = next((path for path in template_dirs if path.exists()), None)
    available = [path.stem for path in sorted(template_dir.glob("*.yaml"))] if template_dir else []
    raise ValueError(f"模板不存在: {template_id}。可用: {', '.join(available)}")


def apply_subtask_template_to_project(
    project: dict,
    parent_id: str,
    template_id: str,
    template: dict,
    *,
    now,
) -> dict:
    parent = _find_node_in_project(project, parent_id)
    if not parent:
        raise ValueError(f"父任务不存在: {parent_id}")

    created_count = 0
    for phase in template.get("phases", []):
        for task in phase.get("tasks", []):
            full_id = f"{parent_id}.{task['id']}"
            if _find_node_in_project(project, full_id):
                continue

            sub_node = {
                "id": full_id,
                "name": task["name"],
                "type": "task",
                "phase": parent.get("phase", ""),
                "parent": parent_id,
                "status": "pending",
                "created": now(),
            }
            if task.get("owner"):
                sub_node["owner"] = task["owner"]
            if task.get("days"):
                sub_node["days"] = task["days"]
            if task.get("depends"):
                sub_node["depends"] = [f"{parent_id}.{dep}" for dep in task["depends"]]
            if task.get("deliverables"):
                sub_node["deliverables"] = task["deliverables"]
            if task.get("critical"):
                sub_node["critical"] = True
            if task.get("description"):
                sub_node["description"] = task["description"]

            hints = task.get("external_depends_hint", [])
            if hints:
                sub_node["_external_hints"] = hints

            project.setdefault("nodes", []).append(sub_node)
            created_count += 1

    external_dep_suggestions = []
    all_node_ids = {node["id"] for node in project.get("nodes", [])}
    for node in project.get("nodes", []):
        if node.get("parent") != parent_id:
            continue
        hints = node.pop("_external_hints", [])
        for hint in hints:
            matched_nodes = [
                node_id
                for node_id in all_node_ids
                if fnmatch.fnmatch(node_id, hint["pattern"])
                and not node_id.startswith(parent_id + ".")
                and node_id != parent_id
            ]
            if matched_nodes and hint.get("required"):
                existing = set(node.get("depends", []))
                for matched in matched_nodes:
                    if matched not in existing:
                        node.setdefault("depends", []).append(matched)
                        external_dep_suggestions.append({
                            "subtask": node["id"],
                            "external_dep": matched,
                            "reason": hint["reason"],
                            "auto_added": True,
                        })
            elif matched_nodes:
                for matched in matched_nodes:
                    external_dep_suggestions.append({
                        "subtask": node["id"],
                        "external_dep": matched,
                        "reason": hint["reason"],
                        "auto_added": False,
                    })

    if created_count > 0:
        sub_ids = {node["id"] for node in project.get("nodes", []) if node.get("parent") == parent_id}

        entry_subs = []
        for node in project.get("nodes", []):
            if node["id"] not in sub_ids:
                continue
            internal_deps = [dep for dep in node.get("depends", []) if dep in sub_ids]
            if not internal_deps:
                entry_subs.append(node["id"])

        depended_by = set()
        for node in project.get("nodes", []):
            if node["id"] not in sub_ids:
                continue
            for dep in node.get("depends", []):
                if dep in sub_ids:
                    depended_by.add(dep)
        exit_subs = [sub_id for sub_id in sub_ids if sub_id not in depended_by]

        parent_deps = parent.get("depends", [])
        if parent_deps:
            for entry_id in entry_subs:
                entry_node = _find_node_in_project(project, entry_id)
                if not entry_node:
                    continue
                existing = set(entry_node.get("depends", []))
                new_deps = [dep for dep in parent_deps if dep not in existing]
                if new_deps:
                    entry_node.setdefault("depends", []).extend(new_deps)

        if exit_subs:
            for node in project.get("nodes", []):
                if node["id"] in sub_ids or node["id"] == parent_id:
                    continue
                depends = node.get("depends", [])
                if parent_id in depends:
                    depends.remove(parent_id)
                    depends.extend(exit_subs)
                    node["depends"] = depends

        parent["status"] = "expanded"
        parent["expanded_to"] = sorted(sub_ids)

    project.setdefault("log", []).append({
        "time": now(),
        "action": "subtask_template_load",
        "task": parent_id,
        "detail": f"加载模板 {template_id}: {created_count} 个子任务",
    })
    return {
        "loaded": created_count,
        "template": template_id,
        "parent": parent_id,
        "template_name": template.get("name", template_id),
        "external_dep_suggestions": external_dep_suggestions,
    }


def load_subtask_template_into_project(
    project: dict,
    parent_id: str,
    template_id: str,
    *,
    now,
    template_dirs: list[Path],
) -> dict:
    template = load_subtask_template_definition(template_id, template_dirs=template_dirs)
    return apply_subtask_template_to_project(project, parent_id, template_id, template, now=now)
