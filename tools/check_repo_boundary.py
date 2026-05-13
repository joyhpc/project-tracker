"""Repository boundary lint for project-tracker.

The root directory should stay small and intentional. AI-generated analysis,
roadmap, task tracker, and auto-output files belong in an archive, an ignored
output directory, a GitHub issue, or the linked project repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracker.repo_boundary import find_root_boundary_violations  # noqa: E402


def main() -> int:
    violations = find_root_boundary_violations(ROOT)

    if violations:
        print("Root-level generated/meta files are not allowed:")
        for violation in violations:
            print(f"  - {violation['message']}")
        print("\nMove useful historical files under docs/_archive/ or keep generated output in outputs/.")
        return 1

    print("Repository boundary lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
