#!/bin/bash
# 快捷方式：在任意目录使用 pt 命令
# 安装: 将此脚本放到 PATH 中，或 alias pt='bash /path/to/pt.sh'
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH="$DIR" python3 "$DIR/pt" "$@"
