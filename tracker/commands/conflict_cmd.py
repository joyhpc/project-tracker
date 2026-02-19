"""冲突命令: conflict"""
import sys
from ..conflict import detect_conflicts, format_conflicts


def cmd_conflict(args):
    result = detect_conflicts()
    print(f"\n{format_conflicts(result)}")
