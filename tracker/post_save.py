"""post-save hooks — 项目保存后自动执行的操作

所有 hook 均为 best-effort，失败静默，不阻断主流程。
通过 core._save() 后自动调用 run_post_save_hooks()。
"""
import os
from pathlib import Path


def run_post_save_hooks(project: dict, event: str = "save") -> None:
    """保存后自动触发的 hooks。"""
    try:
        _auto_html_map(project)
    except Exception:
        pass

    try:
        _auto_review_sync(project, event)
    except Exception:
        pass


def _auto_html_map(project: dict) -> None:
    """自动生成 HTML 项目地图到 repo 目录。

    只在 repo 存在时执行，避免无意义的输出。
    """
    repo = (project.get("repo") or "").strip()
    if not repo:
        return
    repo_path = Path(repo).expanduser()
    if not repo_path.is_dir():
        return

    from .project_query import get_status
    from .project_map import build_project_map, render_project_map_html

    info = get_status(project)
    map_data = build_project_map(project, info)
    html = render_project_map_html(map_data)

    pid = project.get("id", "project").lower()
    out = repo_path / f"{pid}_project_map.html"
    out.write_text(html, encoding="utf-8")


def _auto_review_sync(project: dict, event: str) -> None:
    """审核相关事件后自动同步 sch-review 报告。

    仅在 done/mutation 事件时触发，且只在 ~/sch-review/reports 存在时执行。
    """
    if event not in ("done", "mutation", "save"):
        return

    reports_dir = Path.home() / "sch-review" / "reports"
    if not reports_dir.is_dir():
        return

    # 只做增量检查：看是否有未注册的报告
    existing_files = set()
    for rv in project.get("reviews", []):
        existing_files.add(rv.get("file", ""))

    import re
    from datetime import datetime as dt

    new_count = 0
    for rpt in sorted(reports_dir.rglob("*.md")):
        abs_path = str(rpt)
        if abs_path in existing_files:
            continue

        try:
            content = rpt.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue

        # 只处理有 P0/P1/P2 标记的文件
        p0 = len(re.findall(r'\bP0\b', content))
        p1 = len(re.findall(r'\bP1\b', content))
        p2 = len(re.findall(r'\bP2\b', content))
        if p0 + p1 + p2 == 0:
            continue

        verdict = "NO-GO" if p0 > 0 else ("CAUTION" if p1 > 0 else "GO")

        # 提取标题
        title = ""
        for line in content.split("\n")[:20]:
            m = re.match(r'^#\s+(.*)', line)
            if m:
                title = m.group(1).strip()
                break

        review_entry = {
            "file": abs_path,
            "source": "auto-sync",
            "title": title or rpt.name,
            "verdicts": [{"verdict": verdict}],
            "synced": dt.now().strftime("%Y-%m-%d %H:%M"),
            "p0_count": p0,
            "p1_count": p1,
            "p2_count": p2,
        }

        if "reviews" not in project:
            project["reviews"] = []
        project["reviews"].append(review_entry)
        existing_files.add(abs_path)
        new_count += 1

    # 如果有新注册的，需要重新保存（但避免递归）
    # 不在这里保存 — 调用方会在下一次 _save 时持久化
    if new_count > 0:
        project["_reviews_auto_synced"] = new_count
