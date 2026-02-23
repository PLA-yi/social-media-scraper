#!/bin/bash
# 抖音爬虫环境安装脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== 安装 Python 依赖 ==="
pip install -r requirements.txt

echo ""
echo "=== 安装 Playwright 浏览器 ==="
playwright install chromium

echo ""
echo "=== 安装完成 ==="
echo "运行方式：bash run.sh"
