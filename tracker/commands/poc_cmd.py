"""poc 命令: PoC 验证追踪 — 管理验证项及其 Go/No-Go 状态"""
import sys
import datetime
from .. import core


def cmd_poc(args):
    """poc 命令入口"""
    if args.add:
        _add(args)
    elif args.update:
        _update(args)
    elif args.summary:
        _summary(args)
    else:
        _list_pocs(args)


def _add(args):
    """添加验证项"""
    try:
        p = core.require_active()

        poc = {
            "id": _next_id(p),
            "title": args.add,
            "metric": args.metric or "",
            "status": "pending",
            "date": datetime.date.today().isoformat(),
        }

        if "pocs" not in p:
            p["pocs"] = []
        p["pocs"].append(poc)
        core._save(p)

        print(f"✅ P{poc['id']}: {poc['title']}")
        if poc["metric"]:
            print(f"   红线: {poc['metric']}")

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _update(args):
    """更新验证项"""
    try:
        p = core.require_active()
        pocs = p.get("pocs", [])

        target = None
        for poc in pocs:
            if str(poc["id"]) == str(args.update):
                target = poc
                break

        if not target:
            print(f"❌ 验证项 P{args.update} 不存在")
            sys.exit(1)

        if args.status:
            target["status"] = args.status
        if args.result:
            target["result"] = args.result
            target["result_date"] = datetime.date.today().isoformat()

        core._save(p)

        icon = {"go": "🟢", "no-go": "🔴", "pending": "⏳", "caution": "🟡"}.get(target["status"], "⚪")
        print(f"{icon} P{target['id']}: {target['title']} → {target['status'].upper()}")
        if target.get("result"):
            print(f"   结果: {target['result']}")

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _summary(args):
    """验证项汇总 — 一张表看全部状态"""
    try:
        p = core.require_active()
        pocs = p.get("pocs", [])

        if not pocs:
            print("没有验证项。使用: pt poc --add <title>")
            return

        go = sum(1 for x in pocs if x["status"] == "go")
        nogo = sum(1 for x in pocs if x["status"] == "no-go")
        pending = sum(1 for x in pocs if x["status"] == "pending")
        caution = sum(1 for x in pocs if x["status"] == "caution")

        print(f"\n🧪 PoC 验证汇总 — {p['name']}")
        print(f"   🟢 GO: {go}  🟡 CAUTION: {caution}  🔴 NO-GO: {nogo}  ⏳ 待验证: {pending}\n")

        # 总判定
        if nogo > 0:
            print(f"   ⛔ 综合判定: NO-GO（{nogo} 项未通过）")
        elif pending > 0:
            print(f"   ⏳ 综合判定: 待完成（{pending} 项未验证）")
        elif caution > 0:
            print(f"   ⚠️ 综合判定: CONDITIONAL GO（{caution} 项需关注）")
        else:
            print(f"   ✅ 综合判定: ALL GO")

        print()
        _list_pocs(args)

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _list_pocs(args):
    """列出验证项"""
    try:
        p = core.require_active()
        pocs = p.get("pocs", [])

        if not pocs:
            print("没有验证项。使用: pt poc --add <title>")
            return

        if not hasattr(args, 'summary') or not args.summary:
            print(f"\n🧪 {p['name']} — PoC 验证项 ({len(pocs)})\n")

        for poc in pocs:
            icon = {"go": "🟢", "no-go": "🔴", "pending": "⏳", "caution": "🟡"}.get(poc["status"], "⚪")
            print(f"  {icon} P{poc['id']}: {poc['title']}")
            if poc.get("metric"):
                print(f"     红线: {poc['metric']}")
            if poc.get("result"):
                print(f"     结果: {poc['result']} ({poc.get('result_date', '')})")

        print()

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _next_id(project):
    pocs = project.get("pocs", [])
    if not pocs:
        return 1
    return max(x["id"] for x in pocs) + 1
