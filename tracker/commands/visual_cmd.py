"""Project map commands: terminal map and HTML/PNG visual export."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .. import core
from ..project_map import build_project_map, render_project_map_html, render_project_map_text


def _require_project() -> dict:
    try:
        return core.require_active()
    except RuntimeError as exc:
        print(f"❌ {exc}")
        sys.exit(1)


def _write_map_files(map_data: dict, output: str | None, no_png: bool) -> tuple[Path, Path | None]:
    out_dir = Path(output) if output else Path("/tmp")
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{map_data['project_id'].lower()}-project-map.html"
    png_path = out_dir / f"{map_data['project_id'].lower()}-project-map.png"
    html_path.write_text(render_project_map_html(map_data), encoding="utf-8")
    print(f"📄 HTML: {html_path}")

    if no_png:
        return html_path, None

    if _screenshot_2x(html_path, png_path):
        print(f"🖼️  PNG: {png_path}")
        return html_path, png_path

    print("⚠️  截图跳过（playwright / chrome 不可用）")
    return html_path, None


def cmd_map(args):
    project = _require_project()
    map_data = build_project_map(project)
    print(render_project_map_text(map_data), end="")

    if getattr(args, "html", False):
        _write_map_files(map_data, getattr(args, "output", "/tmp"), getattr(args, "no_png", False))


def cmd_visual(args):
    project = _require_project()
    map_data = build_project_map(project)
    _write_map_files(map_data, getattr(args, "output", "/tmp"), getattr(args, "no_png", False))


def _screenshot_2x(html_path: Path, png_path: Path) -> bool:
    chrome = _find_chrome()
    pw_core = _find_playwright_core()
    if not chrome or not pw_core:
        try:
            subprocess.run(
                [
                    "npx",
                    "playwright",
                    "screenshot",
                    "--full-page",
                    "--viewport-size=1800,2200",
                    f"file://{html_path.resolve()}",
                    str(png_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return png_path.exists() and png_path.stat().st_size > 0
        except Exception:
            return False

    try:
        js = f"""
const {{ chromium }} = require('{pw_core}');
(async () => {{
  const browser = await chromium.launch({{ executablePath: '{chrome}' }});
  const context = await browser.newContext({{ deviceScaleFactor: 2, viewport: {{ width: 1440, height: 1800 }} }});
  const page = await context.newPage();
  await page.goto('file://{html_path.resolve()}');
  await page.waitForTimeout(500);
  await page.screenshot({{ path: '{png_path}', fullPage: true }});
  await browser.close();
}})();
"""
        subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30, check=False)
        return png_path.exists() and png_path.stat().st_size > 0
    except Exception:
        return False


def _find_playwright_core() -> str | None:
    import glob

    patterns = [
        Path.home() / ".npm-global/lib/node_modules/openclaw/node_modules/playwright-core",
        Path.home() / ".npm-global/lib/node_modules/playwright-core",
    ]
    for pattern in patterns:
        if pattern.exists():
            return str(pattern)
    for match in glob.glob(str(Path.home() / ".npm-global/**/playwright-core/index.js"), recursive=True):
        return str(Path(match).parent)
    return None


def _find_chrome() -> str | None:
    pw_dir = Path.home() / ".cache/ms-playwright"
    if pw_dir.exists():
        for path in sorted(pw_dir.iterdir(), reverse=True):
            if path.name.startswith("chromium-"):
                chrome = path / "chrome-linux64" / "chrome"
                if chrome.exists():
                    return str(chrome)
    candidate = Path.home() / ".cache/ms-playwright/chromium-1208/chrome-linux64/chrome"
    return str(candidate) if candidate.exists() else None
