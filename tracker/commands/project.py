"""项目管理命令: init, list, switch, status, phases, note, log, validate"""
import json
import sys
from pathlib import Path

from .. import core
from . import _icon, _require


def cmd_init(args):
    try:
        repo = getattr(args, "repo", "") or ""
        p = core.init_project(args.id, args.name, args.flow, repo=repo)
        _, total = core._progress_counts(p)
        print(f"✅ 项目已创建: {p['id']} ({p['name']})")
        print(f"   流程: {p['flow']}, {total} 个节点")
        if repo:
            print(f"   仓库: {repo}")
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_list(args):
    projects = core.list_projects()
    if not projects:
        print("没有项目。使用 pt init <id> --name <name> 创建。")
        return
    for p in projects:
        marker = " ◀" if p.get("_active") else ""
        done, total = core._progress_counts(p)
        print(f"  {'●' if p.get('_active') else '○'} {p['id']} | {p['name']} | {done}/{total}{marker}")


def cmd_switch(args):
    try:
        core.switch_project(args.id)
        print(f"✅ 已切换到: {args.id}")
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_status(args):
    p = _require()
    info = core.get_status(p)
    classified = info["classified"]
    cpm = info["cpm"]
    close_summary = core.list_close_gates(p["id"])

    print(f"\n📋 {p['name']} ({p['id']})")
    print(f"📊 进度: {info['done_count']}/{info['total']}")
    print(f"⏱️  总工期: {cpm['total_days']:.0f} 天")

    # 阶段进度
    phase_progress = core.get_phase_progress(p)
    if phase_progress:
        print(f"\n📍 阶段进度:")
        bar_width = 12
        for ph in phase_progress:
            fill = round((ph["done"] / ph["total"]) * bar_width) if ph["total"] else 0
            bar = "█" * fill + "░" * (bar_width - fill)
            check = " ✅" if ph["complete"] else ""
            print(f"   {ph['name']}: [{bar}] {ph['progress']}{check}")

    # 关键路径
    if cpm["critical_path"]:
        print(f"\n🔴 关键路径 ({len(cpm['critical_path'])} 节点):")
        graph_nodes = {n["id"]: n for n in p["nodes"]}
        for nid in cpm["critical_path"][:8]:
            node = graph_nodes.get(nid, {})
            r = cpm["nodes"][nid]
            print(f"   [{nid}] {node.get('name','')} ({r['days']:.0f}天, ES={r['es']:.0f})")
        if len(cpm["critical_path"]) > 8:
            print(f"   ... 共 {len(cpm['critical_path'])} 个")

    # 阻塞
    if info["blockers"]:
        print(f"\n🚫 阻塞 ({len(info['blockers'])}):")
        for b in info["blockers"]:
            print(f"   {b['task_id']}: {b['reason']}")

    if close_summary.get("required_count", 0):
        print(
            f"\n🔒 Merge-to-Close: required={close_summary['required_count']} | valid={close_summary['valid_count']} | invalid={close_summary['invalid_count']}"
        )
        invalid_entries = [entry for entry in close_summary.get("entries", []) if not entry.get("valid")]
        for entry in invalid_entries[:5]:
            print(
                f"   ❌ [{entry['task_id']}] {entry['name']} | status={entry.get('status')} | issues={entry.get('issue_count')}"
            )
            if entry.get("close_mode") or entry.get("formal_object_id"):
                print(
                    f"      mode={entry.get('close_mode') or '-'} | formal={entry.get('formal_object_id') or '-'}"
                )
            if entry.get("docs_anchor"):
                print(f"      anchor={entry.get('docs_anchor')}")
            if entry.get("need_human_fields"):
                print("      human=" + ", ".join(entry["need_human_fields"]))
            if entry.get("top_issues"):
                print("      缺少/问题: " + " | ".join(entry["top_issues"]))
        if len(invalid_entries) > 5:
            print(f"   ... 还有 {len(invalid_entries) - 5} 个未通过")

    # 可执行任务
    ready = classified["ready"]
    if ready:
        print(f"\n✅ 可执行 ({len(ready)}):")
        for t in ready[:5]:
            slack = cpm["nodes"].get(t["id"], {}).get("slack", 0)
            crit = " 🔴" if cpm["nodes"].get(t["id"], {}).get("critical") else ""
            print(f"   [{t['id']}] {t['name']}  ← {t.get('owner','?')} (slack={slack:.0f}天){crit}")
        if len(ready) > 5:
            print(f"   ... 共 {len(ready)} 个")

    # 子任务模板提示：in_progress 且未展开的任务
    _print_template_hints(p)

    # 完整性告警
    warnings = info.get("warnings", [])
    if warnings:
        critical = [w for w in warnings if w["severity"] == "critical"]
        errors = [w for w in warnings if w["severity"] == "error"]
        warns = [w for w in warnings if w["severity"] == "warning"]
        infos = [w for w in warnings if w["severity"] == "info"]
        non_info = critical + errors + warns
        print(f"\n⚠️  完整性检查 ({len(non_info)} 个问题{f', {len(infos)} 个建议' if infos else ''}):")
        for w in critical:
            print(f"   🔴 {w['message']}")
        for w in errors:
            print(f"   ❌ {w['message']}")
        for w in warns[:3]:
            print(f"   ⚠️  {w['message']}")
        if len(warns) > 3:
            print(f"   ... 还有 {len(warns)-3} 个警告")
        for w in infos[:3]:
            print(f"   💡 {w['message']}")
        if len(infos) > 3:
            print(f"   ... 还有 {len(infos)-3} 个建议")

    print("💡 项目地图: pt map   |   HTML 地图: pt map --html")
    print()


def _print_template_hints(p):
    """检查 in_progress 任务是否有匹配的子任务模板未加载"""
    hints = []
    for n in p.get("nodes", []):
        if n.get("status") != "in_progress":
            continue
        if n.get("expanded_to"):  # 已展开，跳过
            continue
        matched = core.match_subtask_templates(n["id"])
        if matched:
            hints.append((n, matched))

    if hints:
        print(f"\n💡 可展开的子任务模板:")
        for node, templates in hints:
            for t in templates:
                print(f"   [{node['id']}] {node['name']} → {t['name']} ({t['task_count']}个子任务)")
                print(f"   加载: pt sub-load {node['id']} {t['id']}")


def cmd_phases(args):
    p = _require()
    phase_progress = core.get_phase_progress(p)
    if not phase_progress:
        print("没有阶段信息")
        return

    print(f"\n📋 {p['name']} - 阶段进度\n")
    for ph in phase_progress:
        pct = (ph["done"] / ph["total"] * 100) if ph["total"] > 0 else 0
        check = " ✅" if ph["complete"] else ""
        print(f"  {'●' if 0 < pct < 100 else '○'} {ph['id']} - {ph['name']} [{ph['progress']}] {pct:.0f}%{check}")
    print()


def cmd_note(args):
    try:
        p = _require()
        core.add_note(p["id"], args.text)
        print("📝 已记录")
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)


def cmd_log(args):
    p = _require()
    logs = p.get("log", [])
    n = args.n or 20
    icons = {"init": "🆕", "start": "🔄", "done": "✅", "block": "🚫", "unblock": "🔓",
             "note": "📝", "subtask_add": "➕", "subtask_done": "✅", "subtask_block": "🚫",
             "subtask_template_load": "📦"}
    for entry in logs[-n:]:
        icon = icons.get(entry.get("action", ""), "•")
        task = f" [{entry['task']}]" if entry.get("task") else ""
        detail = f" {entry.get('detail', '')}" if entry.get("detail") else ""
        print(f"  {entry['time']}  {icon}{task}{detail}")


def _validation_targets(args) -> list[Path]:
    if getattr(args, "all", False):
        core.PROJECTS_DIR.mkdir(exist_ok=True)
        return sorted(core.PROJECTS_DIR.glob("*.yaml"))

    project_id = getattr(args, "id", None)
    if project_id:
        return [core._project_file(project_id)]

    active = core._get_active()
    if not active:
        raise RuntimeError("没有活跃项目。先运行: pt init <id> --name <name> 或使用 pt validate <id>")
    return [core._project_file(active)]



def _print_validation_result(result: dict):
    counts = result.get("counts", {})
    total = sum(counts.values()) if counts else len(result.get("issues", []))
    header = f"{result.get('project_id', 'unknown')} | {result.get('path', '')}"
    if total == 0:
        print(f"✅ {header}")
        print("   无问题\n")
        return

    status_icon = "✅" if result.get("valid") else "❌"
    print(f"{status_icon} {header}")
    print(
        f"   critical={counts.get('critical', 0)}  error={counts.get('error', 0)}  warning={counts.get('warning', 0)}  info={counts.get('info', 0)}"
    )
    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    issues = sorted(result.get("issues", []), key=lambda item: (severity_order.get(item.get("severity"), 9), item.get("type", "")))
    for issue in issues:
        icon = {"critical": "🔴", "error": "❌", "warning": "⚠️", "info": "💡"}.get(issue.get("severity"), "•")
        print(f"   {icon} {issue.get('message', issue)}")
    print()



def cmd_validate(args):
    try:
        targets = _validation_targets(args)
        if not targets:
            print("没有项目文件可校验。")
            return

        results = [core.validate_project_file(target) for target in targets]
        if getattr(args, "json", False):
            payload = results[0] if len(results) == 1 else results
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for result in results:
                _print_validation_result(result)
            if len(results) > 1:
                total_errors = sum(result.get("counts", {}).get("error", 0) + result.get("counts", {}).get("critical", 0) for result in results)
                total_warnings = sum(result.get("counts", {}).get("warning", 0) for result in results)
                total_infos = sum(result.get("counts", {}).get("info", 0) for result in results)
                print(f"汇总: errors={total_errors} warnings={total_warnings} info={total_infos}")

        has_errors = any(result.get("counts", {}).get("critical", 0) or result.get("counts", {}).get("error", 0) for result in results)
        has_warnings = any(result.get("counts", {}).get("warning", 0) for result in results)
        if has_errors or (getattr(args, "strict", False) and has_warnings):
            sys.exit(1)

    except (RuntimeError, ValueError) as e:
        print(f"❌ {e}")
        sys.exit(1)
