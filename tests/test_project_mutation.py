from __future__ import annotations

import unittest

from tracker import project_mutation


class ProjectMutationUnitTests(unittest.TestCase):
    def _now(self) -> str:
        return "2026-03-08 12:00"

    def _base_project(self) -> dict:
        return {
            "id": "TMP",
            "name": "tmp",
            "flow": "generic",
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [],
            "blockers": [],
            "log": [],
        }

    def test_start_task_in_project_sets_status_and_template_hint(self):
        project = self._base_project()
        project["nodes"] = [
            {"id": "dep", "name": "Dependency", "phase": "P1", "status": "done"},
            {"id": "task", "name": "Task", "phase": "P1", "status": "pending", "depends": ["dep"]},
        ]

        result = project_mutation.start_task_in_project(
            project,
            "task",
            now=self._now,
            match_subtask_templates=lambda task_id: [{"id": "board_bringup"}] if task_id == "task" else [],
        )

        self.assertEqual(project["nodes"][1]["status"], "in_progress")
        self.assertEqual(project["nodes"][1]["started"], "2026-03-08 12:00")
        self.assertEqual(project["log"][-1]["action"], "start")
        self.assertEqual(result["_matched_templates"][0]["id"], "board_bringup")

    def test_done_task_in_project_updates_progress_and_note_file(self):
        project = self._base_project()
        project["nodes"] = [
            {"id": "dep", "name": "Dependency", "phase": "P1", "status": "done"},
            {"id": "task", "name": "Task", "phase": "P1", "status": "pending", "depends": ["dep"]},
            {"id": "next", "name": "Next", "phase": "P1", "status": "pending"},
        ]

        result = project_mutation.done_task_in_project(
            project,
            "task",
            now=self._now,
            note="done",
            note_file="docs/task.md",
        )

        task = project["nodes"][1]
        self.assertEqual(task["status"], "done")
        self.assertEqual(task["note_file"], "docs/task.md")
        self.assertEqual(task["docs"][0]["path"], "docs/task.md")
        self.assertEqual(result["progress"], "2/3")
        self.assertIn("Next", result["remaining_ready"])

    def test_unblock_task_in_project_falls_back_to_pending(self):
        project = self._base_project()
        project["nodes"] = [
            {"id": "dep", "name": "Dependency", "phase": "P1", "status": "pending"},
            {
                "id": "task",
                "name": "Task",
                "phase": "P1",
                "status": "blocked",
                "depends": ["dep"],
                "blocked_from_status": "in_progress",
                "blocked_reason": "wait",
            },
        ]
        project["blockers"] = [{"task_id": "task", "reason": "wait"}]

        result = project_mutation.unblock_task_in_project(project, "task", now=self._now)

        self.assertEqual(result["task"], "task")
        self.assertEqual(project["nodes"][1]["status"], "pending")
        self.assertNotIn("blocked_reason", project["nodes"][1])
        self.assertEqual(project["blockers"][0]["resolved"], "2026-03-08 12:00")

    def test_add_subtask_to_project_marks_parent_in_progress(self):
        project = self._base_project()
        project["nodes"] = [
            {"id": "parent", "name": "Parent", "phase": "P1", "status": "pending"},
        ]

        result = project_mutation.add_subtask_to_project(
            project,
            "parent",
            "child",
            "Child",
            now=self._now,
            owner="HW",
        )

        self.assertEqual(result["id"], "parent.child")
        self.assertEqual(project["nodes"][0]["status"], "in_progress")
        self.assertEqual(project["nodes"][0]["started"], "2026-03-08 12:00")

    def test_done_subtask_in_project_reports_expanded_parent_hint(self):
        project = self._base_project()
        project["nodes"] = [
            {"id": "parent", "name": "Parent", "phase": "P1", "status": "expanded"},
            {"id": "parent.a", "name": "A", "phase": "P1", "parent": "parent", "status": "done"},
            {"id": "parent.b", "name": "B", "phase": "P1", "parent": "parent", "status": "pending"},
        ]

        result = project_mutation.done_subtask_in_project(project, "parent.b", now=self._now)

        self.assertTrue(result["all_subtasks_done"])
        self.assertIn("父任务已由子任务替代", result["hint"])

    def test_attach_doc_to_task_rejects_duplicate_path(self):
        project = self._base_project()
        project["nodes"] = [
            {"id": "task", "name": "Task", "phase": "P1", "status": "pending", "docs": [{"path": "doc.md"}]},
        ]

        with self.assertRaises(ValueError):
            project_mutation.attach_doc_to_task(project, "task", "doc.md", now=self._now)


if __name__ == "__main__":
    unittest.main()
