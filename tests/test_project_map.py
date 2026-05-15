from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tracker import core, engine
from tracker.commands.visual_cmd import cmd_map
from tracker.project_map import (
    build_global_project_map,
    build_project_map,
    render_global_project_map_text,
    render_project_map_html,
    render_project_map_text,
)


class ProjectSandboxTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = Path(tempfile.mkdtemp(prefix="pt-map-tests-"))
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


class ProjectMapTests(ProjectSandboxTestCase):
    def _sample_project(self) -> dict:
        return {
            "id": "PILLOW",
            "name": "智能助眠枕头",
            "flow": "generic",
            "repo": str(self.tempdir / "missing-smart-sleep-pillow"),
            "phases": [
                {"id": "CONCEPT", "name": "概念阶段"},
                {"id": "DESIGN", "name": "设计阶段", "milestone": "M1"},
                {"id": "PROTO", "name": "原型阶段", "milestone": "M2"},
            ],
            "nodes": [
                {"id": "market_research", "name": "市场调研", "phase": "CONCEPT", "status": "done"},
                {"id": "concept_design", "name": "概念设计", "phase": "CONCEPT", "status": "done", "depends": ["market_research"]},
                {"id": "feasibility", "name": "可行性分析", "phase": "CONCEPT", "status": "done", "depends": ["concept_design"]},
                {"id": "hw_design", "name": "硬件设计", "phase": "DESIGN", "status": "in_progress", "depends": ["feasibility"], "owner": "硬件工程师", "docs": [{"path": "docs/design/hw.md"}], "started": "2026-03-08 10:00"},
                {
                    "id": "fw_design",
                    "name": "固件设计",
                    "phase": "DESIGN",
                    "status": "pending",
                    "depends": ["feasibility"],
                    "owner": "固件工程师",
                    "close_required": True,
                    "closure": {
                        "formal_object": "PILLOW_MAIN",
                        "scope": "固件联调",
                    },
                },
                {"id": "mech_design", "name": "结构设计", "phase": "DESIGN", "status": "pending", "depends": ["feasibility"], "owner": "结构工程师"},
                {"id": "hw_review", "name": "硬件评审", "phase": "DESIGN", "status": "pending", "depends": ["hw_design", "fw_design", "mech_design"], "owner": "硬件工程师"},
                {"id": "bringup", "name": "板级调试", "phase": "PROTO", "status": "blocked", "depends": ["hw_review"], "blocked_reason": "等样机回板", "critical": True},
            ],
            "blockers": [{"task_id": "bringup", "reason": "等样机回板"}],
            "log": [],
            "decisions": [{"id": 1, "title": "先做核心体感链路", "status": "active"}],
        }

    def _active_project(self) -> dict:
        repo = self.tempdir / "active-repo"
        repo.mkdir()
        return {
            "id": "ACTIVE",
            "name": "推进中项目",
            "flow": "generic",
            "repo": str(repo),
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [
                {"id": "done", "name": "已完成任务", "phase": "P1", "status": "done"},
                {"id": "ready", "name": "可推进任务", "phase": "P1", "status": "pending", "depends": ["done"]},
            ],
            "blockers": [],
            "log": [],
        }

    def _done_project(self) -> dict:
        repo = self.tempdir / "done-repo"
        repo.mkdir()
        return {
            "id": "DONE",
            "name": "完成项目",
            "flow": "generic",
            "repo": str(repo),
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [
                {"id": "ship", "name": "发布", "phase": "P1", "status": "done"},
            ],
            "blockers": [],
            "log": [],
        }

    def test_build_project_map_highlights_focus_and_repo_state(self):
        project = self._sample_project()
        map_data = build_project_map(project)

        self.assertEqual(map_data["focus"]["id"], "hw_design")
        self.assertEqual([entry["id"] for entry in map_data["parallel_ready"]], ["fw_design", "mech_design"])
        self.assertEqual(map_data["repo"]["label"], "仓库路径缺失")
        self.assertEqual(map_data["metrics"]["blocked_count"], 1)
        self.assertEqual(map_data["metrics"]["close_required_count"], 1)
        self.assertEqual(map_data["metrics"]["close_invalid_count"], 1)
        fw_design = next(entry for entry in map_data["entries"] if entry["id"] == "fw_design")
        self.assertTrue(fw_design["close_required"])
        self.assertFalse(fw_design["close_valid"])

    def test_render_project_map_text_contains_waiting_and_repo_sections(self):
        project = self._sample_project()
        text = render_project_map_text(build_project_map(project))

        self.assertIn("项目地图", text)
        self.assertIn("仓库状态: 仓库路径缺失", text)
        self.assertIn("等待: 硬件设计", text)
        self.assertIn("当前焦点", text)
        self.assertIn("Merge-to-Close", text)
        self.assertIn("close=NG", text)

    def test_render_project_map_html_contains_focus_and_lane_titles(self):
        project = self._sample_project()
        html = render_project_map_html(build_project_map(project))

        self.assertIn("当前焦点", html)
        self.assertIn("可并行推进", html)
        self.assertIn("等待依赖", html)
        self.assertIn("仓库路径缺失", html)
        self.assertIn("Close Gate", html)
        self.assertIn("Close NG", html)

    def test_cmd_map_prints_terminal_map(self):
        project = self._sample_project()
        core._save(project)
        core._set_active(project["id"])

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cmd_map(SimpleNamespace(html=False, output=str(self.tempdir), no_png=True))
        output = buffer.getvalue()

        self.assertIn("智能助眠枕头", output)
        self.assertIn("当前焦点", output)

    def test_build_global_project_map_sorts_and_summarizes_projects(self):
        blocked_project = self._sample_project()
        blocked_project["_active"] = True
        active_project = self._active_project()
        done_project = self._done_project()

        global_map = build_global_project_map([active_project, done_project, blocked_project])

        self.assertEqual(global_map["kind"], "global_project_map")
        self.assertEqual(global_map["active_project_id"], "PILLOW")
        self.assertEqual([summary["project_id"] for summary in global_map["projects"]], ["PILLOW", "ACTIVE", "DONE"])
        self.assertEqual(global_map["projects"][0]["state"], "blocked")
        self.assertEqual(global_map["projects"][1]["state"], "active")
        self.assertEqual(global_map["projects"][2]["state"], "done")
        self.assertEqual(global_map["projects"][0]["close_invalid_count"], 1)
        self.assertEqual(global_map["projects"][1]["repo_status"], "ok")
        self.assertEqual(global_map["projects"][1]["focus"]["task_id"], "ready")
        self.assertNotIn("depends", global_map["projects"][1]["focus"])

    def test_render_global_project_map_text_contains_table_and_attention(self):
        blocked_project = self._sample_project()
        active_project = self._active_project()
        global_map = build_global_project_map([active_project, blocked_project])

        text = render_global_project_map_text(global_map)

        self.assertIn("全局项目地图", text)
        self.assertIn("| A | Project | Progress | State | Focus / Next |", text)
        self.assertIn("PILLOW", text)
        self.assertIn("ACTIVE", text)
        self.assertIn("需要关注", text)
        self.assertIn("板级调试", text)

    def test_cmd_map_all_json_prints_global_payload(self):
        blocked_project = self._sample_project()
        active_project = self._active_project()
        core._save(blocked_project)
        core._save(active_project)
        core._set_active(blocked_project["id"])

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cmd_map(SimpleNamespace(all=True, json=True, html=False, output=str(self.tempdir), no_png=True))
        payload = json.loads(buffer.getvalue())

        self.assertEqual(payload["kind"], "global_project_map")
        self.assertEqual(payload["active_project_id"], "PILLOW")
        self.assertEqual(payload["metrics"]["project_count"], 2)
        self.assertEqual(payload["projects"][0]["project_id"], "PILLOW")
        self.assertNotIn("nodes", payload["projects"][0])

    def test_cmd_map_json_requires_all(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            with self.assertRaises(SystemExit):
                cmd_map(SimpleNamespace(all=False, json=True, html=False, output=str(self.tempdir), no_png=True))

        self.assertIn("pt map --all --json", buffer.getvalue())


class EngineOrderingTests(unittest.TestCase):
    def test_classify_tasks_follows_stable_topological_order(self):
        flow = {
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [
                {"id": "c", "name": "C", "phase": "P1", "depends": ["a"]},
                {"id": "b", "name": "B", "phase": "P1", "depends": ["a"]},
                {"id": "a", "name": "A", "phase": "P1"},
                {"id": "d", "name": "D", "phase": "P1", "depends": ["b"]},
            ],
        }
        task_status = {
            "a": {"status": "done"},
            "b": {"status": "pending"},
            "c": {"status": "pending"},
            "d": {"status": "pending"},
        }

        result = engine.classify_tasks(flow, task_status)

        self.assertEqual([node["id"] for node in result["ready"]], ["b", "c"])


if __name__ == "__main__":
    unittest.main()
