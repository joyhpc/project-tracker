"""update 命令 — 自然语言项目变更

用户用一句话描述变动，pt 自动推断意图和目标节点。

示例：
  pt update "FMC改线完了"
  pt update "CPHY验证没过，等评估板到货"
  pt update "开始做CAMRX Pin分配"
  pt update "3.5G MIPI验证通过了"
"""
import copy
import json
import sys
from .. import core
from ..fuzzy import parse_update, fuzzy_match


_INTENT_ICON = {
    "done": "✅", "start": "🔄", "block": "🚫",
    "note": "📝", "add": "➕", "unknown": "❓",
}

_INTENT_LABEL = {
    "done": "完成", "start": "开始", "block": "阻塞",
    "note": "备注", "add": "新增", "unknown": "未识别",
}


def _node_payload(node: dict | None) -> dict | None:
    if not node:
        return None
    return {
        "id": node.get("id"),
        "name": node.get("name", ""),
        "status": node.get("status", "pending"),
        "phase": node.get("phase", ""),
        "owner": node.get("owner", ""),
    }


def _suggested_command(intent: str, node: dict | None, result: dict) -> str:
    if not node:
        return ""
    node_id = node["id"]
    if intent == "done":
        return f"pt done {node_id}"
    if intent == "start":
        return f"pt start {node_id}"
    if intent == "block":
        reason = result.get("reason") or "待确认"
        return f'pt block {node_id} "{reason}"'
    if intent == "note":
        return f'pt update "{result.get("raw", "")}"'
    return ""


def _proposed_after_node(intent: str, node: dict | None, result: dict) -> dict | None:
    if not node:
        return None
    after = copy.deepcopy(node)
    if intent == "done":
        after["status"] = "done"
        after["done"] = "<execution time>"
        if result.get("raw"):
            after["note"] = result["raw"]
    elif intent == "start":
        after["status"] = "in_progress"
        after["started"] = "<execution time>"
    elif intent == "block":
        after["blocked_from_status"] = node.get("status", "pending")
        after["status"] = "blocked"
        after["blocked_reason"] = result.get("reason") or result.get("raw", "未说明")
    elif intent == "note":
        after.setdefault("_log_append", {
            "action": "note",
            "task": node["id"],
            "detail": result.get("raw", ""),
            "time": "<execution time>",
        })
    return after


def _parse_payload(project: dict, result: dict) -> dict:
    node = result.get("node")
    intent = result.get("intent", "unknown")
    target_file = str(core._project_file(project["id"]))
    return {
        "version": 1,
        "project_id": project["id"],
        "target_file": target_file,
        "intent": intent,
        "intent_label": _INTENT_LABEL.get(intent, "未知"),
        "confidence": result.get("confidence", "low"),
        "node": _node_payload(node),
        "candidates": [
            {"score": score, "node": _node_payload(candidate)}
            for candidate, score in result.get("candidates", [])
        ],
        "reason": result.get("reason", ""),
        "note": result.get("note", ""),
        "raw": result.get("raw", ""),
        "suggested_command": _suggested_command(intent, node, result),
        "would_execute": bool(intent != "unknown" and node and result.get("confidence") in {"high", "medium"}),
        "proposed_patch": {
            "before": copy.deepcopy(node) if node else None,
            "after": _proposed_after_node(intent, node, result),
        },
    }


def _print_dry_run(payload: dict) -> None:
    print(f"   目标文件: {payload['target_file']}")
    node = payload.get("node")
    if node:
        print(f"   匹配: [{node['id']}] {node['name']} ({node.get('status','pending')})")
    elif payload.get("candidates"):
        print(f"   找到 {len(payload['candidates'])} 个可能的节点:")
        for index, item in enumerate(payload["candidates"][:5], 1):
            candidate = item["node"]
            print(
                f"   {index}. [{candidate['id']}] {candidate['name']} "
                f"({candidate.get('status','pending')}, 匹配分={item['score']:.1f})"
            )
    else:
        print("   未找到匹配的节点")

    if payload.get("suggested_command"):
        print(f"   建议: {payload['suggested_command']}")
    patch = payload.get("proposed_patch", {})
    before = patch.get("before") or {}
    after = patch.get("after") or {}
    if before or after:
        print(f"   预览: status {before.get('status', '-')} -> {after.get('status', '-')}")
    print("   dry-run: 未写入项目")


def _apply_update(project: dict, intent: str, node: dict, result: dict) -> dict:
    """Apply a parsed update and return a structured execution result."""
    nid = node["id"]
    status = node.get("status", "pending")

    if intent == "done":
        if status == "done":
            return {"executed": False, "status": "noop", "message": f"[{nid}] 已经是完成状态"}
        note = result.get("raw", "")
        applied = core.quick_done(project["id"], nid, note=note)
        return {
            "executed": True,
            "status": "done",
            "message": f"[{nid}] {node['name']} -> 已完成",
            "result": applied,
        }

    if intent == "start":
        if status == "in_progress":
            return {"executed": False, "status": "noop", "message": f"[{nid}] 已经在进行中"}
        if status == "done":
            return {"executed": False, "status": "noop", "message": f"[{nid}] 已完成，无法重新开始"}
        applied = core.start_task(project["id"], nid)
        return {
            "executed": True,
            "status": "in_progress",
            "message": f"[{nid}] {node['name']} -> 已开始",
            "result": applied,
        }

    if intent == "block":
        reason = result.get("reason") or result.get("raw", "未说明")
        applied = core.block_task(project["id"], nid, reason)
        return {
            "executed": True,
            "status": "blocked",
            "message": f"[{nid}] {node['name']} -> 已阻塞: {reason}",
            "result": applied,
        }

    if intent == "note":
        from ..project_mutation import _append_log
        _append_log(project, {
            "action": "note",
            "task": nid,
            "detail": result.get("raw", ""),
            "time": core._now(),
        })
        core._save(project)
        return {
            "executed": True,
            "status": "noted",
            "message": f"[{nid}] 已添加备注",
        }

    return {"executed": False, "status": "unsupported", "message": f"不支持的意图: {intent}"}


def cmd_update(args):
    text = args.text
    if not text:
        print("用法: pt update \"FMC改线完了\"")
        return

    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    result = parse_update(p, text)
    intent = result["intent"]
    node = result["node"]
    candidates = result["candidates"]
    confidence = result["confidence"]
    payload = _parse_payload(p, result)

    icon = _INTENT_ICON.get(intent, "❓")
    label = _INTENT_LABEL.get(intent, "未知")

    if getattr(args, "dry_run", False):
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        print(f"\n{icon} 解析: 意图={label}  置信度={confidence}")
        _print_dry_run(payload)
        return

    if getattr(args, "json", False) and payload["would_execute"]:
        try:
            payload["execution"] = _apply_update(p, intent, node, result)
        except (RuntimeError, ValueError) as e:
            payload["execution"] = {"executed": False, "status": "error", "message": str(e)}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            sys.exit(1)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"\n{icon} 解析: 意图={label}  置信度={confidence}")

    # 无法识别意图
    if intent == "unknown":
        print(f"   无法从 \"{text}\" 中识别操作意图")
        print(f"   试试更明确的描述，如：")
        print(f'     "xxx完了"  "开始做xxx"  "xxx卡住了,原因"')
        if candidates:
            print(f"\n   可能相关的节点:")
            for n, s in candidates[:3]:
                print(f"     [{n['id']}] {n['name']} ({n.get('status','pending')})")
        return

    # 高置信度：直接执行
    if confidence == "high" and node:
        _execute(p, intent, node, result)
        return

    # 中等置信度：展示并确认
    if confidence == "medium" and node:
        print(f"   匹配: [{node['id']}] {node['name']} ({node.get('status','pending')})")
        _execute(p, intent, node, result)
        return

    # 低置信度或无匹配：列出候选
    if not candidates:
        print(f"   未找到匹配的节点")
        if intent == "add":
            print(f"   提示: 使用 pt add <id> --name \"名称\" 手动添加")
        return

    print(f"   找到 {len(candidates)} 个可能的节点:\n")
    for i, (n, s) in enumerate(candidates[:5], 1):
        status_icon = {"done": "✅", "in_progress": "🔄", "blocked": "🚫",
                       "pending": "⬜"}.get(n.get("status", "pending"), "⬜")
        print(f"   {i}. {status_icon} [{n['id']}] {n['name']}  (匹配分={s:.1f})")

    # 给出建议命令
    best = candidates[0][0]
    if intent == "done":
        print(f"\n   建议: pt done {best['id']}")
    elif intent == "start":
        print(f"\n   建议: pt start {best['id']}")
    elif intent == "block":
        reason = result["reason"] or "待确认"
        print(f"\n   建议: pt block {best['id']} \"{reason}\"")


def _execute(project, intent, node, result):
    """执行推断出的操作。"""
    try:
        applied = _apply_update(project, intent, node, result)
        message = applied.get("message", "")
        if applied.get("executed"):
            print(f"   ✅ {message}")
            progress = (applied.get("result") or {}).get("progress")
            if progress:
                print(f"   进度: {progress}")
        else:
            print(f"   ⚠️  {message}")

    except (RuntimeError, ValueError) as e:
        print(f"   ❌ 执行失败: {e}")


def cmd_find(args):
    """搜索项目节点。"""
    query = args.query
    if not query:
        print("用法: pt find \"MIPI\"")
        return

    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    show_done = getattr(args, "all", False)
    matches = fuzzy_match(p, query, top_k=10, exclude_done=not show_done)

    if not matches:
        print(f"未找到匹配 \"{query}\" 的节点")
        return

    print(f"\n🔍 搜索 \"{query}\" — {len(matches)} 个匹配:\n")

    STATUS_ICON = {"done": "✅", "in_progress": "🔄", "blocked": "🚫",
                   "pending": "⬜", "expanded": "📦", "skipped": "⏭️"}

    for n, score in matches:
        icon = STATUS_ICON.get(n.get("status", "pending"), "⬜")
        owner = f" ← {n['owner']}" if n.get("owner") else ""
        note = f" | {n['note'][:40]}..." if n.get("note") and len(n.get("note", "")) > 5 else ""
        phase = n.get("phase", "")
        print(f"  {icon} [{n['id']}] {n['name']}{owner}")
        if phase or note:
            print(f"     阶段={phase}{note}")
