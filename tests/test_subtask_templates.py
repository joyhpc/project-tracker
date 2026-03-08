from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tracker import subtask_templates


class SubtaskTemplateUnitTests(unittest.TestCase):
    def _now(self) -> str:
        return "2026-03-08 12:00"

    def _base_project(self) -> dict:
        return {
            "id": "TMP",
            "name": "tmp",
            "flow": "generic",
            "phases": [{"id": "P1", "name": "P1"}, {"id": "P2", "name": "P2"}],
            "nodes": [],
            "blockers": [],
            "log": [],
        }

    def test_list_and_match_subtask_templates(self):
        tempdir = Path(tempfile.mkdtemp(prefix="pt-subtpl-"))
        (tempdir / "board_bringup.yaml").write_text(
            """name: Board Bringup\nattach_to:\n  - bringup\nphases:\n  - name: Stage 1\n    tasks:\n      - id: power\n        name: 上电\n""",
            encoding="utf-8",
        )

        templates = subtask_templates.list_subtask_templates(template_dirs=[tempdir])
        matched = subtask_templates.match_subtask_templates("bringup", template_dirs=[tempdir])

        self.assertEqual(templates[0]["id"], "board_bringup")
        self.assertEqual(templates[0]["task_count"], 1)
        self.assertEqual(matched[0]["attach_to"], ["bringup"])

    def test_apply_subtask_template_rewires_graph_and_external_hints(self):
        project = self._base_project()
        project["nodes"] = [
            {"id": "dep", "name": "Dep", "phase": "P1", "status": "done"},
            {"id": "bringup", "name": "Bringup", "phase": "P1", "status": "pending", "depends": ["dep"]},
            {"id": "external.signal", "name": "Signal", "phase": "P1", "status": "pending"},
            {"id": "next", "name": "Next", "phase": "P2", "status": "pending", "depends": ["bringup"]},
        ]
        template = {
            "name": "Board Bringup",
            "phases": [
                {
                    "name": "Stage 1",
                    "tasks": [
                        {
                            "id": "power",
                            "name": "Power",
                            "external_depends_hint": [
                                {"pattern": "external.*", "reason": "needs signal", "required": True}
                            ],
                        },
                        {"id": "i2c", "name": "I2C", "depends": ["power"]},
                    ],
                }
            ],
        }

        result = subtask_templates.apply_subtask_template_to_project(
            project,
            "bringup",
            "board_bringup",
            template,
            now=self._now,
        )

        power = next(node for node in project["nodes"] if node["id"] == "bringup.power")
        next_node = next(node for node in project["nodes"] if node["id"] == "next")
        parent = next(node for node in project["nodes"] if node["id"] == "bringup")

        self.assertEqual(result["loaded"], 2)
        self.assertEqual(parent["status"], "expanded")
        self.assertEqual(parent["expanded_to"], ["bringup.i2c", "bringup.power"])
        self.assertIn("dep", power["depends"])
        self.assertIn("external.signal", power["depends"])
        self.assertEqual(next_node["depends"], ["bringup.i2c"])
        self.assertTrue(result["external_dep_suggestions"][0]["auto_added"])

    def test_load_subtask_template_definition_reports_available_templates(self):
        tempdir = Path(tempfile.mkdtemp(prefix="pt-subtpl-"))
        (tempdir / "board_bringup.yaml").write_text("name: Board Bringup\n", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            subtask_templates.load_subtask_template_definition("missing", template_dirs=[tempdir])

        self.assertIn("board_bringup", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
