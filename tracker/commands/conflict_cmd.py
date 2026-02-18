"""冲突检测命令: conflict"""
import sys
from ..conflict import detect_conflicts, format_conflicts
from .. import core


def cmd_conflict(args):
    projects = core.list_projects()
    if not projects:
        print("没有项目")
        return
    if len(projects) < 2:
        print("只有 1 个项目，无需冲突检测。至少需要 2 个项目。")
        return

    print(f"\n📋 多项目资源冲突检测\n")
    result = detect_conflicts()
    print(format_conflicts(result))
