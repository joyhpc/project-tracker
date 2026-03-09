"""文档管理命令: docs"""
import sys
from .. import core
from . import _require


def cmd_docs(args):
    """文档管理入口"""
    actions = [bool(args.link), bool(args.attach), bool(args.sync or args.push), bool(args.load)]
    if sum(actions) > 1:
        print("❌ docs 同时只能执行一种动作：--link / --attach / --sync(--push) / --load")
        sys.exit(1)

    if args.link:
        _link(args)
    elif args.attach:
        _attach(args)
    elif args.sync or args.push:
        _sync(args)
    elif args.load:
        _load_from_repo(args)
    else:
        _list(args)


def _link(args):
    """关联仓库"""
    try:
        p = core.require_active()
        path = core.set_repo(p["id"], args.link)
        print(f"✅ 已关联仓库: {path}")
    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _attach(args):
    """关联文档到任务"""
    try:
        if not args.file:
            raise ValueError("使用 --attach 时必须同时提供 --file")
        p = core.require_active()
        desc = args.desc or ""
        core.attach_doc(p["id"], args.attach, args.file, desc)
        print(f"📎 已关联: {args.file} → [{args.attach}]")
    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _list(args):
    """列出文档"""
    p = _require()
    task_id = args.task if hasattr(args, "task") and args.task else None
    docs = core.list_task_docs(p, task_id)

    repo = core.get_repo_path(p)
    print(f"\n📋 {p['name']} — 文档管理")
    if repo:
        print(f"📁 仓库: {repo}")
    else:
        print(f"⚠️ 未关联仓库。使用: pt docs --link <path>")

    if not docs:
        # 显示有 deliverables 但没关联文档的任务
        missing = _get_missing_docs(p)
        if missing:
            print(f"\n📝 有交付物但未关联文档的任务 ({len(missing)}):")
            for n in missing[:10]:
                delivs = ", ".join(n["deliverables"])
                print(f"  [{n['id']}] {n['name']} — 交付物: {delivs}")
            if len(missing) > 10:
                print(f"  ... 共 {len(missing)} 个")
        else:
            print("\n没有关联的文档。")
        print()
        return

    print(f"\n📎 已关联文档 ({len(docs)}):")
    current_task = None
    for d in docs:
        if d["task_id"] != current_task:
            current_task = d["task_id"]
            print(f"\n  [{d['task_id']}] {d['task_name']}")
        icon = "✅" if d["exists"] else "❌"
        desc = f" — {d['desc']}" if d["desc"] else ""
        print(f"    {icon} {d['path']}{desc}")

    # 始终显示未关联统计
    missing = _get_missing_docs(p)
    if missing:
        print(f"\n⚠️ 还有 {len(missing)} 个任务有交付物但未关联文档:")
        for n in missing[:5]:
            delivs = ", ".join(n["deliverables"])
            print(f"  [{n['id']}] {n['name']} — {delivs}")
        if len(missing) > 5:
            print(f"  ... 共 {len(missing)} 个")
    print()


def _get_missing_docs(project):
    """获取有交付物但没关联文档的任务"""
    missing = []
    for n in project.get("nodes", []):
        if n.get("deliverables") and not n.get("docs"):
            missing.append(n)
    return missing


def _sync(args):
    """同步项目到仓库"""
    try:
        p = core.require_active()
        push = getattr(args, 'push', False)
        result = core.sync_project_to_repo(p["id"], push=push)
        print(f"✅ 已同步到: {result['repo']}")
        print(f"   项目文件: {result['synced']}")
        print(f"   README 状态已更新")
        if push:
            if result.get("pushed"):
                print(f"   🚀 已 git commit + push")
            elif result.get("push_error"):
                print(f"   ⚠️ git push 失败: {result['push_error']}")
    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)


def _load_from_repo(args):
    """从仓库加载项目"""
    try:
        p = core.load_from_repo(args.load)
        print(f"✅ 已从仓库加载: {p['id']} ({p['name']})")
        print(f"   节点: {len(p.get('nodes', []))}")
    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        sys.exit(1)
