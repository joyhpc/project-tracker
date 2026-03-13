"""post-save hooks — 项目保存后自动执行的操作

所有 hook 均为 best-effort，失败静默，不阻断主流程。
通过 core._save() 后自动调用 run_post_save_hooks()。

钩子协议:
  1. 内置钩子 (硬编码兜底)
  2. 外部钩子 (~/.pt/hooks.d/*.yaml) — 约定式扫描
"""
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:
    _yaml = None

# ── 钩子目录 ───────────────────────────────────────────────
HOOKS_DIR = Path.home() / ".pt" / "hooks.d"


def run_post_save_hooks(project: dict, event: str = "save") -> None:
    """保存后自动触发的 hooks。"""
    # 1. 内置钩子 (兜底)
    try:
        _auto_html_map(project)
    except Exception:
        pass

    try:
        _auto_review_sync(project, event)
    except Exception:
        pass

    # 2. 外部钩子 (约定式扫描)
    try:
        _run_external_hooks(project, event)
    except Exception:
        pass


# ── 外部钩子扫描 ──────────────────────────────────────────
def load_hooks() -> list[dict]:
    """从 ~/.pt/hooks.d/*.yaml 加载所有钩子定义。"""
    if _yaml is None:
        return []
    if not HOOKS_DIR.is_dir():
        return []

    hooks = []
    for f in sorted(HOOKS_DIR.glob("*.yaml")):
        try:
            data = _yaml.safe_load(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            data["_source_file"] = str(f)
            hooks.append(data)
        except Exception:
            continue
    return hooks


def _evaluate_condition(hook: dict) -> bool:
    """评估钩子的 condition 是否满足。

    支持的 condition 类型:
      - dir_exists <path>   — 目录存在则通过
      - file_exists <path>  — 文件存在则通过
      - 无 condition        — 始终通过
    """
    condition = hook.get("condition", "").strip()
    if not condition:
        return True

    # dir_exists ~/some/path
    if condition.startswith("dir_exists "):
        target = Path(os.path.expanduser(condition[len("dir_exists "):].strip()))
        return target.is_dir()

    # file_exists ~/some/path
    if condition.startswith("file_exists "):
        target = Path(os.path.expanduser(condition[len("file_exists "):].strip()))
        return target.is_file()

    # 未知 condition 类型 — 安全起见不执行
    return False


def _run_external_hooks(project: dict, event: str) -> None:
    """扫描并执行匹配当前 event 的外部钩子。"""
    hooks = load_hooks()
    for hook in hooks:
        events = hook.get("events", [])
        if event not in events:
            continue

        if not _evaluate_condition(hook):
            continue

        command = hook.get("command", "").strip()
        if not command:
            continue

        mode = hook.get("mode", "best-effort")

        try:
            # 展开 ~ 并设置环境变量
            env = os.environ.copy()
            env["PT_EVENT"] = event
            env["PT_PROJECT_ID"] = project.get("id", "")

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                cwd=os.path.expanduser("~"),
            )

            if result.returncode != 0 and mode != "best-effort":
                print(
                    f"⚠️  hook '{hook.get('name', '?')}' 失败 (rc={result.returncode})",
                    file=sys.stderr,
                )
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass


def list_hooks() -> list[dict]:
    """列出所有已注册的钩子（内置 + 外部），用于 `pt hooks` 命令。"""
    builtin = [
        {
            "name": "auto-html-map",
            "type": "builtin",
            "events": ["save", "done", "mutation"],
            "condition": "project has repo",
            "description": "保存后自动生成 HTML 项目地图",
        },
        {
            "name": "auto-review-sync",
            "type": "builtin",
            "events": ["done", "mutation", "save"],
            "condition": "dir_exists ~/sch-review/reports",
            "description": "自动同步 sch-review 审核报告",
        },
    ]

    external = []
    for hook in load_hooks():
        external.append({
            "name": hook.get("name", "unnamed"),
            "type": "external",
            "events": hook.get("events", []),
            "condition": hook.get("condition", ""),
            "command": hook.get("command", ""),
            "mode": hook.get("mode", "best-effort"),
            "source": hook.get("_source_file", ""),
            "description": hook.get("description", ""),
        })

    return builtin + external


def test_hook(hook_def: dict, project: dict) -> dict:
    """测试单个钩子 — 不实际执行 command，只检查 condition。"""
    cond_ok = _evaluate_condition(hook_def)
    return {
        "name": hook_def.get("name", "unnamed"),
        "condition_met": cond_ok,
        "command": hook_def.get("command", ""),
        "would_run": cond_ok and bool(hook_def.get("command", "")),
    }


# ── 内置钩子 (保持不变) ──────────────────────────────────
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
