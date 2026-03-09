"""Tests for the tracker.datax package (stats, gantt, deps_graph)."""
from __future__ import annotations

import unittest


class PhaseStatsTests(unittest.TestCase):
    """Tests for datax/stats.py"""

    def setUp(self):
        self.project = {
            "nodes": [
                {"id": "a", "name": "A", "phase": "PLAN", "status": "done", "days": 5,
                 "started": "2025-01-01 09:00", "completed": "2025-01-04 09:00"},
                {"id": "b", "name": "B", "phase": "PLAN", "status": "done", "days": 3},
                {"id": "c", "name": "C", "phase": "DETAIL", "status": "in_progress", "days": 4},
                {"id": "d", "name": "D", "phase": "DETAIL", "status": "pending", "days": 2},
                {"id": "e", "name": "E", "phase": "PLAN", "status": "expanded"},  # should be excluded
            ]
        }

    def test_compute_phase_stats_groups_by_phase(self):
        """按 phase 分组统计"""
        from tracker.datax.stats import compute_phase_stats

        result = compute_phase_stats(self.project)
        self.assertIn("PLAN", result)
        self.assertIn("DETAIL", result)
        self.assertIn("overall", result)

    def test_compute_phase_stats_excludes_expanded(self):
        """排除 expanded 节点"""
        from tracker.datax.stats import compute_phase_stats

        result = compute_phase_stats(self.project)
        # Node "e" has status=expanded, so PLAN should have count=2 (a + b), not 3
        self.assertEqual(result["PLAN"]["count"], 2)

    def test_compute_phase_stats_actual_days_from_timestamps(self):
        """有时间戳时用实际耗时"""
        from tracker.datax.stats import compute_phase_stats

        result = compute_phase_stats(self.project)
        # Node "a" has started 2025-01-01 09:00 and completed 2025-01-04 09:00 = exactly 3 days
        # Node "b" has no timestamps, so it falls back to days=3
        # avg = (3.0 + 3.0) / 2 = 3.0
        self.assertEqual(result["PLAN"]["avg_days"], 3.0)

    def test_compute_phase_stats_overall_summary(self):
        """overall 汇总正确"""
        from tracker.datax.stats import compute_phase_stats

        result = compute_phase_stats(self.project)
        overall = result["overall"]
        # 4 effective nodes (a, b, c, d — e is expanded)
        self.assertEqual(overall["total_nodes"], 4)
        self.assertEqual(overall["done"], 2)
        self.assertEqual(overall["in_progress"], 1)
        self.assertEqual(overall["pending"], 1)
        self.assertEqual(overall["blocked"], 0)

    def test_compute_phase_stats_done_count(self):
        """phase 内 done 计数正确"""
        from tracker.datax.stats import compute_phase_stats

        result = compute_phase_stats(self.project)
        self.assertEqual(result["PLAN"]["done"], 2)
        self.assertEqual(result["DETAIL"]["done"], 0)

    def test_compute_phase_stats_no_done_nodes(self):
        """无已完成节点时统计值为 0"""
        from tracker.datax.stats import compute_phase_stats

        project = {
            "nodes": [
                {"id": "x", "name": "X", "phase": "P", "status": "pending", "days": 5},
            ]
        }
        result = compute_phase_stats(project)
        self.assertEqual(result["P"]["avg_days"], 0.0)
        self.assertEqual(result["P"]["p50"], 0.0)
        self.assertEqual(result["P"]["p90"], 0.0)
        self.assertEqual(result["P"]["max"], 0.0)

    def test_percentile_edge_cases(self):
        """百分位计算边界: 空列表、单元素"""
        from tracker.datax.stats import _percentile

        # Empty list -> 0.0
        self.assertEqual(_percentile([], 50), 0.0)
        self.assertEqual(_percentile([], 90), 0.0)

        # Single element
        self.assertEqual(_percentile([7.0], 50), 7.0)
        self.assertEqual(_percentile([7.0], 90), 7.0)
        self.assertEqual(_percentile([7.0], 100), 7.0)

    def test_percentile_multiple_values(self):
        """百分位计算: 多元素"""
        from tracker.datax.stats import _percentile

        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        p50 = _percentile(vals, 50)
        p90 = _percentile(vals, 90)
        self.assertTrue(1.0 <= p50 <= 5.0)
        self.assertTrue(p50 <= p90)

    def test_node_actual_days_missing_timestamps(self):
        """缺少时间戳时返回 None"""
        from tracker.datax.stats import _node_actual_days

        self.assertIsNone(_node_actual_days({}))
        self.assertIsNone(_node_actual_days({"started": "2025-01-01 09:00"}))
        self.assertIsNone(_node_actual_days({"completed": "2025-01-04 09:00"}))

    def test_node_actual_days_valid_timestamps(self):
        """有效时间戳计算实际天数"""
        from tracker.datax.stats import _node_actual_days

        node = {"started": "2025-01-01 09:00", "completed": "2025-01-04 09:00"}
        result = _node_actual_days(node)
        self.assertIsNotNone(result)
        self.assertEqual(result, 3.0)


class GanttExportTests(unittest.TestCase):
    """Tests for datax/gantt.py"""

    def setUp(self):
        self.project = {
            "id": "test",
            "name": "Test Project",
            "phases": [{"id": "P1", "name": "Phase 1"}],
            "nodes": [
                {"id": "t1", "name": "Task 1", "phase": "P1", "status": "done", "days": 3, "depends": []},
                {"id": "t2", "name": "Task 2", "phase": "P1", "status": "pending", "days": 5, "depends": ["t1"]},
            ],
            "log": [], "blockers": [], "reviews": [], "decisions": [], "pocs": [],
            "schema_version": 2,
        }

    def test_export_gantt_contains_header(self):
        """输出包含 gantt 头和 title"""
        from tracker.datax.gantt import export_gantt_mermaid

        output = export_gantt_mermaid(self.project)
        self.assertIn("gantt", output)
        self.assertIn("title Test Project", output)
        self.assertIn("dateFormat", output)

    def test_export_gantt_contains_sections(self):
        """输出包含 section Phase 1"""
        from tracker.datax.gantt import export_gantt_mermaid

        output = export_gantt_mermaid(self.project)
        self.assertIn("section Phase 1", output)

    def test_export_gantt_contains_task_names(self):
        """输出包含任务名称"""
        from tracker.datax.gantt import export_gantt_mermaid

        output = export_gantt_mermaid(self.project)
        self.assertIn("Task 1", output)
        self.assertIn("Task 2", output)

    def test_export_gantt_contains_done_tag(self):
        """已完成的任务包含 done 标记"""
        from tracker.datax.gantt import export_gantt_mermaid

        output = export_gantt_mermaid(self.project)
        # The done task should have a "done" tag
        self.assertIn("done", output)

    def test_export_gantt_contains_after_clause(self):
        """有依赖的任务包含 after 子句"""
        from tracker.datax.gantt import export_gantt_mermaid

        output = export_gantt_mermaid(self.project)
        self.assertIn("after t1", output)

    def test_export_gantt_sanitises_hyphens(self):
        """连字符 ID 被替换为下划线"""
        from tracker.datax.gantt import export_gantt_mermaid

        project = {
            "id": "test",
            "name": "Test",
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [
                {"id": "my-task", "name": "My Task", "phase": "P1", "status": "pending", "days": 2, "depends": []},
            ],
            "log": [], "blockers": [], "reviews": [], "decisions": [], "pocs": [],
            "schema_version": 2,
        }
        output = export_gantt_mermaid(project)
        # Hyphens in IDs should be replaced with underscores
        self.assertIn("my_task", output)

    def test_export_gantt_returns_string_ending_newline(self):
        """输出以换行结尾"""
        from tracker.datax.gantt import export_gantt_mermaid

        output = export_gantt_mermaid(self.project)
        self.assertIsInstance(output, str)
        self.assertTrue(output.endswith("\n"))


class DepsGraphTests(unittest.TestCase):
    """Tests for datax/deps_graph.py"""

    def setUp(self):
        self.project = {
            "id": "test",
            "name": "Test Project",
            "phases": [{"id": "P1", "name": "Phase 1"}],
            "nodes": [
                {"id": "t1", "name": "Task 1", "phase": "P1", "status": "done", "days": 3, "depends": []},
                {"id": "t2", "name": "Task 2", "phase": "P1", "status": "pending", "days": 5, "depends": ["t1"]},
            ],
            "log": [], "blockers": [], "reviews": [], "decisions": [], "pocs": [],
            "schema_version": 2,
        }

    def test_export_deps_contains_graph_header(self):
        """输出以 graph LR 开头"""
        from tracker.datax.deps_graph import export_deps_mermaid

        output = export_deps_mermaid(self.project)
        self.assertTrue(output.startswith("graph LR"))

    def test_export_deps_includes_edges(self):
        """有依赖关系时包含 --> 边"""
        from tracker.datax.deps_graph import export_deps_mermaid

        output = export_deps_mermaid(self.project)
        self.assertIn("-->", output)
        # t1 --> t2 (dependency edge)
        self.assertIn("t1", output)
        self.assertIn("t2", output)

    def test_export_deps_colors_by_status(self):
        """不同状态的节点有不同颜色"""
        from tracker.datax.deps_graph import export_deps_mermaid

        output = export_deps_mermaid(self.project)
        # done -> green
        self.assertIn("#4CAF50", output)
        # pending -> grey
        self.assertIn("#9E9E9E", output)

    def test_export_deps_includes_node_labels(self):
        """输出包含节点标签"""
        from tracker.datax.deps_graph import export_deps_mermaid

        output = export_deps_mermaid(self.project)
        self.assertIn("Task 1", output)
        self.assertIn("Task 2", output)

    def test_export_deps_sanitises_hyphens(self):
        """连字符 ID 被替换为下划线"""
        from tracker.datax.deps_graph import export_deps_mermaid

        project = {
            "id": "test",
            "name": "Test",
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [
                {"id": "my-node", "name": "My Node", "phase": "P1", "status": "done", "days": 2, "depends": []},
            ],
            "log": [], "blockers": [], "reviews": [], "decisions": [], "pocs": [],
            "schema_version": 2,
        }
        output = export_deps_mermaid(project)
        self.assertIn("my_node", output)

    def test_export_deps_returns_string_ending_newline(self):
        """输出以换行结尾"""
        from tracker.datax.deps_graph import export_deps_mermaid

        output = export_deps_mermaid(self.project)
        self.assertIsInstance(output, str)
        self.assertTrue(output.endswith("\n"))

    def test_export_deps_critical_path_bold_stroke(self):
        """关键路径节点有加粗边框样式"""
        from tracker.datax.deps_graph import export_deps_mermaid

        output = export_deps_mermaid(self.project)
        # At least one node should be on the critical path and get stroke-width:3px
        self.assertIn("stroke-width:3px", output)

    def test_export_deps_excludes_expanded_nodes(self):
        """排除 expanded 状态节点"""
        from tracker.datax.deps_graph import export_deps_mermaid

        project = {
            "id": "test",
            "name": "Test",
            "phases": [{"id": "P1", "name": "P1"}],
            "nodes": [
                {"id": "parent", "name": "Parent", "phase": "P1", "status": "expanded", "days": 3, "depends": []},
                {"id": "child", "name": "Child", "phase": "P1", "status": "pending", "days": 2, "depends": []},
            ],
            "log": [], "blockers": [], "reviews": [], "decisions": [], "pocs": [],
            "schema_version": 2,
        }
        output = export_deps_mermaid(project)
        # "parent" node is expanded and should not appear
        self.assertNotIn("Parent", output)
        self.assertIn("Child", output)


class SanitiseMermaidIdTests(unittest.TestCase):
    """Tests for datax/__init__.py sanitise_mermaid_id"""

    def test_replaces_hyphens_with_underscores(self):
        from tracker.datax import sanitise_mermaid_id

        self.assertEqual(sanitise_mermaid_id("a-b-c"), "a_b_c")

    def test_no_hyphens_unchanged(self):
        from tracker.datax import sanitise_mermaid_id

        self.assertEqual(sanitise_mermaid_id("abc"), "abc")


if __name__ == "__main__":
    unittest.main()
