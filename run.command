#!/bin/zsh
# Double-click this file in Finder to launch cyberdeck in Terminal.
cd "$(dirname "$0")" || exit 1

if command -v uv >/dev/null 2>&1; then
  exec uv run cyberdeck "$@"
fi

if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m cyberdeck "$@"
fi

echo "uv 未安装。请先在终端运行：brew install uv"
read -k 1 "?按任意键关闭…"
exit 1
