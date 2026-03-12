"""review-sync 命令 — 自动同步 sch-review 审核报告到 pt reviews

扫描指定目录（默认 ~/sch-review/reports/）中的审核报告，
解析 P0/P1/P2 标记，映射为 pt 的 NO-GO/CAUTION/GO verdict，
自动注册到当前项目的 reviews[] 字段。
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from .. import core


def _detect_severity(content: str) -> dict:
    """从审核报告内容中提取 P0/P1/P2 计数和最高严重级别。"""
    counts = {}
    for sev in ("P0", "P1", "P2", "P3", "P4"):
        # 匹配独立的 P0/P1 等标记
        matches = re.findall(rf'\b{sev}\b', content)
        counts[sev] = len(matches)

    if counts["P0"] > 0:
        verdict = "NO-GO"
    elif counts["P1"] > 0:
        verdict = "CAUTION"
    else:
        verdict = "GO"

    return {"counts": counts, "verdict": verdict}


def _extract_title(content: str) -> str:
    """提取 Markdown 文件标题。"""
    for line in content.split("\n")[:20]:
        m = re.match(r'^#\s+(.*)', line)
        if m:
            return m.group(1).strip()
    return ""


def _extract_board_name(filepath: str) -> str:
    """从文件名或路径中提取板名。"""
    name = Path(filepath).stem
    # A57_GWBRGIC_TST_deep_review → GWBRGIC
    # A57_PMU_NA_review → PMU_NA
    m = re.search(r'A57[_-](\w+?)(?:[_-](?:review|deep|fix|report|checklist|tree|comprehensive|phase|architecture))', name, re.IGNORECASE)
    if m:
        return m.group(1)
    return name


def cmd_review_sync(args):
    """扫描 sch-review 报告目录并同步到 pt。"""
    try:
        project = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # 确定扫描目录
    scan_dir = getattr(args, "dir", None)
    if not scan_dir:
        scan_dir = os.path.expanduser("~/sch-review/reports")
    scan_path = Path(scan_dir)

    if not scan_path.is_dir():
        print(f"❌ 目录不存在: {scan_dir}")
        sys.exit(1)

    # 收集已注册的文件路径（避免重复）
    repo = project.get("repo", "")
    existing = set()
    for rv in project.get("reviews", []):
        existing.add(rv.get("file", ""))

    # 扫描 Markdown 文件
    reports = sorted(scan_path.rglob("*.md"))
    if not reports:
        print(f"📂 {scan_dir} 中没有找到 Markdown 报告")
        return

    print(f"\n📂 扫描 sch-review 报告: {scan_dir}")
    print(f"   找到 {len(reports)} 个 Markdown 文件\n")

    registered = 0
    skipped = 0

    for rpt in reports:
        try:
            content = rpt.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        title = _extract_title(content)
        sev = _detect_severity(content)
        board = _extract_board_name(str(rpt))

        # 相对路径用于显示
        rel = os.path.relpath(rpt, scan_dir)

        # 检查是否有 P0/P1/P2 内容（跳过无审核标记的通用文档）
        total_findings = sum(sev["counts"].get(s, 0) for s in ("P0", "P1", "P2"))
        if total_findings == 0:
            continue

        # 检查是否已注册
        # 尝试用多种路径格式匹配
        abs_path = str(rpt)
        if abs_path in existing or rel in existing:
            skipped += 1
            continue

        # 显示状态
        icon = {"NO-GO": "🔴", "CAUTION": "🟡", "GO": "🟢"}[sev["verdict"]]
        p0_str = f"P0={sev['counts']['P0']}" if sev['counts']['P0'] else ""
        p1_str = f"P1={sev['counts']['P1']}" if sev['counts']['P1'] else ""
        p2_str = f"P2={sev['counts']['P2']}" if sev['counts']['P2'] else ""
        counts_str = "  ".join(filter(None, [p0_str, p1_str, p2_str]))

        print(f"  {icon} {rel}")
        if title:
            print(f"     {title}")
        print(f"     板名={board}  {counts_str}  verdict={sev['verdict']}")

        registered += 1
        if not getattr(args, "dry_run", False):
            # 注册到项目
            review_entry = {
                "file": abs_path,
                "source": "sch-review-sync",
                "board": board,
                "title": title or rel,
                "verdicts": [{"verdict": sev["verdict"]}],
                "synced": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "p0_count": sev["counts"]["P0"],
                "p1_count": sev["counts"]["P1"],
                "p2_count": sev["counts"]["P2"],
            }
            if "reviews" not in project:
                project["reviews"] = []
            project["reviews"].append(review_entry)

        print()

    if registered > 0 and not getattr(args, "dry_run", False):
        core._save(project)

    # 汇总
    print("─" * 50)
    if getattr(args, "dry_run", False):
        print(f"🔍 试运行完成 — 发现 {registered} 个可注册报告, 已存在 {skipped} 个")
    else:
        print(f"✅ 同步完成 — 新注册 {registered} 个, 已存在 {skipped} 个")
        if registered > 0:
            print(f"💡 下一步: pt gate <node_id>  — 运行投板门禁检查")
