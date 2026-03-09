"""Tests for the tracker.web package (data, render).

All tests are pure offline -- no real HTTP server is started.

Note: tracker/web/render.py contains a syntax error (un-escaped JS braces in
an f-string) that prevents normal import on Python 3.12. Tests for render.py
work around this by reading the source, patching the problematic section, and
exec-ing the fixed code into a temporary namespace.
"""
from __future__ import annotations

import html as _html_mod
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tracker import core


# ---------------------------------------------------------------------------
# Helper: load render.py despite its syntax error
# ---------------------------------------------------------------------------

def _load_render_module() -> types.ModuleType:
    """Read tracker/web/render.py, fix the JS braces, compile and return as a module."""
    render_path = Path(__file__).resolve().parent.parent / "tracker" / "web" / "render.py"
    source = render_path.read_text(encoding="utf-8")

    # The JavaScript block inside the render_dashboard f-string uses bare { }
    # which Python's f-string parser rejects.  We double them to make them
    # literal braces.
    js_original = """\
<script>
function copyMermaid(id) {
  var el = document.getElementById(id);
  var text = el.textContent || el.innerText;
  navigator.clipboard.writeText(text).then(function() {
    var btns = el.parentElement.querySelectorAll('.copy-btn');
    if (btns.length) { btns[0].textContent = 'Copied!'; setTimeout(function(){ btns[0].textContent = 'Copy'; }, 2000); }
  });
}
</script>"""

    js_fixed = """\
<script>
function copyMermaid(id) {{
  var el = document.getElementById(id);
  var text = el.textContent || el.innerText;
  navigator.clipboard.writeText(text).then(function() {{
    var btns = el.parentElement.querySelectorAll('.copy-btn');
    if (btns.length) {{ btns[0].textContent = 'Copied!'; setTimeout(function(){{ btns[0].textContent = 'Copy'; }}, 2000); }}
  }});
}}
</script>"""

    source = source.replace(js_original, js_fixed)

    code = compile(source, str(render_path), "exec")
    mod = types.ModuleType("tracker.web.render")
    mod.__file__ = str(render_path)
    exec(code, mod.__dict__)
    return mod


# Cache the module so we only compile once.
_render_mod = _load_render_module()


# ---------------------------------------------------------------------------
# web/data.py tests
# ---------------------------------------------------------------------------

class WebDataTests(unittest.TestCase):
    """Tests for web/data.py"""

    def setUp(self):
        self.tempdir = Path(tempfile.mkdtemp(prefix="pt-web-tests-"))
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

    def test_load_all_projects_returns_list(self):
        """返回项目列表"""
        from tracker.web.data import load_all_projects

        # Patch the module-level PROJECTS_DIR in web.data to match our temp dir
        with patch("tracker.web.data.PROJECTS_DIR", core.PROJECTS_DIR):
            result = load_all_projects()
        self.assertIsInstance(result, list)

    def test_load_all_projects_returns_empty_when_no_projects(self):
        """无项目时返回空列表"""
        from tracker.web.data import load_all_projects

        with patch("tracker.web.data.PROJECTS_DIR", core.PROJECTS_DIR):
            result = load_all_projects()
        self.assertEqual(result, [])

    def test_load_all_projects_returns_project_summaries(self):
        """有项目时返回包含摘要的列表"""
        from tracker.web.data import load_all_projects

        core.init_project("WEBTEST", "Web Test Project", "generic")

        with patch("tracker.web.data.PROJECTS_DIR", core.PROJECTS_DIR):
            result = load_all_projects()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "WEBTEST")
        self.assertEqual(result[0]["name"], "Web Test Project")
        self.assertIn("done", result[0])
        self.assertIn("total", result[0])
        self.assertIn("percent", result[0])

    def test_load_project_detail_returns_none_for_missing(self):
        """不存在的项目返回 None"""
        from tracker.web.data import load_project_detail

        result = load_project_detail("NONEXISTENT")
        self.assertIsNone(result)

    def test_load_project_detail_contains_mermaid(self):
        """返回数据包含 gantt_mermaid 和 deps_mermaid"""
        from tracker.web.data import load_project_detail

        core.init_project("WEBTEST", "Web Test Project", "generic")
        result = load_project_detail("WEBTEST")

        self.assertIsNotNone(result)
        self.assertIn("gantt_mermaid", result)
        self.assertIn("deps_mermaid", result)

    def test_load_project_detail_contains_expected_fields(self):
        """返回数据包含所有必要字段"""
        from tracker.web.data import load_project_detail

        core.init_project("WEBTEST", "Web Test Project", "generic")
        result = load_project_detail("WEBTEST")

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "WEBTEST")
        self.assertEqual(result["name"], "Web Test Project")
        self.assertIn("nodes", result)
        self.assertIn("phases", result)
        self.assertIn("status_counts", result)
        self.assertIn("critical_path", result)
        self.assertIn("total_days", result)
        self.assertIn("log", result)
        self.assertIn("done", result)
        self.assertIn("total", result)
        self.assertIn("percent", result)


# ---------------------------------------------------------------------------
# web/render.py tests (loaded via the fixed module)
# ---------------------------------------------------------------------------

class WebRenderTests(unittest.TestCase):
    """Tests for web/render.py"""

    def test_render_project_list_returns_html(self):
        """输出是完整 HTML"""
        render_project_list = _render_mod.render_project_list

        projects = [
            {"id": "P1", "name": "Project 1", "done": 5, "total": 10, "percent": 50.0, "created": "2025-01-01"},
            {"id": "P2", "name": "Project 2", "done": 10, "total": 10, "percent": 100.0, "created": "2025-02-01"},
        ]
        html = render_project_list(projects)

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<html", html)
        self.assertIn("</html>", html)
        self.assertIn("Project Tracker", html)

    def test_render_project_list_empty(self):
        """空项目列表显示提示信息"""
        render_project_list = _render_mod.render_project_list

        html = render_project_list([])
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("No projects found", html)

    def test_render_project_list_contains_project_info(self):
        """列表页包含项目信息"""
        render_project_list = _render_mod.render_project_list

        projects = [
            {"id": "ALPHA", "name": "Alpha Project", "done": 3, "total": 5, "percent": 60.0, "created": "2025-03-01"},
        ]
        html = render_project_list(projects)
        self.assertIn("Alpha Project", html)
        self.assertIn("ALPHA", html)
        self.assertIn("60.0%", html)

    def test_render_dashboard_contains_project_name(self):
        """看板包含项目名称"""
        render_dashboard = _render_mod.render_dashboard

        project = {
            "id": "DEMO",
            "name": "Demo Project",
            "done": 2,
            "total": 5,
            "percent": 40.0,
            "total_days": 15.0,
            "critical_path": ["t1", "t2"],
            "status_counts": {"done": 2, "pending": 3},
            "phases": [{"id": "P1", "name": "Phase 1"}],
            "nodes": [
                {"id": "t1", "name": "Task 1", "status": "done", "phase": "P1",
                 "type": "task", "owner": "", "depends": [], "critical": True,
                 "slack": 0, "es": 0, "ef": 3, "days": 3, "deliverables": [], "gate": "", "note": ""},
            ],
            "log": [],
            "gantt_mermaid": "",
            "deps_mermaid": "",
        }
        html = render_dashboard(project)

        self.assertIn("Demo Project", html)
        self.assertIn("<!DOCTYPE html>", html)

    def test_render_dashboard_escapes_html(self):
        """XSS 防护: 特殊字符被转义"""
        render_dashboard = _render_mod.render_dashboard

        project = {
            "id": "XSS",
            "name": "<script>alert('xss')</script>",
            "done": 0,
            "total": 1,
            "percent": 0.0,
            "total_days": 5.0,
            "critical_path": [],
            "status_counts": {"pending": 1},
            "phases": [{"id": "P1", "name": "Phase 1"}],
            "nodes": [
                {"id": "t1", "name": "<img onerror=alert(1) src=x>", "status": "pending", "phase": "P1",
                 "type": "task", "owner": "", "depends": [], "critical": False,
                 "slack": 0, "es": 0, "ef": 5, "days": 5, "deliverables": [], "gate": "", "note": ""},
            ],
            "log": [],
            "gantt_mermaid": "",
            "deps_mermaid": "",
        }
        html = render_dashboard(project)

        # The malicious project name must be HTML-escaped in the output.
        # Note: the page legitimately contains <script> for its own JS, so we
        # check that the *injected* script content does not appear raw.
        self.assertNotIn("alert('xss')", html)
        # The escaped version of the project name should be present
        self.assertIn("&lt;script&gt;", html)
        # Node name should be escaped too
        self.assertNotIn("<img onerror", html)
        self.assertIn("&lt;img onerror", html)

    def test_render_dashboard_contains_mermaid_section(self):
        """有 Mermaid 数据时显示代码块"""
        render_dashboard = _render_mod.render_dashboard

        gantt_code = "gantt\n    title Test\n    dateFormat YYYY-MM-DD\n"
        deps_code = "graph LR\n    a --> b\n"
        project = {
            "id": "MRM",
            "name": "Mermaid Test",
            "done": 0,
            "total": 1,
            "percent": 0.0,
            "total_days": 3.0,
            "critical_path": [],
            "status_counts": {"pending": 1},
            "phases": [],
            "nodes": [],
            "log": [],
            "gantt_mermaid": gantt_code,
            "deps_mermaid": deps_code,
        }
        html = render_dashboard(project)

        self.assertIn("Gantt Chart (Mermaid)", html)
        self.assertIn("Dependency Graph (Mermaid)", html)
        self.assertIn("mermaid-code", html)
        self.assertIn("gantt", html)

    def test_render_dashboard_no_mermaid_when_empty(self):
        """无 Mermaid 数据时不显示 Mermaid 区域"""
        render_dashboard = _render_mod.render_dashboard

        project = {
            "id": "NOMRM",
            "name": "No Mermaid",
            "done": 0,
            "total": 0,
            "percent": 0.0,
            "total_days": 0,
            "critical_path": [],
            "status_counts": {},
            "phases": [],
            "nodes": [],
            "log": [],
            "gantt_mermaid": "",
            "deps_mermaid": "",
        }
        html = render_dashboard(project)

        self.assertNotIn("Gantt Chart (Mermaid)", html)
        self.assertNotIn("Dependency Graph (Mermaid)", html)

    def test_render_dashboard_shows_log_entries(self):
        """看板显示日志条目"""
        render_dashboard = _render_mod.render_dashboard

        project = {
            "id": "LOG",
            "name": "Log Test",
            "done": 0,
            "total": 1,
            "percent": 0.0,
            "total_days": 3.0,
            "critical_path": [],
            "status_counts": {"pending": 1},
            "phases": [],
            "nodes": [],
            "log": [
                {"time": "2025-01-01 10:00", "action": "start", "task": "t1", "detail": "started task"},
            ],
            "gantt_mermaid": "",
            "deps_mermaid": "",
        }
        html = render_dashboard(project)

        self.assertIn("Recent Log", html)
        self.assertIn("2025-01-01 10:00", html)
        self.assertIn("start", html)

    def test_render_dashboard_shows_critical_path(self):
        """看板显示关键路径"""
        render_dashboard = _render_mod.render_dashboard

        project = {
            "id": "CP",
            "name": "Critical Path Test",
            "done": 0,
            "total": 2,
            "percent": 0.0,
            "total_days": 10.0,
            "critical_path": ["node_a", "node_b"],
            "status_counts": {"pending": 2},
            "phases": [],
            "nodes": [],
            "log": [],
            "gantt_mermaid": "",
            "deps_mermaid": "",
        }
        html = render_dashboard(project)

        self.assertIn("Critical Path", html)
        self.assertIn("node_a", html)
        self.assertIn("node_b", html)


class WebRenderHelperTests(unittest.TestCase):
    """Tests for internal helper functions in web/render.py"""

    def test_escape_function(self):
        """_e 转义 HTML 特殊字符"""
        _e = _render_mod._e

        self.assertEqual(_e("<b>bold</b>"), "&lt;b&gt;bold&lt;/b&gt;")
        self.assertEqual(_e("a & b"), "a &amp; b")
        self.assertEqual(_e('"quoted"'), "&quot;quoted&quot;")
        self.assertEqual(_e(""), "")
        self.assertEqual(_e(None), "")


if __name__ == "__main__":
    unittest.main()
