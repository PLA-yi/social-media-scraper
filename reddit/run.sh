#!/bin/bash
# Reddit 爬虫启动脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 &>/dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3.9+"
    exit 1
fi

if ! python3 -c "import requests" &>/dev/null; then
    echo "[安装] 未检测到依赖，正在安装..."
    python3 -m pip install -r requirements.txt
    echo ""
fi

echo "================================"
echo "  Reddit 数据爬虫"
echo "================================"
python3 main.py
