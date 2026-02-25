"""scan 命令 — 中途接入项目的 CLI 入口

薄壳层：解析参数 → 调用 onboard 模块 → 格式化输出
"""
import os
import sys
from .. import core
from .. import onboard


def cmd_scan(args):
    # 确定仓库路径
    repo = args.repo
    if not repo:
        try:
            p = core.require_active()
            repo = p.get("repo", "")
        except RuntimeError:
            pass

    if not repo:
        print("❌ 请指定仓库路径: pt scan --repo /path/to/repo")
        sys.exit(1)

    # 扫描
    try:
        result = onboard.scan_repo(repo)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if not result["files"]:
        print(f"📂 {repo} 中没有找到 markdown 文件")
        return

    # 输出扫描结果
    _print_scan_result(result)

    # --auto-register
    if getattr(args, "auto_register", False) and result["reviews"]:
        _do_auto_register(result)

    # --onboard
    if getattr(args, "onboard", False):
        _do_onboard(result)

    # 提示下一步
    if not getattr(args, "auto_register", False) and result["reviews"]:
        print("💡 下一步:")
        print("  pt scan --auto-register  — 自动注册所有 review 文件")
        print("  pt scan --onboard        — 生成项目导入 prompt（喂给 LLM 生成项目配置）")


def _print_scan_result(result: dict):
    """格式化输出扫描结果"""
    repo = result["repo"]
    reviews = result["reviews"]
    decisions = result["decisions"]
    pocs = result["pocs"]
    docs = result["docs"]

    print(f"\n📂 扫描: {repo}")
    print(f"   文件总数: {len(result['files'])}")
    print()

    if reviews:
        print(f"📋 发现 {len(reviews)} 个可能的 review 文件（含 GO/NO-GO/CAUTION 判定）:\n")
        for r in reviews:
            rel = os.path.relpath(r["path"], repo)
            verdicts = r["verdicts"]
            v_str = " ".join(f'{v["verdict"]}' for v in verdicts)
            has_nogo = any(v["verdict"] in ("NO-GO", "HIGH RISK") for v in verdicts)
            has_caution = any(v["verdict"] in ("CAUTION", "CONDITIONAL GO") for v in verdicts)
            icon = "🔴" if has_nogo else "🟡" if has_caution else "🟢"
            print(f"  {icon} {rel}")
            if r["title"]:
                print(f"     标题: {r['title']}")
            print(f"     判定: {v_str}")
            print()

    if decisions:
        print(f"📌 发现 {len(decisions)} 个含决策内容的文件:\n")
        for d in decisions:
            rel = os.path.relpath(d["path"], repo)
            print(f"  📄 {rel} — {d['title'] or '(无标题)'}")
        print()

    if pocs:
        print(f"🧪 发现 {len(pocs)} 个含 PoC/验证内容的文件:\n")
        for p_item in pocs:
            rel = os.path.relpath(p_item["path"], repo)
            print(f"  🔬 {rel} — {p_item['title'] or '(无标题)'}")
        print()

    other = [d for d in docs if not d["has_decisions"] and not d["has_poc"]]
    if other:
        print(f"📄 其他文档 ({len(other)}):\n")
        for d in other[:10]:
            rel = os.path.relpath(d["path"], repo)
            print(f"  📄 {rel} — {d['title'] or '(无标题)'} ({d['lines']}行)")
        if len(other) > 10:
            print(f"  ... 还有 {len(other) - 10} 个")
        print()


def _do_auto_register(result: dict):
    """自动注册 review 文件"""
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ 自动注册需要先激活项目: {e}")
        return

    registered = onboard.register_reviews(p, result)
    if registered:
        print(f"\n✅ 自动注册了 {registered} 个 review 文件")
    else:
        print("\n✅ 所有 review 文件已注册，无需操作")


def _do_onboard(result: dict):
    """生成并保存 onboard prompt"""
    repo = result["repo"]
    prompt_text = onboard.generate_onboard_prompt(repo, result)

    print("\n" + "=" * 60)
    print("  📋 项目导入 Prompt（复制给 LLM）")
    print("=" * 60)
    print()
    print(prompt_text)

    rel_path = onboard.save_onboard_prompt(repo, prompt_text)
    print(f"\n📄 已保存: {rel_path}")
