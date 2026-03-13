"""domain-sync 命令 — 通用领域工具包同步桥

Usage:
    pt domain-sync          — 扫描所有已知工具包的 pt-sync.yaml 并同步
    pt domain-sync --dry-run — 试运行，不实际写入
    pt domain-sync --list    — 列出已发现的 manifest
"""
import sys
from .. import core
from ..domain_sync import discover_manifests, sync_all


def cmd_domain_sync(args):
    """执行领域工具包同步。"""
    try:
        project = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if getattr(args, "list", False):
        manifests = discover_manifests()
        if not manifests:
            print("📂 未发现任何 pt-sync.yaml manifest")
            print("💡 在工具包根目录创建 pt-sync.yaml 即可接入")
            return

        print(f"📋 已发现 {len(manifests)} 个同步 manifest:\n")
        for m in manifests:
            print(f"  • {m.get('name', 'unnamed')}")
            print(f"    路径: {m.get('_manifest_path', '?')}")
            print(f"    扫描: {m.get('scan_dir', '.')}")
            print(f"    模式: {m.get('file_pattern', '*.md')}")
            extract = m.get("extract", {})
            print(f"    提取: {extract.get('type', '?')}")
            print(f"    目标: {m.get('target', 'decisions')}")
            print()
        return

    dry_run = getattr(args, "dry_run", False)
    results = sync_all(project, dry_run)

    if results["manifests_found"] == 0:
        print("📂 未发现任何 pt-sync.yaml manifest")
        print("💡 在工具包根目录创建 pt-sync.yaml 即可接入")
        return

    print(f"\n🔄 domain-sync: 扫描了 {results['manifests_found']} 个 manifest\n")

    for detail in results["details"]:
        icon = "✅" if detail["synced_count"] > 0 else "—"
        print(f"  {icon} {detail['name']}: {detail['synced_count']} 条新同步")

        for item in detail["items"]:
            verdict = item["entry"].get("verdict", item["entry"].get("verdicts", [{}])[0].get("verdict", "?"))
            verdict_icon = {"GO": "🟢", "NO-GO": "🔴", "CAUTION": "🟡",
                            "KILL": "🔴", "MAYBE": "🟡"}.get(verdict, "⚪")
            print(f"     {verdict_icon} {item['title'][:60]} → {item['target']}")

    print(f"\n{'─' * 50}")
    if dry_run:
        print(f"🔍 试运行完成 — 发现 {results['total_synced']} 条可同步")
    else:
        if results["total_synced"] > 0:
            core._save(project)
        print(f"✅ 同步完成 — 新增 {results['total_synced']} 条")
