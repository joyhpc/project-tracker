from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tracker import core, engine, onboard
from tracker.commands.close_cmd import cmd_close
from tracker.commands.decision_cmd import _select_action as select_decision_action
from tracker.commands.poc_cmd import _select_action as select_poc_action
from tracker.commands.project import cmd_status, cmd_validate
from tracker.commands.prompt_cmd import cmd_prompt
from tracker.commands.review_cmd import _select_action as select_review_action


class ProjectSandboxTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = Path(tempfile.mkdtemp(prefix="pt-tests-"))
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


class MigrationTests(ProjectSandboxTestCase):
    def test_migrate_project_data_normalizes_legacy_shapes(self):
        legacy = {
            "id": "LEGACY",
            "name": "legacy",
            "flow": "generic",
            "nodes": [{
                "id": "task",
                "name": "task",
                "phase": "P1",
                "status": "done",
                "docs": [{"file": "docs/a.md", "desc": "A"}],
            }],
            "reviews": [{"file": "r.md", "verdicts": {"GO": 2}}],
        }
        migrated, changed = core.migrate_project_data(legacy)
        self.assertTrue(changed)
        self.assertEqual(migrated["schema_version"], core.PROJECT_SCHEMA_VERSION)
        self.assertEqual(migrated["nodes"][0]["docs"][0]["path"], "docs/a.md")
        self.assertNotIn("file", migrated["nodes"][0]["docs"][0])
        self.assertIsInstance(migrated["reviews"][0]["verdicts"], list)
        self.assertEqual(migrated["reviews"][0]["verdicts"][0]["verdict"], "GO")

    def test_load_marks_legacy_project_dirty_and_normalized(self):
        project_file = core.PROJECTS_DIR / "LEGACY.yaml"
        project_file.parent.mkdir(parents=True, exist_ok=True)
        project_file.write_text(
            "id: LEGACY\nname: legacy\nflow: generic\nblockers: []\nlog: []\nnodes:\n"
            "- id: task\n  name: task\n  phase: P1\n  status: done\n  docs:\n"
            "  - file: docs/a.md\nreviews:\n- file: r.md\n  verdicts:\n    GO: 1\n",
            encoding="utf-8",
        )
        loaded = core._load("LEGACY")
        self.assertTrue(loaded.get("_schema_dirty"))
        self.assertEqual(loaded["schema_version"], core.PROJECT_SCHEMA_VERSION)
        self.assertEqual(loaded["nodes"][0]["docs"][0]["path"], "docs/a.md")
        self.assertIsInstance(loaded["reviews"][0]["verdicts"], list)

    def test_migration_script_dry_run(self):
        project_file = self.tempdir / "demo.yaml"
        project_file.write_text(
            "id: DEMO\nname: demo\nflow: generic\nblockers: []\nlog: []\nnodes: []\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "tools/migrate_projects.py", str(project_file), "--dry-run"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("DRY-RUN demo.yaml", result.stdout)


class CoreRegressionTests(ProjectSandboxTestCase):
    def test_validate_project_schema_flags_invalid_node_status(self):
        project = {
            "id": "BAD",
            "name": "bad",
            "flow": "generic",
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [{"id": "task", "name": "Task", "phase": "P1", "status": "mystery"}],
            "blockers": [],
            "log": [],
        }
        issues = core.validate_project_schema(project)
        self.assertTrue(any(issue["type"] == "invalid_node_status" for issue in issues))

    def test_validate_project_file_handles_non_mapping_yaml(self):
        project_file = core.PROJECTS_DIR / "BROKEN.yaml"
        project_file.parent.mkdir(parents=True, exist_ok=True)
        project_file.write_text("- not-a-project\n", encoding="utf-8")

        result = core.validate_project_file(project_file)

        self.assertFalse(result["valid"])
        self.assertEqual(result["issues"][0]["type"], "invalid_project_root")

    def test_missing_dependency_is_not_ready(self):
        flow = {
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [
                {"id": "a", "name": "A", "phase": "P1", "status": "pending"},
                {"id": "b", "name": "B", "phase": "P1", "status": "pending", "depends": ["missing"]},
            ],
        }
        task_status = {"a": {"status": "pending"}, "b": {"status": "pending"}}
        classified = engine.classify_tasks(flow, task_status)
        self.assertEqual([n["id"] for n in classified["ready"]], ["a"])
        self.assertEqual(classified["waiting"][0]["_waiting_for"], ["missing"])
        with self.assertRaises(ValueError):
            engine.compute_cpm(flow, task_status)

    def test_start_task_requires_dependencies(self):
        core.init_project("TMP", "tmp", "generic")
        with self.assertRaises(ValueError):
            core.start_task("TMP", "bringup")

    def test_attach_doc_requires_existing_file_when_repo_bound(self):
        repo = self.tempdir / "repo"
        repo.mkdir()
        (repo / "doc.md").write_text("# ok\n", encoding="utf-8")
        core.init_project("TMP", "tmp", "generic", repo=str(repo))
        with self.assertRaises(ValueError):
            core.attach_doc("TMP", "market_research", "missing.md")
        node = core.attach_doc("TMP", "market_research", "doc.md")
        self.assertEqual(node["docs"][0]["path"], "doc.md")

    def test_prompt_save_without_repo_still_writes_file(self):
        core.init_project("TMP", "tmp", "generic")
        output = self.tempdir / "prompt.md"
        args = SimpleNamespace(
            question="测试问题",
            list=False,
            auto=False,
            deep_all=False,
            deep=False,
            full=False,
            system=False,
            save=str(output),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_prompt(args)
        self.assertTrue(output.exists())
        self.assertIn("测试问题", output.read_text(encoding="utf-8"))

    def test_core_close_closure_roundtrip(self):
        repo = self.tempdir / "repo"
        repo.mkdir()
        (repo / "evidence.md").write_text("# ev\n", encoding="utf-8")
        (repo / "docs_backwrite.md").write_text("# doc\n", encoding="utf-8")
        core.init_project("TMP", "tmp", "generic", repo=str(repo))

        updated = core.update_task_closure(
            "TMP",
            "bringup",
            updates={
                "formal_object_id": "DCURX_MAIN",
                "scope": "DCURX eDP",
                "sample_entity_id": "SN-01",
                "protocol_object_id": "TI984_DECODER",
                "firmware_version": "STM32_v0.9.1",
                "fpga_version": "KU3P_2026_03_22",
                "docs_anchor": "A57.DCURX.EDP_OLDI.EXEC_V1_V2",
                "docs_backwrite_path": "docs_backwrite.md",
                "close_mode": "merged_fix",
                "evidence_paths": ["evidence.md"],
            },
            require=True,
        )

        self.assertTrue(updated["required"])
        self.assertTrue(updated["check"]["valid"])
        listed = core.list_close_gates("TMP")
        self.assertEqual(listed["required_count"], 1)
        self.assertEqual(listed["valid_count"], 1)
        shown = core.get_task_closure("TMP", "bringup")
        self.assertEqual(shown["closure"]["formal_object_id"], "DCURX_MAIN")
        self.assertEqual(shown["closure"]["docs_anchor"], "A57.DCURX.EDP_OLDI.EXEC_V1_V2")


class CommandValidationTests(ProjectSandboxTestCase):
    def test_validate_command_reports_clean_project(self):
        core.init_project("TMP", "tmp", "generic")
        buffer = io.StringIO()
        args = SimpleNamespace(id=None, all=False, strict=False, json=False)
        with contextlib.redirect_stdout(buffer):
            cmd_validate(args)
        output = buffer.getvalue()
        self.assertIn("TMP", output)
        self.assertIn("error=0", output)

    def test_validate_command_fails_on_schema_error(self):
        project_file = core.PROJECTS_DIR / "BAD.yaml"
        project_file.parent.mkdir(parents=True, exist_ok=True)
        project_file.write_text(
            """id: BAD
name: broken
flow: generic
phases:
- id: P1
  name: P1
nodes:
- id: task
  name: Task
  phase: P1
  status: mystery
""",
            encoding="utf-8",
        )
        core._set_active("BAD")
        buffer = io.StringIO()
        args = SimpleNamespace(id=None, all=False, strict=False, json=False)
        with contextlib.redirect_stdout(buffer), self.assertRaises(SystemExit) as ctx:
            cmd_validate(args)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("status='mystery'", buffer.getvalue())

    def test_close_command_set_and_show_json(self):
        repo = self.tempdir / "repo"
        repo.mkdir()
        (repo / "evidence.md").write_text("# ev\n", encoding="utf-8")
        (repo / "docs_backwrite.md").write_text("# doc\n", encoding="utf-8")
        core.init_project("TMP", "tmp", "generic", repo=str(repo))

        set_args = SimpleNamespace(
            close_command="set",
            task_id="bringup",
            conclusion=None,
            formal_object_id="DCURX_MAIN",
            formal_object="DCURX_MAIN",
            formal_object_class=None,
            borrowed_object_id=None,
            borrowed_object=None,
            borrowed_object_class=None,
            borrowed_purpose=None,
            scope="DCURX eDP",
            sample_entity_id="SN-01",
            sample_id="SN-01",
            protocol_object_id="TI984_DECODER",
            protocol_object="TI984_DECODER",
            protocol_object_class=None,
            firmware_version="STM32_v0.9.1",
            fpga_version="KU3P_2026_03_22",
            pcb_version=None,
            bom_version=None,
            docs_anchor="A57.DCURX.EDP_OLDI.EXEC_V1_V2",
            docs_backwrite_path="docs_backwrite.md",
            docs_backwrite="docs_backwrite.md",
            close_mode="merged_fix",
            evidence=["evidence.md"],
            need_human_check_fields=None,
            clear=None,
            require=True,
            optional=False,
            json=False,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_close(set_args)

        show_args = SimpleNamespace(close_command="show", task_id="bringup", json=True)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cmd_close(show_args)

        output = buffer.getvalue()
        self.assertIn('"formal_object_id": "DCURX_MAIN"', output)
        self.assertIn('"docs_anchor": "A57.DCURX.EDP_OLDI.EXEC_V1_V2"', output)
        self.assertIn('"required": true', output)

    def test_status_command_prints_close_gate_summary(self):
        repo = self.tempdir / "repo"
        repo.mkdir()
        core.init_project("TMP", "tmp", "generic", repo=str(repo))
        core.update_task_closure(
            "TMP",
            "bringup",
            updates={
                "formal_object_id": "DCURX_MAIN",
            },
            require=True,
        )

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cmd_status(SimpleNamespace())
        output = buffer.getvalue()

        self.assertIn("Merge-to-Close", output)
        self.assertIn("[bringup]", output)
        self.assertIn("human=", output)

    def test_close_command_human_outputs_minimal_template(self):
        repo = self.tempdir / "repo"
        repo.mkdir()
        (repo / "docs_backwrite.md").write_text("# doc\n", encoding="utf-8")
        core.init_project("TMP", "tmp", "generic", repo=str(repo))

        core.update_task_closure(
            "TMP",
            "bringup",
            updates={
                "formal_object_id": "DCURX_MAIN",
                "scope": "DCURX 控制平面",
                "sample_entity_id": "NEED_HUMAN_CHECK",
                "protocol_object_id": "NA",
                "firmware_version": "NEED_HUMAN_CHECK",
                "fpga_version": "NEED_HUMAN_CHECK",
                "docs_anchor": "A57.DCURX.CONTROL_PLANE.GONOGO",
                "docs_backwrite_path": "docs_backwrite.md",
                "close_mode": "merged_fix",
                "evidence_paths": ["NEED_HUMAN_CHECK"],
                "need_human_check_fields": ["sample_entity_id", "firmware_version", "fpga_version", "evidence_paths"],
            },
            require=True,
        )

        human_args = SimpleNamespace(close_command="human", task_id="bringup", json=False)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cmd_close(human_args)
        output = buffer.getvalue()

        self.assertIn("close human", output)
        self.assertIn("sample_entity_id", output)
        self.assertIn("firmware_version", output)
        self.assertIn("evidence_paths", output)

    def test_review_select_action_rejects_multiple_flags(self):
        args = SimpleNamespace(add="a.md", approve=None, report=None, analyze=True, list=False)
        with self.assertRaises(ValueError):
            select_review_action(args)

    def test_decision_select_action_rejects_multiple_flags(self):
        args = SimpleNamespace(add="A", update="1")
        with self.assertRaises(ValueError):
            select_decision_action(args)

    def test_poc_select_action_rejects_multiple_flags(self):
        args = SimpleNamespace(add="A", update=None, summary=True)
        with self.assertRaises(ValueError):
            select_poc_action(args)


class ScanRegressionTests(ProjectSandboxTestCase):
    def test_scan_repo_excludes_generated_prompt_artifacts(self):
        repo = self.tempdir / "repo"
        (repo / "docs" / "prompts").mkdir(parents=True)
        (repo / "docs").mkdir(exist_ok=True)
        (repo / "docs" / "review-result.md").write_text("# R\n结论：GO\n", encoding="utf-8")
        (repo / "docs" / "onboard-prompt.md").write_text("# onboard\n结论：NO-GO\n", encoding="utf-8")
        (repo / "docs" / "prompts" / "foo-prompt.md").write_text("# generated\n结论：NO-GO\n", encoding="utf-8")

        result = onboard.scan_repo(str(repo))
        review_paths = sorted(Path(item["path"]).name for item in result["reviews"])
        self.assertEqual(review_paths, ["review-result.md"])


if __name__ == "__main__":
    unittest.main()
