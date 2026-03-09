"""Lightweight read-only HTTP server for the project-tracker kanban.

Uses only the Python standard library (``http.server``).
No request will ever trigger a YAML write -- the server is strictly read-only.
"""

from __future__ import annotations

import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

from tracker.web.data import load_all_projects, load_project_detail
from tracker.web.render import render_dashboard, render_project_list

# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

# Pre-compiled route patterns
_RE_PROJECT_PAGE = re.compile(r"^/project/([A-Za-z0-9_.-]+)$")
_RE_API_PROJECT = re.compile(r"^/api/project/([A-Za-z0-9_.-]+)$")


class _Handler(BaseHTTPRequestHandler):
    """Simple router that dispatches GET requests to the appropriate handler."""

    # Suppress default stderr logging per-request (keep it clean)
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        pass  # silent by default; override for debugging

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/") or "/"

        if path == "/":
            self._handle_index()
        elif path == "/api/projects":
            self._handle_api_projects()
        else:
            m = _RE_PROJECT_PAGE.match(path)
            if m:
                self._handle_project_page(m.group(1))
                return

            m = _RE_API_PROJECT.match(path)
            if m:
                self._handle_api_project(m.group(1))
                return

            self._send_error(404, "Not Found")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_index(self) -> None:
        projects = load_all_projects()
        html = render_project_list(projects)
        self._send_html(html)

    def _handle_project_page(self, project_id: str) -> None:
        detail = load_project_detail(project_id)
        if detail is None:
            self._send_error(404, f"Project '{project_id}' not found.")
            return
        html = render_dashboard(detail)
        self._send_html(html)

    def _handle_api_projects(self) -> None:
        projects = load_all_projects()
        self._send_json(projects)

    def _handle_api_project(self, project_id: str) -> None:
        detail = load_project_detail(project_id)
        if detail is None:
            self._send_json({"error": f"Project '{project_id}' not found."}, status=404)
            return
        self._send_json(detail)

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        html = (
            f"<!DOCTYPE html><html><head><title>{status}</title></head>"
            f"<body style='font-family:sans-serif;padding:2rem;'>"
            f"<h1>{status}</h1><p>{message}</p>"
            f"<p><a href='/'>Back to project list</a></p></body></html>"
        )
        self._send_html(html, status)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def start_server(host: str = "localhost", port: int = 8080) -> None:
    """Start the read-only web kanban server."""
    server = HTTPServer((host, port), _Handler)
    print(f"Project Tracker kanban running on http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\nServer stopped.")
