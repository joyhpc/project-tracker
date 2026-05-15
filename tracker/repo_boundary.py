"""Repository boundary checks for project-tracker."""

from __future__ import annotations

import fnmatch
from pathlib import Path


FORBIDDEN_ROOT_PATTERNS = (
    "*_ANALYSIS.md",
    "*_ANALYSIS.txt",
    "*_ROADMAP.md",
    "*_INDEX.md",
    "TASK_*.md",
    "AGENT_TASKS.md",
    "*_AUTO.md",
)


def find_root_boundary_violations(root: str | Path) -> list[dict]:
    """Return root-level generated/meta files that violate repo boundaries."""
    root_path = Path(root)
    violations: list[dict] = []
    if not root_path.exists():
        return [
            {
                "path": str(root_path),
                "name": root_path.name,
                "pattern": "",
                "message": f"仓库根目录不存在: {root_path}",
            }
        ]

    for path in sorted(root_path.iterdir()):
        if not path.is_file():
            continue
        for pattern in FORBIDDEN_ROOT_PATTERNS:
            if fnmatch.fnmatch(path.name, pattern):
                violations.append(
                    {
                        "path": str(path),
                        "name": path.name,
                        "pattern": pattern,
                        "message": f"{path.name} matches {pattern}",
                    }
                )
                break
    return violations
