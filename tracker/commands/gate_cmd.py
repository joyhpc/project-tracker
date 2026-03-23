"""gate 命令 — 投板/推进门禁检查

检查指定节点关联的所有 reviews，汇总 P0/P1/P2 状态，
如有 NO-GO 则阻断并输出修改清单路径。

整合 sch-review 的 P0/P1/P2 体系与 pt 的 GO/CAUTION/NO-GO。
"""
import os
import re
import sys
from pathlib import Path
from .. import core
from .close_cmd import _print_check


# ── sch-review severity ↔ pt verdict 映射 ──

SEVERITY_TO_VERDICT = {
    "P0": "NO-GO",
    "P1": "CAUTION",
    "P2": "GO",
    "P3": "GO",
    "P4": "GO",
}


def _scan_review_file(filepath: str) -> dict:
    """扫描审核报告，提取 P0/P1/P2 计数和阻断项。"""
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return {"error": f"无法读取: {filepath}"}

    findings = {"P0": [], "P1": [], "P2": []}
    # 匹配 P0/P1/P2 标记行
    for line in content.split("\n"):
        for sev in ("P0", "P1", "P2"):
            if re.search(rf'\b{sev}\b', line):
                desc = line.strip().lstrip("|#*-> ")
                if len(desc) > 10 and desc not in findings[sev]:
                    findings[sev].append(desc[:120])

    # 检测投板就绪关键词
    ready = None
    if re.search(r'投板就绪[：:]\s*否', content):
        ready = False
    elif re.search(r'投板就绪[：:]\s*是', content):
        ready = True
    elif re.search(r'结论[：:].*不通过', content):
        ready = False
    elif re.search(r'NOT READY|NO.?GO', content, re.IGNORECASE):
        ready = False

    return {
        "findings": findings,
        "ready": ready,
        "p0_count": len(findings["P0"]),
        "p1_count": len(findings["P1"]),
        "p2_count": len(findings["P2"]),
    }


def _find_related_reports(project: dict, node_id: str) -> list:
    """查找与节点相关的审核报告。

    来源：
    1. 项目 reviews[] 中的已注册报告
    2. 节点 docs[] 中关联的文件
    """
    repo = project.get("repo", "")
    reports = []

    # 已注册的 reviews
    for rv in project.get("reviews", []):
        fpath = rv.get("file", "")
        if fpath:
            full = os.path.join(repo, fpath) if repo and not os.path.isabs(fpath) else fpath
            reports.append({"path": full, "source": "review", "verdict": rv.get("verdicts", [])})

    # 节点 docs
    nodes_map = {n["id"]: n for n in project.get("nodes", [])}
    node = nodes_map.get(node_id)
    if node:
        for doc in node.get("docs", []):
            fpath = doc.get("file", "") or doc.get("path", "")
            if fpath:
                full = os.path.join(repo, fpath) if repo and not os.path.isabs(fpath) else fpath
                reports.append({"path": full, "source": "docs", "verdict": []})

    return reports


def cmd_gate(args):
    """执行投板门禁检查或正式闭环门禁检查。"""
    try:
        project = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    gate_target = getattr(args, "gate_target", None)
    task_id = getattr(args, "task_id", None)

    if gate_target == "closure":
        if not task_id:
            print("❌ 用法: pt gate closure <task_id>")
            sys.exit(1)
        try:
            result = core.check_close_gate(project["id"], task_id)
        except (RuntimeError, ValueError) as exc:
            print(f"❌ {exc}")
            sys.exit(1)
        if getattr(args, "json", False):
            import json
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("🚦 正式闭环门禁检查")
            _print_check(result)
        if not result.get("valid"):
            sys.exit(1)
        return

    node_id = task_id or gate_target
    if gate_target == "review" and not task_id:
        print("❌ 用法: pt gate review <task_id>")
        sys.exit(1)
    if not node_id:
        print("❌ 用法: pt gate <task_id> 或 pt gate closure <task_id>")
        sys.exit(1)
    nodes_map = {n["id"]: n for n in project.get("nodes", [])}
    if node_id not in nodes_map:
        print(f"❌ 节点 [{node_id}] 不存在")
        sys.exit(1)

    node = nodes_map[node_id]
    print(f"\n🚦 投板门禁检查: [{node_id}] {node.get('name', node_id)}")
    print("=" * 60)

    # 收集相关报告
    reports = _find_related_reports(project, node_id)

    # 如果没有找到报告，尝试用 --scan-dir 扫描
    scan_dir = getattr(args, "scan_dir", None)
    if scan_dir:
        scan_path = Path(scan_dir)
        if scan_path.is_dir():
            for f in sorted(scan_path.rglob("*.md")):
                reports.append({"path": str(f), "source": "scan", "verdict": []})

    if not reports:
        print("⚠️  未找到关联的审核报告")
        print("   提示: 使用 pt review-sync 同步 sch-review 报告")
        print("   或使用: pt gate <node_id> --scan-dir ~/sch-review/reports/")
        return

    # 逐一扫描报告
    total_p0 = 0
    total_p1 = 0
    total_p2 = 0
    all_p0_items = []
    gate_pass = True

    for rpt in reports:
        path = rpt["path"]
        if not os.path.isfile(path):
            continue
        result = _scan_review_file(path)
        if "error" in result:
            continue

        rel = os.path.relpath(path, project.get("repo", "."))
        p0, p1, p2 = result["p0_count"], result["p1_count"], result["p2_count"]
        total_p0 += p0
        total_p1 += p1
        total_p2 += p2

        if p0 > 0:
            gate_pass = False
            icon = "🔴"
        elif p1 > 0:
            icon = "🟡"
        else:
            icon = "🟢"

        if p0 + p1 + p2 > 0:
            print(f"\n  {icon} {rel}")
            print(f"     P0={p0}  P1={p1}  P2={p2}")
            if result["ready"] is not None:
                print(f"     投板就绪: {'是' if result['ready'] else '否'}")

        all_p0_items.extend(result["findings"]["P0"])
        if result.get("ready") is False:
            gate_pass = False

    # 汇总判定
    print("\n" + "─" * 60)
    if gate_pass:
        print("✅ 门禁通过 — 可推进")
        verdict = "GO"
    elif total_p0 > 0:
        print(f"❌ 门禁不通过 — {total_p0} 个 P0 阻断项未闭合")
        verdict = "NO-GO"
        print("\n📋 P0 阻断清单:")
        for i, item in enumerate(all_p0_items[:10], 1):
            print(f"   {i}. {item}")
        if len(all_p0_items) > 10:
            print(f"   ... 共 {len(all_p0_items)} 项")
    else:
        print(f"⚠️  门禁有条件通过 — {total_p1} 个 P1 问题待确认")
        verdict = "CAUTION"

    print(f"\n📊 汇总: P0={total_p0}  P1={total_p1}  P2={total_p2}  判定={verdict}")

    # gate 条件检查
    gate_cond = node.get("gate", "")
    if gate_cond:
        print(f"\n📌 节点准入条件: {gate_cond}")
