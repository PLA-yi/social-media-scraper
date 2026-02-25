#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  Social Media Scraper — 一键启动脚本
#  首次运行：自动安装所有依赖（约需 5-10 分钟）
#  后续运行：直接启动，秒开
# ══════════════════════════════════════════════════════════════════
cd "$(dirname "$0")"

# ── 颜色输出辅助 ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
step()  { echo ""; echo -e "${BOLD}${BLUE}▶ $1${NC}"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
err()   { echo -e "  ${RED}✗${NC} $1"; }
banner(){ echo -e "${BOLD}$1${NC}"; }

# ── 欢迎界面 ─────────────────────────────────────────────────────
clear
banner "╔══════════════════════════════════════════╗"
banner "║        Social Media Scraper              ║"
banner "╚══════════════════════════════════════════╝"
echo ""

VENV_DIR="$(pwd)/.venv"
SETUP_MARKER="$VENV_DIR/.setup_done"

# ══════════════════════════════════════════════════════════════════
#  如果已完成安装，直接跳到启动阶段
# ══════════════════════════════════════════════════════════════════
if [ -f "$SETUP_MARKER" ]; then
    echo -e "  ${GREEN}环境已就绪，正在启动...${NC}"
else
    # ══════════════════════════════════════════════════════════════
    #  首次安装流程
    # ══════════════════════════════════════════════════════════════
    banner "首次运行，开始自动安装依赖（约需 5-10 分钟）..."
    echo ""

    # ── Step 1: 查找 Python 3.10+ ────────────────────────────────
    step "Step 1/4 — 检查 Python 版本"

    PYTHON=""
    # 按优先级搜索：Homebrew 路径 > PATH 中的通用命令
    for candidate in \
        /opt/homebrew/bin/python3.13 \
        /opt/homebrew/bin/python3.12 \
        /opt/homebrew/bin/python3.11 \
        /opt/homebrew/bin/python3.10 \
        /usr/local/bin/python3.13 \
        /usr/local/bin/python3.12 \
        /usr/local/bin/python3.11 \
        /usr/local/bin/python3.10 \
        python3.13 python3.12 python3.11 python3.10; do
        if command -v "$candidate" &>/dev/null 2>&1; then
            _minor=$("$candidate" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
            _major=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
            if [ "$_major" -ge 3 ] 2>/dev/null && [ "$_minor" -ge 10 ] 2>/dev/null; then
                PYTHON=$(command -v "$candidate" 2>/dev/null || echo "$candidate")
                break
            fi
        fi
    done

    if [ -z "$PYTHON" ]; then
        warn "未找到 Python 3.10+，正在通过 Homebrew 自动安装..."

        # 安装 Homebrew（如果没有）
        if ! command -v brew &>/dev/null 2>&1; then
            echo "  正在安装 Homebrew（需输入 macOS 开机密码）..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # 将 Homebrew 加入当前 shell 的 PATH
            if [ -f /opt/homebrew/bin/brew ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [ -f /usr/local/bin/brew ]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
        fi

        if ! command -v brew &>/dev/null 2>&1; then
            err "Homebrew 安装失败，请手动前往 https://brew.sh 安装后重试"
            read -p "按回车键退出..." _
            exit 1
        fi

        echo "  正在通过 Homebrew 安装 Python 3.12..."
        brew install python@3.12
        PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
    fi

    if [ -z "$PYTHON" ] || ! "$PYTHON" --version &>/dev/null 2>&1; then
        err "Python 安装失败，请手动安装 Python 3.10 或以上版本后重试"
        err "下载地址：https://www.python.org/downloads/"
        read -p "按回车键退出..." _
        exit 1
    fi

    ok "Python 已就绪：$PYTHON ($("$PYTHON" --version))"

    # ── Step 2: 创建虚拟环境 ──────────────────────────────────────
    step "Step 2/4 — 创建独立虚拟环境（.venv）"
    "$PYTHON" -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        err "虚拟环境创建失败"
        read -p "按回车键退出..." _
        exit 1
    fi
    ok "虚拟环境已创建"

    VENV_PIP="$VENV_DIR/bin/pip"

    # ── Step 3: 安装 Python 依赖包 ────────────────────────────────
    step "Step 3/4 — 安装 Python 依赖包"
    echo "  (此步骤需要网络连接，请耐心等待...)"
    echo ""

    "$VENV_PIP" install --quiet --upgrade pip

    PACKAGES=(
        "fastapi>=0.100.0"
        "uvicorn>=0.22.0"
        "httpx>=0.24.0"
        "pydantic>=2.0.0"
        "aiofiles>=23.0.0"
        "playwright>=1.40.0"
        "pandas>=2.0.0"
        "openpyxl>=3.1.0"
        "yt-dlp>=2024.1.1"
        "requests>=2.31.0"
        "twikit>=2.0.0"
    )

    for pkg in "${PACKAGES[@]}"; do
        pkg_name=$(echo "$pkg" | sed 's/[>=].*//')
        echo -n "  安装 $pkg_name..."
        "$VENV_PIP" install --quiet "$pkg"
        if [ $? -eq 0 ]; then
            echo -e " ${GREEN}✓${NC}"
        else
            echo -e " ${RED}✗ 失败${NC}"
            err "安装 $pkg 失败，请检查网络后重试"
            rm -rf "$VENV_DIR"
            read -p "按回车键退出..." _
            exit 1
        fi
    done

    # ── Step 4: 安装 Playwright Chromium 浏览器 ──────────────────
    step "Step 4/4 — 下载 Playwright Chromium 浏览器驱动"
    echo "  (首次下载约 150-200MB，请耐心等待...)"
    "$VENV_DIR/bin/python" -m playwright install chromium
    if [ $? -ne 0 ]; then
        err "Playwright Chromium 安装失败，请检查网络后重试"
        rm -rf "$VENV_DIR"
        read -p "按回车键退出..." _
        exit 1
    fi
    ok "Chromium 浏览器驱动安装完成"

    # ── 标记安装完成 ──────────────────────────────────────────────
    touch "$SETUP_MARKER"
    echo ""
    banner "══════════════════════════════════════════"
    echo -e "  ${GREEN}${BOLD}所有依赖安装完成！正在启动服务器...${NC}"
    banner "══════════════════════════════════════════"
    echo ""
fi

# ══════════════════════════════════════════════════════════════════
#  启动服务器
# ══════════════════════════════════════════════════════════════════
VENV_PYTHON="$VENV_DIR/bin/python"

# 创建 data 目录（首次使用时）
mkdir -p data

# 释放端口 8000（如有残留进程）
lsof -ti:8000 | xargs kill -9 2>/dev/null
sleep 1

# 启动服务器
"$VENV_PYTHON" server.py &
SERVER_PID=$!

# 等待服务器就绪（最多 10 秒）
for i in $(seq 1 10); do
    if curl -s http://localhost:8000 >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# 打开浏览器
open http://localhost:8000

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  ${GREEN}服务器运行中：http://localhost:8000${NC}${BOLD}      ║${NC}"
echo -e "${BOLD}║  请勿关闭此窗口，关闭将停止服务。       ║${NC}"
echo -e "${BOLD}║  按 Ctrl+C 可手动停止服务器。            ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# 保持终端窗口打开
wait $SERVER_PID
