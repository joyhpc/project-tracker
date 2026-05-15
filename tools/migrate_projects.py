#!/usr/bin/env python3
"""项目 YAML schema 迁移工具。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tracker.core import migrate_project_data, PROJECT_SCHEMA_VERSION  # noqa: E402
from tracker.console import configure_stdio  # noqa: E402


def migrate_file(path: Path, dry_run: bool = False) -> tuple[bool, str]:
    with open(path, "r", encoding="utf-8") as fh:
        project = yaml.safe_load(fh)

    migrated, changed = migrate_project_data(project)
    if not changed:
        return False, f"SKIP {path.name} already schema v{PROJECT_SCHEMA_VERSION}"

    if not dry_run:
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(migrated, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    action = "DRY-RUN" if dry_run else "MIGRATED"
    return True, f"{action} {path.name} -> schema v{PROJECT_SCHEMA_VERSION}"


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="迁移 project-tracker 项目 YAML 到最新 schema")
    parser.add_argument("paths", nargs="*", help="项目 YAML 文件或目录，默认 projects/")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写回文件")
    args = parser.parse_args()

    targets = args.paths or [str(ROOT / "projects")]
    files: list[Path] = []
    for target in targets:
        path = Path(target).expanduser().resolve()
        if path.is_dir():
            files.extend(sorted(p for p in path.glob("*.yaml") if p.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            print(f"WARN missing path: {path}")

    if not files:
        print("No project YAML files found")
        return 1

    changed_count = 0
    for path in files:
        changed, message = migrate_file(path, dry_run=args.dry_run)
        if changed:
            changed_count += 1
        print(message)

    print(f"DONE: {changed_count}/{len(files)} files need migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
