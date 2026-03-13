"""hooks 命令 — 列出/测试已注册的 pt 钩子

Usage:
    pt hooks          — 列出所有钩子（内置 + 外部）
    pt hooks --test   — 测试所有钩子的 condition 是否满足
"""
import sys
from .. import core
from ..post_save import list_hooks, load_hooks, test_hook


def cmd_hooks(args):
    """列出或测试已注册的钩子。"""
    hooks = list_hooks()

    if getattr(args, "test", False):
        # 测试模式
        try:
            project = core.require_active()
        except RuntimeError as e:
            print(f"❌ {e}")
            sys.exit(1)

        print("🔍 钩子测试结果:\n")
        for h in hooks:
            if h["type"] == "builtin":
                print(f"  ✅ {h['name']} (内置) — 始终活跃")
                continue

            result = test_hook(h, project)
            icon = "✅" if result["would_run"] else "❌"
            print(f"  {icon} {result['name']}")
            print(f"     condition: {'满足' if result['condition_met'] else '未满足'}")
            if result["command"]:
                print(f"     command: {result['command']}")
            print()
        return

    # 列表模式
    print("📋 已注册钩子:\n")

    builtin = [h for h in hooks if h["type"] == "builtin"]
    external = [h for h in hooks if h["type"] == "external"]

    if builtin:
        print("── 内置钩子 ──")
        for h in builtin:
            print(f"  • {h['name']}")
            print(f"    事件: {', '.join(h['events'])}")
            print(f"    {h.get('description', '')}")
            print()

    if external:
        print("── 外部钩子 (~/.pt/hooks.d/) ──")
        for h in external:
            print(f"  • {h['name']}")
            print(f"    事件: {', '.join(h['events'])}")
            print(f"    条件: {h.get('condition', '无')}")
            print(f"    命令: {h.get('command', '—')}")
            print(f"    模式: {h.get('mode', 'best-effort')}")
            if h.get("source"):
                print(f"    来源: {h['source']}")
            print()
    elif not builtin:
        print("  (无已注册钩子)")

    print(f"合计: {len(builtin)} 内置 + {len(external)} 外部")
    print(f"\n💡 创建外部钩子: 在 ~/.pt/hooks.d/ 中添加 YAML 文件")
    print(f"   使用 --test 检查钩子条件是否满足")
