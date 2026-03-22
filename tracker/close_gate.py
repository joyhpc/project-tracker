"""Merge-to-Close / formal closure gate helpers."""

from __future__ import annotations

from pathlib import Path

from .project_model import _find_node_in_project


VALID_CLOSE_MODES = {"merged_fix", "merged_waiver", "accepted_risk"}
VALID_CLOSURE_FIELDS = {
    "formal_object",
    "borrowed_object",
    "borrowed_purpose",
    "scope",
    "sample_id",
    "protocol_object",
    "firmware_version",
    "fpga_version",
    "docs_backwrite",
    "close_mode",
    "evidence",
}
REQUIRED_CLOSE_FIELDS = (
    "formal_object",
    "scope",
    "sample_id",
    "protocol_object",
    "firmware_version",
    "fpga_version",
    "docs_backwrite",
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

    for key in REQUIRED_CLOSE_FIELDS:
        value = closure.get(key)
        if value is not None and not isinstance(value, str):
            issues.append(_issue("invalid_closure_field_type", "error", f"节点 [{node_id}] closure.{key} 必须是字符串", node=node_id, field=key))

    for key in ("borrowed_object", "borrowed_purpose"):
        value = closure.get(key)
        if value is not None and not isinstance(value, str):
            issues.append(_issue("invalid_closure_field_type", "error", f"节点 [{node_id}] closure.{key} 必须是字符串", node=node_id, field=key))

    evidence = closure.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, list):
            issues.append(_issue("invalid_closure_evidence", "error", f"节点 [{node_id}] closure.evidence 必须是 string list", node=node_id))
        elif any(not isinstance(item, str) or not item.strip() for item in evidence):
            issues.append(_issue("invalid_closure_evidence", "error", f"节点 [{node_id}] closure.evidence 必须是非空字符串列表", node=node_id))

    close_mode = closure.get("close_mode")
    if close_mode is not None and isinstance(close_mode, str) and close_mode.strip() and close_mode not in VALID_CLOSE_MODES:
        issues.append(_issue("invalid_close_mode", "error", f"节点 [{node_id}] close_mode 非法: {close_mode}", node=node_id, field="close_mode"))

    return issues


def check_close_gate(project: dict, task_id: str) -> dict:
    node = _find_node_in_project(project, task_id)
    if not node:
        raise ValueError(f"任务不存在: {task_id}")

    closure = node.get("closure", {}) or {}
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
        ("formal_object", "正式对象"),
        ("scope", "适用范围"),
        ("sample_id", "样机编号"),
        ("protocol_object", "协议板/解码板对象"),
        ("firmware_version", "固件版本"),
        ("fpga_version", "FPGA/RTL 版本"),
        ("docs_backwrite", "A57-docs 回写路径"),
        ("close_mode", "关闭方式"),
    ):
        value = str(closure.get(field, "")).strip()
        if not value:
            issues.append(_issue("missing_close_field", "error", f"缺少 {label}", field=field))

    borrowed_object = str(closure.get("borrowed_object", "")).strip()
    if borrowed_object and not str(closure.get("borrowed_purpose", "")).strip():
        issues.append(_issue("missing_borrowed_purpose", "error", "存在借用对象但缺少借用目的", field="borrowed_purpose"))

    close_mode = str(closure.get("close_mode", "")).strip()
    if close_mode and close_mode not in VALID_CLOSE_MODES:
        issues.append(_issue("invalid_close_mode", "error", f"close_mode 非法: {close_mode}", field="close_mode"))

    docs_backwrite = str(closure.get("docs_backwrite", "")).strip()
    if docs_backwrite:
        backwrite_path = _resolve_file(repo, docs_backwrite)
        if not backwrite_path.exists():
            issues.append(_issue("missing_docs_backwrite", "error", f"A57-docs 回写路径不存在: {docs_backwrite}", field="docs_backwrite"))

    evidence_paths = closure.get("evidence", []) or []
    if not isinstance(evidence_paths, list) or not evidence_paths:
        issues.append(_issue("missing_evidence", "error", "缺少证据路径", field="evidence"))
    else:
        for index, item in enumerate(evidence_paths):
            path = str(item).strip()
            if not path:
                issues.append(_issue("invalid_evidence_item", "error", f"evidence[{index}] 为空", index=index))
                continue
            resolved = _resolve_file(repo, path)
            if not resolved.exists():
                issues.append(_issue("missing_evidence_file", "error", f"证据路径不存在: {path}", index=index))

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
            "formal_object": closure.get("formal_object", ""),
            "docs_backwrite": closure.get("docs_backwrite", ""),
            "close_mode": closure.get("close_mode", ""),
            "top_issues": [issue.get("message", "") for issue in result.get("issues", [])[:3]],
        })
    invalid = [entry for entry in entries if not entry["valid"]]
    return {
        "entries": entries,
        "required_count": len(entries),
        "invalid_count": len(invalid),
        "valid_count": len(entries) - len(invalid),
    }
