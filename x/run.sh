#!/bin/bash
set -e
cd "$(dirname "$0")"

PYTHON=/opt/homebrew/bin/python3.12

# 检查 twikit 是否已安装
if ! $PYTHON -c "import twikit" 2>/dev/null; then
    echo "[run] 未检测到 twikit，正在安装依赖..."
    $PYTHON -m pip install -r requirements.txt --break-system-packages
fi

$PYTHON main.py
