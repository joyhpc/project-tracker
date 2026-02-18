"""CLI 入口 — 只做参数解析和路由"""
import argparse
from .commands.project import cmd_init, cmd_list, cmd_switch, cmd_status, cmd_phases, cmd_advance, cmd_note, cmd_log
from .commands.tasks import cmd_tasks, cmd_next, cmd_start, cmd_done, cmd_block, cmd_unblock, cmd_sub_add, cmd_sub_done, cmd_sub_block, cmd_sub_list
from .commands.analysis import cmd_plan, cmd_digest, cmd_timeline, cmd_estimate
from .commands.guide_cmd import cmd_guide
from .commands.risk_cmd import cmd_risk
from .commands.conflict_cmd import cmd_conflict
from .commands.prompt_cmd import cmd_prompt


def main():
    parser = argparse.ArgumentParser(prog="pt", description="项目推进助手")
    sub = parser.add_subparsers(dest="command")

    # ── 项目管理 ──
    p_init = sub.add_parser("init", help="创建项目")
    p_init.add_argument("id", help="项目ID")
    p_init.add_argument("--name", "-n", required=True, help="项目名称")
    p_init.add_argument("--phase", "-p", default="REQ", help="起始阶段")
    p_init.add_argument("--flow", "-f", default="duxin", help="流程定义")

    sub.add_parser("list", aliases=["ls"], help="列出所有项目")

    p_sw = sub.add_parser("switch", aliases=["sw"], help="切换活跃项目")
    p_sw.add_argument("id", help="项目ID")

    sub.add_parser("status", aliases=["s"], help="查看项目状态")
    sub.add_parser("phases", aliases=["ph"], help="查看流程阶段")

    p_adv = sub.add_parser("advance", help="推进到下一阶段")
    p_adv.add_argument("--force", action="store_true", help="强制推进")

    p_note = sub.add_parser("note", help="添加备注")
    p_note.add_argument("text", help="备注内容")

    p_log = sub.add_parser("log", help="查看项目日志")
    p_log.add_argument("-n", type=int, default=20, help="显示条数")

    # ── 任务操作 ──
    sub.add_parser("tasks", aliases=["t"], help="查看当前阶段任务")
    sub.add_parser("next", aliases=["n"], help="查看下一步行动")

    p_start = sub.add_parser("start", help="开始任务")
    p_start.add_argument("task_id")

    p_done = sub.add_parser("done", aliases=["d"], help="完成任务")
    p_done.add_argument("task_id")
    p_done.add_argument("--note", help="备注")
    p_done.add_argument("--force", action="store_true", help="跳过依赖检查")

    p_block = sub.add_parser("block", help="标记任务阻塞")
    p_block.add_argument("task_id")
    p_block.add_argument("--reason", "-r", required=True, help="阻塞原因")

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

    # ── 分析 ──
    sub.add_parser("plan", help="项目作战地图")

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

    # ── 引导 ──
    p_guide = sub.add_parser("guide", help="启发式项目引导")
    p_guide.add_argument("--product", "-p")
    p_guide.add_argument("--phase")
    p_guide.add_argument("--overview", action="store_true")
    p_guide.add_argument("--flow", "-f", default="duxin")
    p_guide.add_argument("--save", "-s")

    # ── 风险 ──
    p_risk = sub.add_parser("risk", help="风险评估")
    p_risk.add_argument("--phase", help="评估单个阶段")

    # ── 冲突 ──
    sub.add_parser("conflict", aliases=["cf"], help="多项目资源冲突检测")

    # ── Prompt ──
    p_prompt = sub.add_parser("prompt", help="Prompt 导出（带项目上下文）")
    p_prompt.add_argument("question", nargs="?", help="你的问题")
    p_prompt.add_argument("--list", "-l", action="store_true", help="列出支持的问题类型")
    p_prompt.add_argument("--system", action="store_true", help="显示 system prompt")
    p_prompt.add_argument("--save", "-s", help="保存到文件")

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
        "advance": cmd_advance, "note": cmd_note, "log": cmd_log,
        "tasks": cmd_tasks, "t": cmd_tasks,
        "next": cmd_next, "n": cmd_next,
        "start": cmd_start, "done": cmd_done, "d": cmd_done,
        "block": cmd_block, "unblock": cmd_unblock,
        "sub": cmd_sub_add, "sub-done": cmd_sub_done, "sd": cmd_sub_done,
        "sub-block": cmd_sub_block, "sb": cmd_sub_block,
        "sub-list": cmd_sub_list, "sl": cmd_sub_list,
        "plan": cmd_plan, "digest": cmd_digest,
        "timeline": cmd_timeline, "tl": cmd_timeline,
        "estimate": cmd_estimate, "est": cmd_estimate,
        "guide": cmd_guide, "risk": cmd_risk,
        "conflict": cmd_conflict, "cf": cmd_conflict,
        "prompt": cmd_prompt,
    }

    fn = CMD.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()
