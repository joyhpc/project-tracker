"""Merge-to-Close / formal closure gate helpers."""

from __future__ import annotations

from pathlib import Path

from .project_model import _find_node_in_project


VALID_CLOSE_MODES = {"merged_fix", "merged_waiver", "accepted_risk"}
NEED_HUMAN_CHECK = "NEED_HUMAN_CHECK"
STRING_ALIAS_FIELDS = {
    "conclusion": ("conclusion",),
    "formal_object_id": ("formal_object_id", "formal_object"),
    "formal_object_class": ("formal_object_class",),
    "borrowed_object_id": ("borrowed_object_id", "borrowed_object"),
    "borrowed_object_class": ("borrowed_object_class",),
    "borrowed_purpose": ("borrowed_purpose",),
    "scope": ("scope",),
    "sample_entity_id": ("sample_entity_id", "sample_id"),
    "protocol_object_id": ("protocol_object_id", "protocol_object"),
    "protocol_object_class": ("protocol_object_class",),
    "firmware_version": ("firmware_version",),
    "fpga_version": ("fpga_version",),
    "pcb_version": ("pcb_version",),
    "bom_version": ("bom_version",),
    "docs_anchor": ("docs_anchor",),
    "docs_backwrite_path": ("docs_backwrite_path", "docs_backwrite"),
    "close_mode": ("close_mode",),
}
LIST_ALIAS_FIELDS = {
    "evidence_paths": ("evidence_paths", "evidence"),
    "need_human_check_fields": ("need_human_check_fields",),
}
VALID_CLOSURE_FIELDS = {
    "conclusion",
    "formal_object",
    "formal_object_id",
    "formal_object_class",
    "borrowed_object",
    "borrowed_object_id",
    "borrowed_object_class",
    "borrowed_purpose",
    "scope",
    "sample_id",
    "sample_entity_id",
    "protocol_object",
    "protocol_object_id",
    "protocol_object_class",
    "firmware_version",
    "fpga_version",
    "pcb_version",
    "bom_version",
    "docs_anchor",
    "docs_backwrite",
    "docs_backwrite_path",
    "close_mode",
    "evidence",
    "evidence_paths",
    "need_human_check_fields",
}
REQUIRED_CLOSE_FIELDS = (
    "formal_object_id",
    "scope",
    "sample_entity_id",
    "protocol_object_id",
    "firmware_version",
    "fpga_version",
    "docs_anchor",
    "docs_backwrite_path",
    "close_mode",
)


def node_requires_close_gate(node: dict) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("close_required") or node.get("closure") or node.get("closure_required"):
        return True
    gate_text = str(node.get("gate", "")).lower()
    return "merge-to-close" in gate_text or "formal close" in gate_text


def _issue(issue_type: str, severity: str, message: str, **extra) -> dict:
    payload = {"type": issue_type, "severity": severity, "message": message}
    payload.update(extra)
    return payload


def _resolve_file(repo: Path | None, file_path: str) -> Path:
    path = Path(file_path).expanduser()
    if path.is_absolute():
        return path
    if repo is None:
        return path
    return repo / path


def _first_string(closure: dict, *keys: str) -> str:
    for key in keys:
        value = closure.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_list(closure: dict, *keys: str) -> list:
    for key in keys:
        value = closure.get(key)
        if isinstance(value, list):
            return value
    return []


def normalize_closure_view(closure: dict | None) -> dict:
    source = dict(closure or {})
    view = dict(source)
    for canonical, aliases in STRING_ALIAS_FIELDS.items():
        value = _first_string(source, *aliases)
        if value:
            for key in aliases:
                view.setdefault(key, value)
            view.setdefault(canonical, value)
    for canonical, aliases in LIST_ALIAS_FIELDS.items():
        value = _first_list(source, *aliases)
        if value:
            for key in aliases:
                view.setdefault(key, list(value))
            view.setdefault(canonical, list(value))
    return view


def summarize_human_fields(closure: dict | None, issues: list[dict] | None = None) -> list[str]:
    normalized = normalize_closure_view(closure)
    fields: list[str] = []
    for field in normalized.get("need_human_check_fields", []):
        if isinstance(field, str) and field.strip():
            fields.append(field.strip())

    for field in REQUIRED_CLOSE_FIELDS:
        value = normalized.get(field)
        if isinstance(value, str):
            if not value.strip() or value.strip() == NEED_HUMAN_CHECK:
                fields.append(field)
        elif value in (None, []):
            fields.append(field)

    evidence_paths = normalized.get("evidence_paths", [])
    if not evidence_paths or any(str(item).strip() == NEED_HUMAN_CHECK for item in evidence_paths):
        fields.append("evidence_paths")

    borrowed_object_id = str(normalized.get("borrowed_object_id", "")).strip()
    if borrowed_object_id and not str(normalized.get("borrowed_purpose", "")).strip():
        fields.append("borrowed_purpose")

    for issue in issues or []:
        field = issue.get("field")
        if isinstance(field, str) and field.strip():
            fields.append(field.strip())

    result = []
    seen = set()
    for field in fields:
        if field not in seen:
            seen.add(field)
            result.append(field)
    return result


def build_human_closure_template(project: dict, task_id: str) -> dict:
    node = _find_node_in_project(project, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")

    result = check_close_gate(project, task_id)
    closure = result.get("closure", {}) or {}
    fields = summarize_human_fields(closure, result.get("issues", []))
    values = {}
    for field in fields:
        current = closure.get(field)
        if current in (None, ""):
            values[field] = "" if field != "evidence_paths" else []
        else:
            values[field] = current

    return {
        "task_id": task_id,
        "name": node.get("name", task_id),
        "required": result.get("required", False),
        "valid": result.get("valid", False),
        "docs_anchor": closure.get("docs_anchor", ""),
        "docs_backwrite_path": closure.get("docs_backwrite_path", ""),
        "fields": fields,
        "values": values,
        "closure": closure,
        "issues": result.get("issues", []),
    }


def validate_closure_schema(node: dict) -> list[dict]:
    issues: list[dict] = []
    node_id = node.get("id", "?")
    closure = node.get("closure")
    if closure is None:
        if node.get("close_required") or node.get("closure_required"):
            issues.append(_issue("missing_closure", "warning", f"节点 [{node_id}] 标记了 close gate，但缺少 closure 对象", node=node_id))
        return issues

    if not isinstance(closure, dict):
        return [_issue("invalid_closure", "error", f"节点 [{node_id}] closure 必须是 object/map", node=node_id)]

    for key in closure.keys():
        if key not in VALID_CLOSURE_FIELDS:
            issues.append(_issue("unknown_closure_field", "warning", f"节点 [{node_id}] closure 出现未知字段 `{key}`", node=node_id, field=key))

    for canonical, aliases in STRING_ALIAS_FIELDS.items():
        for key in aliases:
            value = closure.get(key)
            if value is not None and not isinstance(value, str):
                issues.append(_issue("invalid_closure_field_type", "error", f"节点 [{node_id}] closure.{key} 必须是字符串", node=node_id, field=key))

    for canonical, aliases in LIST_ALIAS_FIELDS.items():
        for key in aliases:
            value = closure.get(key)
            if value is None:
                continue
            if not isinstance(value, list):
                issues.append(_issue("invalid_closure_list_type", "error", f"节点 [{node_id}] closure.{key} 必须是 string list", node=node_id, field=key))
            elif any(not isinstance(item, str) or not item.strip() for item in value):
                issues.append(_issue("invalid_closure_list_type", "error", f"节点 [{node_id}] closure.{key} 必须是非空字符串列表", node=node_id, field=key))

    close_mode = closure.get("close_mode")
    if close_mode is not None and isinstance(close_mode, str) and close_mode.strip() and close_mode not in VALID_CLOSE_MODES:
        issues.append(_issue("invalid_close_mode", "error", f"节点 [{node_id}] close_mode 非法: {close_mode}", node=node_id, field="close_mode"))

    normalized = normalize_closure_view(closure)
    need_check_fields = {item.strip() for item in normalized.get("need_human_check_fields", []) if isinstance(item, str) and item.strip()}
    for canonical, aliases in (
        ("sample_entity_id", STRING_ALIAS_FIELDS["sample_entity_id"]),
        ("firmware_version", STRING_ALIAS_FIELDS["firmware_version"]),
        ("fpga_version", STRING_ALIAS_FIELDS["fpga_version"]),
        ("formal_object_id", STRING_ALIAS_FIELDS["formal_object_id"]),
        ("protocol_object_id", STRING_ALIAS_FIELDS["protocol_object_id"]),
        ("borrowed_object_id", STRING_ALIAS_FIELDS["borrowed_object_id"]),
    ):
        value = _first_string(closure, *aliases)
        if value == NEED_HUMAN_CHECK and not any(name in need_check_fields for name in (canonical, *aliases)):
            issues.append(
                _issue(
                    "missing_need_human_check_field",
                    "error",
                    f"节点 [{node_id}] {canonical} 标记为 NEED_HUMAN_CHECK，但 need_human_check_fields 未列出该字段",
                    node=node_id,
                    field=canonical,
                )
            )

    return issues


def check_close_gate(project: dict, task_id: str) -> dict:
    node = _find_node_in_project(project, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")

    raw_closure = node.get("closure", {}) or {}
    closure = normalize_closure_view(raw_closure)
    repo = Path(project["repo"]).expanduser() if project.get("repo") else None
    issues: list[dict] = []

    if not node_requires_close_gate(node):
        return {
            "task_id": task_id,
            "required": False,
            "valid": True,
            "issues": [],
            "counts": {"critical": 0, "error": 0, "warning": 0, "info": 0},
        }

    for field, label in (
        ("formal_object_id", "正式对象"),
        ("scope", "适用范围"),
        ("sample_entity_id", "样机实体编号"),
        ("protocol_object_id", "协议板/解码板对象"),
        ("firmware_version", "固件版本"),
        ("fpga_version", "FPGA/RTL 版本"),
        ("docs_anchor", "A57-docs 回写锚点"),
        ("docs_backwrite_path", "A57-docs 回写路径"),
        ("close_mode", "关闭方式"),
    ):
        value = str(closure.get(field, "")).strip()
        if not value:
            issues.append(_issue("missing_close_field", "error", f"缺少 {label}", field=field))

    borrowed_object = str(closure.get("borrowed_object_id", "")).strip()
    if borrowed_object and not str(closure.get("borrowed_purpose", "")).strip():
        issues.append(_issue("missing_borrowed_purpose", "error", "存在借用对象但缺少借用目的", field="borrowed_purpose"))

    close_mode = str(closure.get("close_mode", "")).strip()
    if close_mode and close_mode not in VALID_CLOSE_MODES:
        issues.append(_issue("invalid_close_mode", "error", f"close_mode 非法: {close_mode}", field="close_mode"))

    docs_backwrite = str(closure.get("docs_backwrite_path", "")).strip()
    if docs_backwrite:
        backwrite_path = _resolve_file(repo, docs_backwrite)
        if not backwrite_path.exists():
            issues.append(_issue("missing_docs_backwrite", "error", f"A57-docs 回写路径不存在: {docs_backwrite}", field="docs_backwrite_path"))

    evidence_paths = closure.get("evidence_paths", []) or []
    if not isinstance(evidence_paths, list) or not evidence_paths:
        issues.append(_issue("missing_evidence", "error", "缺少证据路径", field="evidence_paths"))
    else:
        for index, item in enumerate(evidence_paths):
            path = str(item).strip()
            if not path:
                issues.append(_issue("invalid_evidence_item", "error", f"evidence[{index}] 为空", index=index))
                continue
            resolved = _resolve_file(repo, path)
            if not resolved.exists():
                issues.append(_issue("missing_evidence_file", "error", f"证据路径不存在: {path}", index=index))

    need_check_fields = {item.strip() for item in closure.get("need_human_check_fields", []) if isinstance(item, str) and item.strip()}
    for field in ("sample_entity_id", "firmware_version", "fpga_version", "formal_object_id", "protocol_object_id", "borrowed_object_id"):
        value = str(closure.get(field, "")).strip()
        if value == NEED_HUMAN_CHECK and field not in need_check_fields:
            issues.append(_issue("missing_need_human_check_field", "error", f"{field} 标记为 NEED_HUMAN_CHECK，但 need_human_check_fields 未列出该字段", field=field))

    counts = {
        "critical": sum(1 for issue in issues if issue.get("severity") == "critical"),
        "error": sum(1 for issue in issues if issue.get("severity") == "error"),
        "warning": sum(1 for issue in issues if issue.get("severity") == "warning"),
        "info": sum(1 for issue in issues if issue.get("severity") == "info"),
    }
    return {
        "task_id": task_id,
        "required": True,
        "valid": counts["critical"] == 0 and counts["error"] == 0,
        "issues": issues,
        "counts": counts,
        "closure": closure,
    }


def summarize_close_gates(project: dict) -> dict:
    entries = []
    for node in project.get("nodes", []):
        if not node_requires_close_gate(node):
            continue
        result = check_close_gate(project, node["id"])
        closure = result.get("closure", {}) or {}
        entries.append({
            "task_id": node["id"],
            "name": node.get("name", node["id"]),
            "phase": node.get("phase", ""),
            "status": node.get("status", "pending"),
            "valid": result["valid"],
            "issue_count": len(result["issues"]),
            "error_count": result["counts"].get("error", 0),
            "warning_count": result["counts"].get("warning", 0),
            "formal_object_id": closure.get("formal_object_id", ""),
            "formal_object": closure.get("formal_object_id", ""),
            "sample_entity_id": closure.get("sample_entity_id", ""),
            "protocol_object_id": closure.get("protocol_object_id", ""),
            "docs_anchor": closure.get("docs_anchor", ""),
            "docs_backwrite_path": closure.get("docs_backwrite_path", ""),
            "docs_backwrite": closure.get("docs_backwrite_path", ""),
            "close_mode": closure.get("close_mode", ""),
            "need_human_fields": summarize_human_fields(closure, result.get("issues", [])),
            "top_issues": [issue.get("message", "") for issue in result.get("issues", [])[:3]],
        })
    invalid = [entry for entry in entries if not entry["valid"]]
    return {
        "entries": entries,
        "required_count": len(entries),
        "invalid_count": len(invalid),
        "valid_count": len(entries) - len(invalid),
    }
