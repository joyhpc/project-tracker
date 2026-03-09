"""CLI 入口 — 只做参数解析和路由"""
import argparse
from .commands.project import cmd_init, cmd_list, cmd_switch, cmd_status, cmd_phases, cmd_note, cmd_log, cmd_validate
from .commands.tasks import cmd_tasks, cmd_next, cmd_start, cmd_done, cmd_block, cmd_unblock, cmd_sub_add, cmd_sub_done, cmd_sub_block, cmd_sub_list, cmd_sub_load
from .commands.analysis import cmd_plan, cmd_digest, cmd_timeline, cmd_estimate, cmd_gantt, cmd_stats, cmd_deps, cmd_burndown, cmd_export
from .commands.guide_cmd import cmd_guide
from .commands.risk_cmd import cmd_risk
from .commands.conflict_cmd import cmd_conflict
from .commands.prompt_cmd import cmd_prompt
from .commands.docs_cmd import cmd_docs
from .commands.log_cmd import cmd_log as cmd_brief
from .commands.review_cmd import cmd_review
from .commands.decision_cmd import cmd_decision
from .commands.poc_cmd import cmd_poc
from .commands.propose_cmd import cmd_propose
from .commands.scan_cmd import cmd_scan
from .commands.visual_cmd import cmd_map, cmd_visual
from .commands.node_cmd import cmd_add, cmd_rm, cmd_skip, cmd_undo, cmd_rewire, cmd_replace, cmd_promote
from .commands.web_cmd import cmd_web
from .commands.notify_cmd import cmd_notify
from .commands.who_cmd import cmd_who


def main():
    parser = argparse.ArgumentParser(prog="pt", description="项目推进助手")
    sub = parser.add_subparsers(dest="command")

    # ── 项目管理 ──
    p_init = sub.add_parser("init", help="创建项目")
    p_init.add_argument("id", help="项目ID")
    p_init.add_argument("--name", "-n", required=True, help="项目名称")
    p_init.add_argument("--flow", "-f", default="duxin", help="流程定义")
    p_init.add_argument("--repo", help="关联本地仓库路径")

    sub.add_parser("list", aliases=["ls"], help="列出所有项目")

    p_sw = sub.add_parser("switch", aliases=["sw"], help="切换活跃项目")
    p_sw.add_argument("id", help="项目ID")

    sub.add_parser("status", aliases=["s"], help="查看项目状态")
    sub.add_parser("phases", aliases=["ph"], help="查看阶段进度")

    p_note = sub.add_parser("note", help="添加备注")
    p_note.add_argument("text", help="备注内容")

    p_log = sub.add_parser("log", help="查看项目日志")
    p_log.add_argument("-n", type=int, default=20, help="显示条数")

    p_validate = sub.add_parser("validate", aliases=["check"], help="显式校验项目 YAML / DAG 完整性")
    p_validate.add_argument("id", nargs="?", help="项目ID (默认当前活跃项目)")
    p_validate.add_argument("--all", "-a", action="store_true", help="校验所有项目")
    p_validate.add_argument("--strict", action="store_true", help="warning 也视为失败")
    p_validate.add_argument("--json", action="store_true", help="JSON 输出")

    # ── 任务操作 ──
    p_tasks = sub.add_parser("tasks", aliases=["t"], help="查看任务列表")
    p_tasks.add_argument("--phase", "-p", help="按阶段过滤")
    p_tasks.add_argument("--all", "-a", action="store_true", help="包含子任务")

    sub.add_parser("next", aliases=["n"], help="查看下一步行动")

    p_start = sub.add_parser("start", help="开始任务")
    p_start.add_argument("task_id", nargs="+", help="任务ID (支持多个)")

    p_done = sub.add_parser("done", aliases=["d"], help="完成任务")
    p_done.add_argument("task_id", nargs="+", help="任务ID (支持多个)")
    p_done.add_argument("--note", help="备注（一行）")
    p_done.add_argument("--note-file", help="备注文件（相对于仓库根目录）")
    p_done.add_argument("--force", action="store_true", help="跳过依赖检查")
    p_done.add_argument("--quick", "-q", action="store_true", help="跳过 start，直接完成")

    p_block = sub.add_parser("block", help="标记任务阻塞")
    p_block.add_argument("task_id")
    p_block.add_argument("reason", help="阻塞原因")

    p_unblock = sub.add_parser("unblock", help="解除任务阻塞")
    p_unblock.add_argument("task_id")

    # ── 子任务 ──
    p_sub = sub.add_parser("sub", help="添加子任务")
    p_sub.add_argument("parent")
    p_sub.add_argument("sub_id")
    p_sub.add_argument("--name", "-n", required=True)
    p_sub.add_argument("--owner", "-o")
    p_sub.add_argument("--depends")

    p_sd = sub.add_parser("sub-done", aliases=["sd"], help="完成子任务")
    p_sd.add_argument("full_id")
    p_sd.add_argument("--note")

    p_sb = sub.add_parser("sub-block", aliases=["sb"], help="阻塞子任务")
    p_sb.add_argument("full_id")
    p_sb.add_argument("--reason", "-r", required=True)

    p_sl = sub.add_parser("sub-list", aliases=["sl"], help="查看子任务")
    p_sl.add_argument("parent")

    p_sload = sub.add_parser("sub-load", help="从模板加载子任务")
    p_sload.add_argument("parent", nargs="?", help="父任务ID")
    p_sload.add_argument("template", nargs="?", help="模板ID")
    p_sload.add_argument("--list", "-l", action="store_true", help="列出可用模板")

    # ── 分析 ──
    sub.add_parser("plan", help="项目作战地图")

    p_map = sub.add_parser("map", help="项目地图（终端优先，可选 HTML/PNG）")
    p_map.add_argument("--html", action="store_true", help="同时生成 HTML 地图")
    p_map.add_argument("--output", "-o", default="/tmp", help="HTML/PNG 输出目录 (默认 /tmp)")
    p_map.add_argument("--no-png", action="store_true", help="只生成 HTML，不截图")

    p_dig = sub.add_parser("digest", help="项目状态摘要")
    p_dig.add_argument("--json", action="store_true")
    p_dig.add_argument("--quiet", "-q", action="store_true")

    p_tl = sub.add_parser("timeline", aliases=["tl"], help="项目时间线")
    p_tl.add_argument("--phase")
    p_tl.add_argument("--start", help="开始日期 YYYY-MM-DD")

    p_est = sub.add_parser("estimate", aliases=["est"], help="设置工时估算")
    p_est.add_argument("task_id", nargs="?")
    p_est.add_argument("days", nargs="?", type=int)
    p_est.add_argument("--show", action="store_true")
    p_est.add_argument("--all", action="store_true")

    # ── datax 导出 ──
    p_gantt = sub.add_parser("gantt", help="输出 Mermaid Gantt 图")
    p_gantt.add_argument("--project", help="项目ID (默认当前活跃项目)")

    p_stats = sub.add_parser("stats", help="输出阶段耗时统计表")
    p_stats.add_argument("--project", help="项目ID (默认当前活跃项目)")
    p_stats.add_argument("--json", action="store_true", help="JSON 输出")

    p_deps = sub.add_parser("deps", help="输出 Mermaid 依赖图")
    p_deps.add_argument("--project", help="项目ID (默认当前活跃项目)")

    p_burndown = sub.add_parser("burndown", help="Burndown 图表与速度分析")
    p_burndown.add_argument("--project", help="项目ID")
    p_burndown.add_argument("--mermaid", action="store_true", help="输出 Mermaid 格式")
    p_burndown.add_argument("--json", action="store_true", help="JSON 输出")

    p_export = sub.add_parser("export", help="导出项目数据为 CSV")
    p_export.add_argument("format", choices=["nodes", "stats", "burndown"], help="导出格式")
    p_export.add_argument("--project", help="项目ID")

    # ── 引导 ──
    p_guide = sub.add_parser("guide", help="启发式项目引导")
    p_guide.add_argument("--product", "-p")
    p_guide.add_argument("--phase")
    p_guide.add_argument("--overview", action="store_true")
    p_guide.add_argument("--flow", "-f", default="duxin")
    p_guide.add_argument("--save", "-s")

    # ── 人员视图 ──
    p_who = sub.add_parser("who", help="按人员查看任务分配")
    p_who.add_argument("--owner", help="筛选特定人员")
    p_who.add_argument("--status", choices=["pending", "in_progress", "blocked", "done"], help="筛选状态")
    p_who.add_argument("--all", "-a", action="store_true", help="显示已完成的任务")

    # ── 风险 ──
    p_risk = sub.add_parser("risk", help="风险评估")
    p_risk.add_argument("--phase", help="评估单个阶段")

    # ── 冲突 ──
    sub.add_parser("conflict", aliases=["cf"], help="多项目资源冲突检测")

    # ── Prompt ──
    p_prompt = sub.add_parser("prompt", help="Prompt 导出（带项目上下文）")
    p_prompt.add_argument("question", nargs="?", help="你的问题")
    p_prompt.add_argument("--list", "-l", action="store_true", help="列出支持的问题类型")
    p_prompt.add_argument("--auto", action="store_true", help="自动生成最有价值的问题")
    p_prompt.add_argument("--system", action="store_true", help="显示 system prompt")
    p_prompt.add_argument("--full", action="store_true", help="完整输出（system+prompt，方便复制）")
    p_prompt.add_argument("--deep", action="store_true", help="深度模式：生成 meta-prompt，让 LLM 做矛盾识别+盲区发现")
    p_prompt.add_argument("--deep-all", action="store_true", help="批量生成所有关键问题的 deep meta-prompt")
    p_prompt.add_argument("--save", "-s", help="保存到文件")

    # ── 简报 ──
    p_brief = sub.add_parser("brief", aliases=["br"], help="项目推进简报")
    p_brief.add_argument("--save", "-s", help="保存到文件")

    # ── Review ──
    p_review = sub.add_parser("review", aliases=["rv"], help="LLM 回复管理与交叉验证")
    p_review.add_argument("--add", "-a", help="收录回复文件 (相对于仓库根)")
    p_review.add_argument("--task", "-t", help="关联任务ID")
    p_review.add_argument("--source", default="super-llm", help="来源标记")
    p_review.add_argument("--unreviewed", action="store_true", help="标记为未审核 (自动生成/测试用)")
    p_review.add_argument("--approve", help="批准审核指定回复文件")
    p_review.add_argument("--analyze", action="store_true", help="交叉验证分析")
    p_review.add_argument("--report", nargs="?", const="auto", help="生成可行性分析报告 (默认auto保存)")
    p_review.add_argument("--list", "-l", action="store_true", help="列出已收录回复")

    # ── Decision ──
    p_dec = sub.add_parser("decision", aliases=["dec"], help="决策登记簿")
    p_dec.add_argument("--add", "-a", help="添加决策")
    p_dec.add_argument("--update", "-u", help="更新决策 (ID)")
    p_dec.add_argument("--source", help="决策来源")
    p_dec.add_argument("--impact", help="影响范围")
    p_dec.add_argument("--status", help="状态 (active/superseded/reverted/pending)")
    p_dec.add_argument("--note", help="备注")

    # ── PoC ──
    p_poc = sub.add_parser("poc", help="PoC 验证追踪")
    p_poc.add_argument("--add", "-a", help="添加验证项")
    p_poc.add_argument("--update", "-u", help="更新验证项 (ID)")
    p_poc.add_argument("--metric", "-m", help="Go/No-Go 红线指标")
    p_poc.add_argument("--result", help="验证结果")
    p_poc.add_argument("--status", help="状态 (pending/go/no-go/caution)")
    p_poc.add_argument("--summary", action="store_true", help="验证汇总")

    # ── 文档管理 ──
    p_docs = sub.add_parser("docs", help="文档管理")
    p_docs.add_argument("task", nargs="?", help="查看指定任务的文档")
    p_docs.add_argument("--link", help="关联本地仓库路径")
    p_docs.add_argument("--attach", help="关联文档到任务 (任务ID)")
    p_docs.add_argument("--file", help="文档文件路径 (相对于仓库根)")
    p_docs.add_argument("--desc", help="文档描述")
    p_docs.add_argument("--sync", action="store_true", help="同步项目到仓库")
    p_docs.add_argument("--push", action="store_true", help="同步后自动 git commit + push")
    p_docs.add_argument("--load", help="从仓库加载项目 (仓库路径)")

    # ── 方案推荐 ──
    p_propose = sub.add_parser("propose", aliases=["pp"], help="基于 review 回复生成方案推荐 prompt")
    p_propose.add_argument("--full", action="store_true", help="完整输出（方便复制）")
    p_propose.add_argument("--save", "-s", help="保存到文件")

    # ── 扫描导入 ──
    p_scan = sub.add_parser("scan", help="扫描仓库文档，自动识别 review/决策/PoC（中途接入项目用）")
    p_scan.add_argument("--repo", "-r", help="仓库路径（默认用当前项目的 repo）")
    p_scan.add_argument("--auto-register", action="store_true", help="自动注册发现的 review 文件")
    p_scan.add_argument("--onboard", action="store_true", help="生成项目导入 prompt（喂给 LLM 生成项目 YAML）")
    p_scan.add_argument("--arch", action="store_true", help="生成项目架构理解 prompt（中途介入第一步）")

    # ── 可视化 ──
    p_vis = sub.add_parser("visual", aliases=["vis", "v"], help="生成项目进度可视化图")
    p_vis.add_argument("--output", "-o", default="/tmp", help="输出目录 (默认 /tmp)")
    p_vis.add_argument("--no-png", action="store_true", help="只生成 HTML，不截图")

    # ── 节点 CRUD ──
    p_add = sub.add_parser("add", help="添加一等节点到 DAG")
    p_add.add_argument("id", help="节点ID")
    p_add.add_argument("--name", "-n", help="节点名称 (默认=ID)")
    p_add.add_argument("--phase", "-p", help="阶段 (默认 DETAIL)")
    p_add.add_argument("--days", "-d", type=int, help="预估工时(天)")
    p_add.add_argument("--owner", "-o", help="负责人")
    p_add.add_argument("--depends", help="上游依赖 (逗号分隔)")
    p_add.add_argument("--leads-to", help="下游节点 (逗号分隔, 自动接入+切断冗余边)")
    p_add.add_argument("--note", help="备注")
    p_add.add_argument("--dry-run", action="store_true", help="试运行 (不保存文件)")
    p_add.add_argument("--json", action="store_true", help="JSON 输出 (机器可读)")

    p_rm = sub.add_parser("rm", help="从 DAG 移除节点")
    p_rm.add_argument("id", help="节点ID")
    p_rm.add_argument("--stitch", action="store_true", help="自动缝合依赖链")
    p_rm.add_argument("--dry-run", action="store_true", help="试运行 (不保存文件)")
    p_rm.add_argument("--json", action="store_true", help="JSON 输出 (机器可读)")

    p_skip = sub.add_parser("skip", help="软删除: 标记节点为 skipped (0工时穿透)")
    p_skip.add_argument("id", help="节点ID")
    p_skip.add_argument("--reason", "-r", help="跳过原因")
    p_skip.add_argument("--dry-run", action="store_true", help="试运行 (不保存文件)")
    p_skip.add_argument("--json", action="store_true", help="JSON 输出 (机器可读)")

    p_undo = sub.add_parser("undo", help="恢复到上一个快照")
    p_undo.add_argument("--json", action="store_true", help="JSON 输出 (机器可读)")

    p_rewire = sub.add_parser("rewire", help="底层拓扑原语: 修改节点依赖")
    p_rewire.add_argument("target", help="目标节点ID")
    p_rewire.add_argument("--add", help="添加上游依赖 (逗号分隔)")
    p_rewire.add_argument("--rm", help="移除上游依赖 (逗号分隔)")
    p_rewire.add_argument("--dry-run", action="store_true", help="试运行 (不保存文件)")
    p_rewire.add_argument("--json", action="store_true", help="JSON 输出 (机器可读)")

    p_replace = sub.add_parser("replace", help="方案交接棒: 替换旧方案为新方案")
    p_replace.add_argument("old", help="被替换的旧节点ID")
    p_replace.add_argument("--entry", required=True, help="新方案入口节点ID (接管上游)")
    p_replace.add_argument("--exit", help="新方案出口节点ID (接管下游, 默认=entry)")
    p_replace.add_argument("--dry-run", action="store_true", help="试运行 (不保存文件)")
    p_replace.add_argument("--json", action="store_true", help="JSON 输出 (机器可读)")

    p_promote = sub.add_parser("promote", help="提拔子任务为一等节点")
    p_promote.add_argument("parent", help="父节点ID")
    p_promote.add_argument("sub", help="子任务ID (不含父节点前缀)")
    p_promote.add_argument("--days", "-d", type=int, help="预估工时(天)")
    p_promote.add_argument("--owner", "-o", help="负责人")
    p_promote.add_argument("--dry-run", action="store_true", help="试运行 (不保存文件)")
    p_promote.add_argument("--json", action="store_true", help="JSON 输出 (机器可读)")

    # ── Web 看板 ──
    p_web = sub.add_parser("web", help="启动只读 Web 看板")
    p_web.add_argument("--port", type=int, default=8080, help="端口 (默认 8080)")
    p_web.add_argument("--host", default="localhost", help="绑定地址 (默认 localhost)")

    # ── 通知管理 ──
    p_notify = sub.add_parser("notify", help="Webhook 通知管理")
    p_notify.add_argument("action", nargs="?", default="status", choices=["status", "test"], help="操作: status=查看配置, test=发送测试")

    # ── 路由 ──
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    CMD = {
        "init": cmd_init, "list": cmd_list, "ls": cmd_list,
        "switch": cmd_switch, "sw": cmd_switch,
        "status": cmd_status, "s": cmd_status,
        "phases": cmd_phases, "ph": cmd_phases,
        "note": cmd_note, "log": cmd_log,
        "validate": cmd_validate, "check": cmd_validate,
        "tasks": cmd_tasks, "t": cmd_tasks,
        "next": cmd_next, "n": cmd_next,
        "start": cmd_start, "done": cmd_done, "d": cmd_done,
        "block": cmd_block, "unblock": cmd_unblock,
        "sub": cmd_sub_add, "sub-done": cmd_sub_done, "sd": cmd_sub_done,
        "sub-block": cmd_sub_block, "sb": cmd_sub_block,
        "sub-list": cmd_sub_list, "sl": cmd_sub_list,
        "sub-load": cmd_sub_load,
        "plan": cmd_plan, "map": cmd_map, "digest": cmd_digest,
        "timeline": cmd_timeline, "tl": cmd_timeline,
        "estimate": cmd_estimate, "est": cmd_estimate,
        "gantt": cmd_gantt, "stats": cmd_stats, "deps": cmd_deps,
        "burndown": cmd_burndown, "export": cmd_export,
        "guide": cmd_guide, "risk": cmd_risk, "who": cmd_who,
        "conflict": cmd_conflict, "cf": cmd_conflict,
        "prompt": cmd_prompt,
        "docs": cmd_docs,
        "propose": cmd_propose, "pp": cmd_propose,
        "scan": cmd_scan,
        "visual": cmd_visual, "vis": cmd_visual, "v": cmd_visual,
        "brief": cmd_brief, "br": cmd_brief,
        "review": cmd_review, "rv": cmd_review,
        "decision": cmd_decision, "dec": cmd_decision,
        "poc": cmd_poc,
        "add": cmd_add, "rm": cmd_rm, "skip": cmd_skip, "undo": cmd_undo,
        "rewire": cmd_rewire, "replace": cmd_replace, "promote": cmd_promote,
        "web": cmd_web,
        "notify": cmd_notify,
    }

    fn = CMD.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()
