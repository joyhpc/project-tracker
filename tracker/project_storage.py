"""Project YAML storage primitives."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml


def project_file(projects_dir: Path, project_id: str) -> Path:
    return projects_dir / f"{project_id}.yaml"


def load_project(projects_dir: Path, project_id: str, migrate) -> dict | None:
    path = project_file(projects_dir, project_id)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as fh:
        project = yaml.safe_load(fh)

    project, migrated = migrate(project)
    if not isinstance(project, dict):
        return project

    project["_mtime"] = path.stat().st_mtime
    if migrated:
        project["_schema_dirty"] = True
    return project


def save_project(projects_dir: Path, project: dict, prepare, *, check_mtime: bool = True) -> Path:
    projects_dir.mkdir(exist_ok=True)
    path = project_file(projects_dir, project["id"])

    if check_mtime and "_mtime" in project and path.exists():
        current_mtime = path.stat().st_mtime
        if current_mtime != project["_mtime"]:
            raise RuntimeError(
                f"并发冲突：YAML 文件已被外部修改 (mtime: {project['_mtime']} → {current_mtime})。"
                f"请重新加载项目后重试。"
            )

    normalized = prepare(project)
    save_data = {key: value for key, value in normalized.items() if not key.startswith("_")}
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(save_data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)

    project["_mtime"] = path.stat().st_mtime
    project.pop("_schema_dirty", None)
    return path


def get_active(config_file: Path) -> str | None:
    if config_file.exists():
        return config_file.read_text(encoding="utf-8").strip()
    return None


def set_active(projects_dir: Path, config_file: Path, project_id: str) -> None:
    projects_dir.mkdir(exist_ok=True)
    config_file.write_text(project_id, encoding="utf-8")


def list_project_files(projects_dir: Path) -> list[Path]:
    projects_dir.mkdir(exist_ok=True)
    return sorted(projects_dir.glob("*.yaml"))


def snapshot(history_dir: Path, source: Path, project_id: str, *, max_history: int) -> Path | None:
    history_dir.mkdir(exist_ok=True)
    if not source.exists():
        return None

    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = history_dir / f"{project_id}_{timestamp}.yaml"
    shutil.copy2(source, destination)

    snapshots = sorted(history_dir.glob(f"{project_id}_*.yaml"))
    for old in snapshots[:-max_history]:
        old.unlink()
    return destination


def restore_latest_snapshot(history_dir: Path, target: Path, project_id: str) -> Path:
    snapshots = sorted(history_dir.glob(f"{project_id}_*.yaml"))
    if not snapshots:
        raise ValueError(f"没有可恢复的历史快照: {project_id}")

    latest = snapshots[-1]
    shutil.copy2(latest, target)
    latest.unlink()
    return latest
