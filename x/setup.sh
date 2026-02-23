#!/bin/bash
set -e
echo "[setup] 安装依赖..."
/opt/homebrew/bin/python3.12 -m pip install -r "$(dirname "$0")/requirements.txt" --break-system-packages
echo "[setup] 完成"
