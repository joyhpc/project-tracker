from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from tracker import core


class RequirementsSandboxTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = Path(tempfile.mkdtemp(prefix="pt-req-tests-"))
        self.old_projects_dir = core.PROJECTS_DIR
        self.old_config_file = core.CONFIG_FILE
        self.old_history_dir = core.HISTORY_DIR
        core.PROJECTS_DIR = self.tempdir / "projects"
        core.CONFIG_FILE = core.PROJECTS_DIR / ".active"
        core.HISTORY_DIR = core.PROJECTS_DIR / ".pt_history"

    def tearDown(self):
        core.PROJECTS_DIR = self.old_projects_dir
        core.CONFIG_FILE = self.old_config_file
        core.HISTORY_DIR = self.old_history_dir


class RequirementsTests(RequirementsSandboxTestCase):
    def test_init_requirements_creates_manifest_bindings_and_state(self):
        repo = self.tempdir / "repo"
        repo.mkdir()
        core.init_project("A57", "A57 docs", "generic", repo=str(repo))

        result = core.init_requirements("A57", subprojects=["CAMRX", "DCURX"])

        self.assertTrue((repo / ".pt" / "requirements_manifest.yaml").exists())
        manifest = yaml.safe_load((repo / ".pt" / "requirements_manifest.yaml").read_text(encoding="utf-8"))
        self.assertIn("req_first_principles", manifest["bindings"])
        self.assertIn("req_app_goal_matrix@CAMRX", manifest["bindings"])
        self.assertTrue((repo / "01_需求阶段_Requirements" / "00_项目级需求_Project_Level" / "A57_项目级需求追溯矩阵.md").exists())
        self.assertTrue((repo / "01_需求阶段_Requirements" / "01_CAMRX" / "CAMRX_应用目标矩阵.md").exists())
        self.assertEqual(len(result["subprojects"]), 2)

        project = core._load("A57")
        self.assertEqual(project["requirements"]["profile"], "hardware-platform")
        self.assertEqual(project["requirements"]["root"], "01_需求阶段_Requirements")

    def test_init_requirements_discovers_legacy_doc_and_injects_frontmatter(self):
        repo = self.tempdir / "repo"
        project_level = repo / "01_需求阶段_Requirements" / "00_项目级需求_Project_Level"
        project_level.mkdir(parents=True)
        legacy = project_level / "A57_第一性原理需求范式_2026-03-19.md"
        legacy.write_text("# old\n", encoding="utf-8")
        core.init_project("A57", "A57 docs", "generic", repo=str(repo))

        result = core.init_requirements("A57")

        self.assertIn("01_需求阶段_Requirements/00_项目级需求_Project_Level/A57_第一性原理需求范式_2026-03-19.md", result["skipped"])
        self.assertFalse((project_level / "A57_第一性原理需求.md").exists())
        self.assertTrue(legacy.read_text(encoding="utf-8").startswith("---\n"))
        manifest = yaml.safe_load((repo / ".pt" / "requirements_manifest.yaml").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["bindings"]["req_first_principles"]["path"],
            "01_需求阶段_Requirements/00_项目级需求_Project_Level/A57_第一性原理需求范式_2026-03-19.md",
        )
        check = core.check_requirements("A57", save=False)
        self.assertTrue(check["valid"])

    def test_rebuild_indexes_keeps_other_requirement_blocks_visible(self):
        repo = self.tempdir / "repo"
        research_dir = repo / "01_需求阶段_Requirements" / "01_调研与分析_Research"
        research_dir.mkdir(parents=True)
        (research_dir / "需求调研报告.md").write_text("# 调研\n", encoding="utf-8")
        core.init_project("A57", "A57 docs", "generic", repo=str(repo))

        core.init_requirements("A57")

        root_readme = (repo / "01_需求阶段_Requirements" / "README.md").read_text(encoding="utf-8")
        self.assertIn("01_调研与分析_Research", root_readme)

    def test_check_requirements_uses_binding_not_pattern_guess(self):
        repo = self.tempdir / "repo"
        project_level = repo / "01_需求阶段_Requirements" / "00_项目级需求_Project_Level"
        project_level.mkdir(parents=True)
        legacy = project_level / "A57_第一性原理需求范式_2026-03-19.md"
        legacy.write_text("# old\n", encoding="utf-8")
        core.init_project("A57", "A57 docs", "generic", repo=str(repo))
        core.init_requirements("A57")

        manifest_path = repo / ".pt" / "requirements_manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        legacy.rename(project_level / "A57_第一性原理需求范式_2026-03-19_renamed.md")
        manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")

        result = core.check_requirements("A57", save=False)

        self.assertFalse(result["valid"])
        self.assertTrue(any(issue["type"] == "binding_target_missing" for issue in result["issues"]))

    def test_check_requirements_strict_reports_broken_links(self):
        repo = self.tempdir / "repo"
        repo.mkdir()
        core.init_project("A57", "A57 docs", "generic", repo=str(repo))
        core.init_requirements("A57")
        conclusion = repo / "01_需求阶段_Requirements" / "00_项目级需求_Project_Level" / "A57_当前有效结论.md"
        conclusion.write_text(conclusion.read_text(encoding="utf-8") + "\n[bad](missing.md)\n", encoding="utf-8")

        result = core.check_requirements("A57", strict=True, save=False)

        self.assertFalse(result["valid"])
        self.assertTrue(any(issue["type"] == "broken_markdown_link" for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
