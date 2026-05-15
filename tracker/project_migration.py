"""Project schema migration helpers."""

from __future__ import annotations

import copy

from .project_constants import PROJECT_SCHEMA_VERSION


def normalize_verdicts(raw) -> list[dict]:
    """Normalize verdicts to ``list[{verdict, topic}]``."""
    if isinstance(raw, dict):
        return [
            {"verdict": verdict, "topic": f"(legacy, {count}次)"}
            for verdict, count in raw.items()
            for _ in range(count)
        ]
    return raw or []


def migrate_project_data(project: dict | None) -> tuple[dict | None, bool]:
    """Migrate historical project data to the current schema."""
    if not isinstance(project, dict):
        return project, False

    changed = False
    migrated = copy.deepcopy(project)

    if migrated.get("schema_version") != PROJECT_SCHEMA_VERSION:
        migrated["schema_version"] = PROJECT_SCHEMA_VERSION
        changed = True

    for key in ("blockers", "log", "nodes", "reviews", "decisions", "pocs"):
        if key not in migrated or migrated[key] is None:
            migrated[key] = []
            changed = True

    for node in migrated.get("nodes", []):
        docs = node.get("docs", []) or []
        normalized_docs = []
        docs_changed = False
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            normalized = dict(doc)
            path = normalized.get("path") or normalized.get("file")
            if path and normalized.get("path") != path:
                normalized["path"] = path
                docs_changed = True
            if "file" in normalized:
                normalized.pop("file", None)
                docs_changed = True
            normalized_docs.append(normalized)
        if docs_changed or normalized_docs != docs:
            node["docs"] = normalized_docs
            changed = True

    normalized_reviews = []
    for review in migrated.get("reviews", []):
        if not isinstance(review, dict):
            continue
        normalized = dict(review)
        verdicts = normalize_verdicts(normalized.get("verdicts", []))
        if normalized.get("verdicts") != verdicts:
            normalized["verdicts"] = verdicts
            changed = True
        normalized_reviews.append(normalized)
    if normalized_reviews != migrated.get("reviews", []):
        migrated["reviews"] = normalized_reviews

    for collection in ("decisions", "pocs"):
        normalized_items = []
        for item in migrated.get(collection, []):
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            if "id" in normalized and isinstance(normalized["id"], str) and normalized["id"].isdigit():
                normalized["id"] = int(normalized["id"])
                changed = True
            normalized_items.append(normalized)
        if normalized_items != migrated.get(collection, []):
            migrated[collection] = normalized_items

    return migrated, changed


def prepare_for_save(project: dict) -> dict:
    """Normalize project data before dumping YAML."""
    migrated, _ = migrate_project_data(project)
    return migrated or {}
