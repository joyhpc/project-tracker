"""decision 命令: 决策登记簿 — 追踪项目中的关键架构/技术/商业决策

决策从 review 分析中提取，或手动添加。
"""
import sys
import datetime
from .. import core


def cmd_decision(args):
    """decision 命令入口"""
    if args.add:
        _add(args)
    elif args.update:
        _update(args)
    else:
        _list_decisions(args)


def _add(args):
    """添加决策"""
    try:
        p = core.require_active()

        decision = {
            "id": _next_id(p),
            "title": args.add,
            "source": args.source or "",
            "impact": args.impact or "",
            "status": "active",
            "date": datetime.date.today().isoformat(),
        }

        if "decisions" not in p:
            p["decisions"] = []
        p["decisions"].append(decision)
        core._save(p)

        print(f"✅ D{decision['id']}: {decision['title']}")
        if decision["source"]:
            print(f"   来源: {decision['source']}")
        if decision["impact"]:
            print(f"   影响: {decision['impact']}")

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _update(args):
    """更新决策状态"""
    try:
        p = core.require_active()
        decisions = p.get("decisions", [])

        target = None
        for d in decisions:
            if str(d["id"]) == str(args.update):
                target = d
                break

        if not target:
            print(f"❌ 决策 D{args.update} 不存在")
            sys.exit(1)

        if args.status:
            target["status"] = args.status
        if args.note:
            target["note"] = args.note

        core._save(p)
        print(f"✅ D{target['id']}: {target['title']} → {target['status']}")

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _list_decisions(args):
    """列出所有决策"""
    try:
        p = core.require_active()
        decisions = p.get("decisions", [])

        if not decisions:
            print("没有决策记录。使用: pt decision --add <title>")
            return

        print(f"\n📋 {p['name']} — 决策登记簿 ({len(decisions)})\n")

        status_icon = {"active": "🟢", "superseded": "⚫", "reverted": "🔴", "pending": "🟡"}

        for d in decisions:
            icon = status_icon.get(d.get("status", "active"), "⚪")
            print(f"  {icon} D{d['id']}: {d['title']}")
            if d.get("source"):
                print(f"     来源: {d['source']}")
            if d.get("impact"):
                print(f"     影响: {d['impact']}")
            if d.get("note"):
                print(f"     备注: {d['note']}")
            print(f"     日期: {d.get('date', '?')}  状态: {d.get('status', 'active')}")

        print()

    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _next_id(project):
    """生成下一个决策 ID"""
    decisions = project.get("decisions", [])
    if not decisions:
        return 1
    return max(d["id"] for d in decisions) + 1
