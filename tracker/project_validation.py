"""Project schema and integrity validation helpers."""

from __future__ import annotations

from collections import Counter

from .project_constants import (
    PROJECT_SCHEMA_VERSION,
    VALID_DECISION_STATUSES,
    VALID_NODE_STATUSES,
    VALID_POC_STATUSES,
    VALID_REVIEW_VERDICTS,
)
from .close_gate import validate_closure_schema
from .project_model import _effective_nodes



def _validation_issue(issue_type: str, severity: str, message: str, **extra) -> dict:
    issue = {"type": issue_type, "severity": severity, "message": message}
    issue.update(extra)
    return issue



def _validate_named_list_items(items, *, label: str, id_key: str = "id") -> list[dict]:
    issues = []
    if not isinstance(items, list):
        return [
            _validation_issue(
                f"invalid_{label}_collection",
                "warning",
                f"{label} 必须是 list",
            )
        ]

    seen_ids = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(
                _validation_issue(
                    f"invalid_{label}_item",
                    "warning",
                    f"{label}[{index}] 必须是 object/map",
                    index=index,
                )
            )
            continue
        item_id = item.get(id_key)
        if item_id in (None, ""):
            continue
        if item_id in seen_ids:
            issues.append(
                _validation_issue(
                    f"duplicate_{label}_id",
                    "warning",
                    f"{label} 出现重复 ID: {item_id}",
                    item_id=item_id,
                )
            )
            continue
        seen_ids.add(item_id)
    return issues



def validate_project_schema(project: dict | None) -> list[dict]:
    """验证项目 YAML 的结构和关键枚举字段。"""
    issues = []
    if not isinstance(project, dict):
        return [
            _validation_issue(
                "invalid_project_root",
                "error",
                "项目文件顶层必须是 YAML object/map",
            )
        ]

    for key in ("id", "name", "flow"):
        value = project.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                _validation_issue(
                    f"invalid_{key}",
                    "error",
                    f"顶层字段 `{key}` 必须是非空字符串",
                    field=key,
                )
            )

    schema_version = project.get("schema_version")
    if schema_version != PROJECT_SCHEMA_VERSION:
        issues.append(
            _validation_issue(
                "schema_version_mismatch",
                "info",
                f"schema_version={schema_version!r}，当前版本为 {PROJECT_SCHEMA_VERSION}",
            )
        )

    phases = project.get("phases", [])
    phase_ids = set()
    if not isinstance(phases, list):
        issues.append(_validation_issue("invalid_phases", "warning", "顶层字段 `phases` 应为 list"))
    else:
        for index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                issues.append(_validation_issue("invalid_phase_item", "warning", f"phases[{index}] 必须是 object/map", index=index))
                continue
            phase_id = phase.get("id")
            phase_name = phase.get("name")
            if not isinstance(phase_id, str) or not phase_id.strip():
                issues.append(_validation_issue("invalid_phase_id", "warning", f"phases[{index}].id 必须是非空字符串", index=index))
                continue
            if phase_id in phase_ids:
                issues.append(_validation_issue("duplicate_phase_id", "warning", f"阶段 ID 重复: {phase_id}", phase=phase_id))
            phase_ids.add(phase_id)
            if not isinstance(phase_name, str) or not phase_name.strip():
                issues.append(_validation_issue("invalid_phase_name", "warning", f"phases[{index}].name 必须是非空字符串", index=index, phase=phase_id))

    nodes = project.get("nodes", [])
    if not isinstance(nodes, list):
        issues.append(_validation_issue("invalid_nodes", "error", "顶层字段 `nodes` 必须是 list"))
    else:
        seen_node_ids = set()
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                issues.append(_validation_issue("invalid_node_item", "error", f"nodes[{index}] 必须是 object/map", index=index))
                continue

            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                issues.append(_validation_issue("invalid_node_id", "error", f"nodes[{index}].id 必须是非空字符串", index=index))
                continue
            if node_id in seen_node_ids:
                issues.append(_validation_issue("duplicate_node_id", "error", f"节点 ID 重复: {node_id}", node=node_id))
            seen_node_ids.add(node_id)

            name = node.get("name")
            if not isinstance(name, str) or not name.strip():
                issues.append(_validation_issue("invalid_node_name", "error", f"节点 [{node_id}] 缺少有效 name", node=node_id))

            phase = node.get("phase")
            if not isinstance(phase, str) or not phase.strip():
                issues.append(_validation_issue("invalid_node_phase", "error", f"节点 [{node_id}] 缺少有效 phase", node=node_id))
            elif phase_ids and phase not in phase_ids:
                issues.append(_validation_issue("unknown_node_phase", "warning", f"节点 [{node_id}] 引用了未知阶段 `{phase}`", node=node_id, phase=phase))

            status = node.get("status", "pending")
            if status not in VALID_NODE_STATUSES:
                issues.append(_validation_issue("invalid_node_status", "error", f"节点 [{node_id}] status={status!r} 非法", node=node_id, status=status))

            depends = node.get("depends", [])
            if not isinstance(depends, list) or any(not isinstance(dep, str) or not dep.strip() for dep in depends):
                issues.append(_validation_issue("invalid_node_depends", "error", f"节点 [{node_id}] depends 必须是 string list", node=node_id))

            docs = node.get("docs", [])
            if docs is not None:
                if not isinstance(docs, list):
                    issues.append(_validation_issue("invalid_node_docs", "warning", f"节点 [{node_id}] docs 应为 list", node=node_id))
                else:
                    for doc_index, doc in enumerate(docs):
                        if not isinstance(doc, dict):
                            issues.append(_validation_issue("invalid_doc_item", "warning", f"节点 [{node_id}] docs[{doc_index}] 必须是 object/map", node=node_id, index=doc_index))
                            continue
                        doc_path = doc.get("path") or doc.get("file")
                        if not isinstance(doc_path, str) or not doc_path.strip():
                            issues.append(_validation_issue("invalid_doc_path", "warning", f"节点 [{node_id}] docs[{doc_index}] 缺少 path/file", node=node_id, index=doc_index))
            issues.extend(validate_closure_schema(node))

    for field_name in ("blockers", "log"):
        items = project.get(field_name, [])
        if not isinstance(items, list):
            issues.append(_validation_issue(f"invalid_{field_name}", "warning", f"顶层字段 `{field_name}` 应为 list"))

    reviews = project.get("reviews", [])
    if not isinstance(reviews, list):
        issues.append(_validation_issue("invalid_reviews", "warning", "顶层字段 `reviews` 应为 list"))
    else:
        for index, review in enumerate(reviews):
            if not isinstance(review, dict):
                issues.append(_validation_issue("invalid_review_item", "warning", f"reviews[{index}] 必须是 object/map", index=index))
                continue
            review_file = review.get("file") or review.get("path")
            if not isinstance(review_file, str) or not review_file.strip():
                issues.append(_validation_issue("invalid_review_file", "warning", f"reviews[{index}] 缺少 file/path", index=index))
            verdicts = review.get("verdicts", []) or []
            if not isinstance(verdicts, list):
                issues.append(_validation_issue("invalid_review_verdicts", "warning", f"reviews[{index}].verdicts 应为 list 或 legacy dict", index=index))
                continue
            for verdict_index, verdict in enumerate(verdicts):
                if not isinstance(verdict, dict):
                    issues.append(_validation_issue("invalid_review_verdict", "warning", f"reviews[{index}].verdicts[{verdict_index}] 必须是 object/map", index=index))
                    continue
                verdict_name = verdict.get("verdict")
                if not isinstance(verdict_name, str) or not verdict_name.strip():
                    issues.append(_validation_issue("missing_review_verdict", "warning", f"reviews[{index}].verdicts[{verdict_index}] 缺少 verdict", index=index))
                elif verdict_name.upper() not in VALID_REVIEW_VERDICTS:
                    issues.append(_validation_issue("unknown_review_verdict", "info", f"reviews[{index}] 使用了非标准 verdict `{verdict_name}`", index=index))

    decisions = project.get("decisions", [])
    issues.extend(_validate_named_list_items(decisions, label="decisions"))
    if isinstance(decisions, list):
        for index, decision in enumerate(decisions):
            if not isinstance(decision, dict):
                continue
            status = decision.get("status", "active")
            if status not in VALID_DECISION_STATUSES:
                issues.append(_validation_issue("invalid_decision_status", "warning", f"decisions[{index}] status={status!r} 非法", index=index))
            title = decision.get("title")
            if not isinstance(title, str) or not title.strip():
                issues.append(_validation_issue("invalid_decision_title", "warning", f"decisions[{index}] 缺少 title", index=index))

    pocs = project.get("pocs", [])
    issues.extend(_validate_named_list_items(pocs, label="pocs"))
    if isinstance(pocs, list):
        for index, poc in enumerate(pocs):
            if not isinstance(poc, dict):
                continue
            status = poc.get("status", "pending")
            if status not in VALID_POC_STATUSES:
                issues.append(_validation_issue("invalid_poc_status", "warning", f"pocs[{index}] status={status!r} 非法", index=index))
            title = poc.get("title")
            if not isinstance(title, str) or not title.strip():
                issues.append(_validation_issue("invalid_poc_title", "warning", f"pocs[{index}] 缺少 title", index=index))

    return issues



def check_integrity(project: dict, cpm: dict = None) -> list[dict]:
    """项目完整性检查 — 检测结构性问题。"""
    nodes = _effective_nodes(project)
    node_ids = {node["id"] for node in nodes}
    nodes_map = {node["id"]: node for node in nodes}
    phases = project.get("phases", [])
    phase_order = {phase["id"]: i for i, phase in enumerate(phases)}
    last_phase_id = phases[-1]["id"] if phases else None
    first_phase_id = phases[0]["id"] if phases else None

    successors = {node["id"]: [] for node in nodes}
    predecessors = {node["id"]: [] for node in nodes}
    for node in nodes:
        for dep in node.get("depends", []):
            if dep in successors:
                successors[dep].append(node["id"])
            if dep in predecessors:
                predecessors[node["id"]].append(dep)

    final_milestones = {
        node["id"] for node in nodes
        if node.get("type") == "milestone" and node.get("phase") == last_phase_id
    }
    final_phase_nodes = {node["id"] for node in nodes if node.get("phase") == last_phase_id}

    warnings = []

    in_degree = {node_id: len(predecessors.get(node_id, [])) for node_id in node_ids}
    queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
    visited_count = 0
    while queue:
        node_id = queue.pop(0)
        visited_count += 1
        for succ in successors.get(node_id, []):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)
    if visited_count != len(node_ids):
        cycle_nodes = [node_id for node_id, degree in in_degree.items() if degree > 0]
        warnings.append(
            {
                "type": "cycle_detected",
                "severity": "error",
                "nodes": cycle_nodes[:10],
                "message": f"检测到循环依赖: {', '.join(cycle_nodes[:5])}{'...' if len(cycle_nodes) > 5 else ''}",
            }
        )

    for node in nodes:
        node_id = node["id"]
        if not successors[node_id] and node_id not in final_milestones and node_id not in final_phase_nodes:
            if node.get("type") == "milestone":
                continue
            if node.get("status") in {"done", "skipped"}:
                continue
            severity = "critical" if (cpm and cpm.get("nodes", {}).get(node_id, {}).get("critical")) else "warning"
            warnings.append(
                {
                    "type": "orphan_terminal",
                    "severity": severity,
                    "node": node_id,
                    "name": node.get("name", ""),
                    "message": f"[{node_id}] {node.get('name', '')} 没有后继节点 — 可能未接入下游流程",
                }
            )

    for node in nodes:
        for dep in node.get("depends", []):
            if dep not in node_ids:
                warnings.append(
                    {
                        "type": "dangling_dep",
                        "severity": "error",
                        "node": node["id"],
                        "dep": dep,
                        "message": f"[{node['id']}] 依赖 [{dep}] 不存在",
                    }
                )

    for node in nodes:
        if node.get("type") == "milestone" and not node.get("depends"):
            warnings.append(
                {
                    "type": "milestone_no_deps",
                    "severity": "warning",
                    "node": node["id"],
                    "message": f"里程碑 [{node['id']}] 没有上游依赖",
                }
            )

    for node in nodes:
        node_order = phase_order.get(node.get("phase", ""), -1)
        if node_order < 0:
            continue
        for dep in node.get("depends", []):
            dep_node = nodes_map.get(dep)
            if dep_node:
                dep_order = phase_order.get(dep_node.get("phase", ""), -1)
                if dep_order > node_order:
                    warnings.append(
                        {
                            "type": "reverse_phase_dep",
                            "severity": "info",
                            "node": node["id"],
                            "dep": dep,
                            "message": f"[{node['id']}]({node.get('phase', '')}) 依赖后阶段 [{dep}]({dep_node.get('phase', '')})",
                        }
                    )

    id_counts = Counter(node["id"] for node in nodes)
    for node_id, count in id_counts.items():
        if count > 1:
            warnings.append(
                {
                    "type": "duplicate_id",
                    "severity": "error",
                    "node": node_id,
                    "message": f"[{node_id}] 节点ID重复 ({count}次)",
                }
            )

    for node in nodes:
        node_id = node["id"]
        if (
            not predecessors[node_id]
            and not successors[node_id]
            and node.get("phase") != first_phase_id
            and node.get("status") not in {"done", "skipped"}
        ):
            warnings.append(
                {
                    "type": "isolated_node",
                    "severity": "warning",
                    "node": node_id,
                    "message": f"[{node_id}] {node.get('name', '')} 完全孤立（无前驱无后继）",
                }
            )

    for node in nodes:
        deps = node.get("depends", [])
        if len(deps) < 2:
            continue
        dep_set = set(deps)
        for dep in deps:
            other_deps = dep_set - {dep}
            visited = set()
            queue = list(other_deps)
            reachable = False
            while queue:
                current = queue.pop(0)
                if current == dep:
                    reachable = True
                    break
                if current in visited:
                    continue
                visited.add(current)
                current_node = nodes_map.get(current)
                if current_node:
                    for current_dep in current_node.get("depends", []):
                        if current_dep not in visited:
                            queue.append(current_dep)
            if reachable:
                warnings.append(
                    {
                        "type": "redundant_dep",
                        "severity": "info",
                        "node": node["id"],
                        "dep": dep,
                        "message": f"[{node['id']}] → [{dep}] 冗余依赖（已被其他依赖路径覆盖）",
                    }
                )

    bringup_keywords = ["调试", "bringup", "bring-up", "bring_up"]
    for node in nodes:
        if node.get("status") == "done":
            continue
        node_id = node["id"]
        name_lower = (node.get("name", "") + " " + node_id).lower()
        if not any(keyword in name_lower for keyword in bringup_keywords):
            continue
        has_children = any(child["id"].startswith(node_id + ".") for child in nodes if child["id"] != node_id)
        if not has_children:
            warnings.append(
                {
                    "type": "coarse_bringup",
                    "severity": "info",
                    "node": node_id,
                    "message": f"[{node_id}] {node.get('name', '')} 是粗粒度调试节点 — 可用 pt sub-load {node_id} board_bringup 展开为分层调试",
                }
            )

    return warnings



def validate_project(project: dict | None) -> list[dict]:
    issues = validate_project_schema(project)
    hard_errors = [issue for issue in issues if issue.get("severity") in ("error", "critical")]
    if hard_errors or not isinstance(project, dict):
        return issues
    try:
        issues.extend(check_integrity(project))
    except Exception as exc:
        issues.append(_validation_issue("integrity_check_failed", "error", f"完整性检查执行失败: {exc}"))
    return issues



def summarize_validation_issues(issues: list[dict]) -> dict:
    return {
        "critical": sum(1 for issue in issues if issue.get("severity") == "critical"),
        "error": sum(1 for issue in issues if issue.get("severity") == "error"),
        "warning": sum(1 for issue in issues if issue.get("severity") == "warning"),
        "info": sum(1 for issue in issues if issue.get("severity") == "info"),
    }
