"""Repository boundary lint for project-tracker.

The root directory should stay small and intentional. AI-generated analysis,
roadmap, task tracker, and auto-output files belong in an archive, an ignored
output directory, a GitHub issue, or the linked project repository.
"""

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


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []

    for path in root.iterdir():
        if not path.is_file():
            continue
        for pattern in FORBIDDEN_ROOT_PATTERNS:
            if fnmatch.fnmatch(path.name, pattern):
                violations.append(f"{path.name} matches {pattern}")
                break

    if violations:
        print("Root-level generated/meta files are not allowed:")
        for violation in violations:
            print(f"  - {violation}")
        print("\nMove useful historical files under docs/_archive/ or keep generated output in outputs/.")
        return 1

    print("Repository boundary lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
