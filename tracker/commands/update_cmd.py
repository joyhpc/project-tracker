"""update 命令 — 自然语言项目变更

用户用一句话描述变动，pt 自动推断意图和目标节点。

示例：
  pt update "FMC改线完了"
  pt update "CPHY验证没过，等评估板到货"
  pt update "开始做CAMRX Pin分配"
  pt update "3.5G MIPI验证通过了"
"""
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

    icon = _INTENT_ICON.get(intent, "❓")
    label = _INTENT_LABEL.get(intent, "未知")

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
    nid = node["id"]
    status = node.get("status", "pending")

    try:
        if intent == "done":
            if status == "done":
                print(f"   ⚠️  [{nid}] 已经是完成状态")
                return
            note = result.get("raw", "")
            res = core.quick_done(project["id"], nid, note=note)
            print(f"   ✅ [{nid}] {node['name']} → 已完成")
            print(f"   进度: {res['progress']}")

        elif intent == "start":
            if status == "in_progress":
                print(f"   ⚠️  [{nid}] 已经在进行中")
                return
            if status == "done":
                print(f"   ⚠️  [{nid}] 已完成，无法重新开始")
                return
            core.start_task(project["id"], nid)
            print(f"   🔄 [{nid}] {node['name']} → 已开始")

        elif intent == "block":
            reason = result.get("reason") or result.get("raw", "未说明")
            core.block_task(project["id"], nid, reason)
            print(f"   🚫 [{nid}] {node['name']} → 已阻塞: {reason}")

        elif intent == "note":
            # 添加备注到项目日志
            from ..project_mutation import _append_log
            _append_log(project, {
                "action": "note",
                "task": nid,
                "detail": result.get("raw", ""),
                "time": core._now(),
            })
            core._save(project)
            print(f"   📝 [{nid}] 已添加备注")

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
