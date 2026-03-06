"""项目交互日志 — 高度抽象的项目推进简报"""
import sys
from datetime import datetime
from pathlib import Path
from .. import core


def cmd_log(args):
    try:
        p = core.require_active()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    flow = core._project_as_flow(p)
    repo = p.get("repo", "")

    # 收集已完成任务的时间线
    entries = []
    for n in flow.get("nodes", []):
        if n.get("status") != "done":
            continue
        entry = {
            "id": n["id"],
            "name": n["name"],
            "phase": n.get("phase", ""),
            "note": n.get("note", ""),
            "docs": [],
        }
        # 收集关联文档
        for doc in n.get("docs", []):
            entry["docs"].append(doc.get("desc") or doc.get("path") or doc.get("file", ""))
        # 从 note_file 提取一句话摘要
        if n.get("note_file") and repo:
            path = Path(repo) / n["note_file"]
            if path.exists():
                content = path.read_text(encoding="utf-8")
                # 取第一个引用块或第一个非标题非空行
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith(">") and len(line) > 10:
                        entry["summary"] = line.lstrip("> ").strip()[:100]
                        break
                    if line and not line.startswith("#") and not line.startswith("-") and len(line) > 15:
                        entry["summary"] = line[:100]
                        break
        entries.append(entry)

    # 当前状态
    done, total = core._progress_counts(p)
    task_status = {n["id"]: {"status": n.get("status", "pending")} for n in flow["nodes"]}

    from ..engine import compute_cpm, classify_tasks
    cpm = compute_cpm(flow, task_status)
    classified = classify_tasks(flow, task_status)
    ready = classified.get("ready", [])

    # 输出简报
    print(f"\n📋 {p['name']} — 项目推进简报")
    print(f"{'=' * 50}")
    print(f"进度: {done}/{total} | 总工期: {cpm['total_days']:.0f}天")
    print()

    # 已完成的里程碑
    if entries:
        print("✅ 已完成:")
        for e in entries:
            line = f"  [{e['id']}] {e['name']}"
            if e.get("note"):
                line += f" — {e['note']}"
            print(line)
            if e.get("summary"):
                print(f"    📄 {e['summary']}")
            for doc in e.get("docs", []):
                print(f"    📎 {doc}")
        print()

    # 关键决策
    decisions = []
    for e in entries:
        note = e.get("note", "")
        if any(w in note for w in ["决策", "拍板", "决定", "选择"]):
            decisions.append(f"  • {e['name']}: {note}")
    if decisions:
        print("🎯 关键决策:")
        for d in decisions:
            print(d)
        print()

    # 下一步
    if ready:
        print("⏭️  下一步:")
        for t in ready[:3]:
            slack = cpm["nodes"].get(t["id"], {}).get("slack", 0)
            crit = " 🔴" if slack == 0 else ""
            delivs = ", ".join(t.get("deliverables", []))
            print(f"  [{t['id']}] {t['name']}{crit}")
            if delivs:
                print(f"    交付物: {delivs}")
            # 显示已关联的参考文档
            for doc in t.get("docs", []):
                print(f"    📎 {doc.get('desc') or doc.get('path') or doc.get('file', '')}")
        print()

    # 保存
    if args.save:
        import io
        old_stdout = sys.stdout
        sys.stdout = buf = io.StringIO()

        print(f"# {p['name']} — 项目推进简报")
        print(f"\n进度: {done}/{total} | 总工期: {cpm['total_days']:.0f}天\n")
        if entries:
            print("## 已完成")
            for e in entries:
                line = f"- **{e['name']}**"
                if e.get("note"):
                    line += f": {e['note']}"
                print(line)
                for doc in e.get("docs", []):
                    print(f"  - 📎 {doc}")
        if decisions:
            print("\n## 关键决策")
            for d in decisions:
                print(d)
        if ready:
            print("\n## 下一步")
            for t in ready[:3]:
                delivs = ", ".join(t.get("deliverables", []))
                print(f"- **{t['name']}**" + (f": {delivs}" if delivs else ""))

        sys.stdout = old_stdout
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(buf.getvalue())
        print(f"💾 已保存: {args.save}")
