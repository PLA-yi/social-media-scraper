#!/bin/bash
# Reddit 爬虫环境安装脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== 安装 Python 依赖 ==="
pip3 install -r requirements.txt

echo ""
echo "=== 安装完成 ==="
echo "运行方式：bash run.sh"
