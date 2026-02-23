# 社交媒体爬虫控制面板

[English](./README.md)

基于 **FastAPI + Vue 3** 构建的统一 Web 可视化平台，整合了抖音、TikTok、Reddit、X（推特）、YouTube 五个平台的爬虫。所有操作均在浏览器中完成，支持实时日志流式输出和 AI 评论数据分析。

---

## 功能特性

- **五平台统一管理** — 抖音、TikTok、Reddit、X、YouTube
- **关键词搜索 & 博主/频道采集** — 每个平台均支持两种模式
- **实时终端日志** — SSE 流式推送，无需刷新页面
- **人工介入流程** — 遇到登录/验证码时浏览器自动弹出，完成后点击"继续执行"
- **AI 数据分析** — 最多同时选择 10 个数据集，逐 token 流式输出分析结果
- **数据管理** — 浏览输出文件夹，一键清理空白目录

---

## 快速开始

```bash
# 1. 安装依赖（按需选择平台）
pip install -r douyin/requirements.txt
pip install -r tiktok/requirements.txt
pip install -r reddit/requirements.txt
pip install -r x/requirements.txt
pip install -r youtube/requirements.txt

# 2. 启动服务
python3 server.py

# 3. 浏览器访问 http://localhost:8000
```

**macOS 一键启动**（自动打开浏览器）：
```bash
./Start_Scraper.command
```

**停止服务：**
```bash
kill -9 $(lsof -t -i :8000)
```

> YouTube 还需要系统级 `yt-dlp`：`brew install yt-dlp`
>
> Playwright 浏览器需单独安装：`playwright install chromium`

---

## 平台说明

| 平台 | 驱动方式 | 鉴权方式 |
|------|----------|----------|
| 抖音 | Playwright（Chromium） | 手动登录 → 自动保存 Cookie |
| TikTok | Playwright（Chromium） | 手动登录 → 自动保存 Cookie |
| Reddit | HTTP requests | Cookie-Editor 插件导出 |
| X（推特） | twikit 异步客户端 | Cookie-Editor 插件导出 |
| YouTube | yt-dlp 子进程 | 无需登录（公开内容） |

---

## 数据输出结构

每次运行在 `data/` 下生成带时间戳的目录：

```
data/{标签}_{YYYYMMDD_HHMMSS}/
├── videos.json / videos.csv        # 视频/帖子/推文元数据
├── all_comments.json / .csv        # 聚合所有评论（AI 分析数据源）
└── comments/
    └── {item_id}.json              # 每条内容的评论（单独文件）
```

---

## AI 数据分析

切换到 **AI 数据分析** 标签页，最多可同时选择 10 个数据集的 `all_comments.json`，向 AI 提问，回答以打字机效果逐字流式输出。

支持的 AI 服务商（需自行填入 API Key）：

| 服务商 | 模型 |
|--------|------|
| Moonshot Kimi | `moonshot-v1-32k` |
| 智谱 ChatGLM | `glm-4` |
| MiniMax | `abab6.5s-chat` |
| OpenRouter | `openai/gpt-4o-mini` |

---

## 系统架构

```
server.py          # FastAPI 核心：路由、SSE 日志、动态爬虫加载
static/index.html  # Vue 3 + Tailwind CSS 单文件 UI（无需构建）
data/              # 统一数据输出目录 + 共享 cookies.json
douyin/ tiktok/ reddit/ x/ youtube/   # 各平台爬虫
```

核心设计模式：
- **`platform_env()` 上下文管理器** — 为每个平台临时隔离 `sys.path` 与 `sys.modules`，防止五个平台的 `config`/`utils` 模块命名冲突
- **SSE 日志队列** — 所有 `print()` 替换为 `self._log()` → `asyncio.Queue` → `/api/logs` 事件流
- **用户介入机制** — `request_user_intervention()` 挂起爬虫并等待前端"继续执行"按钮，替代阻塞式 `input()`

---

## 注意事项

- Python **3.10+**（X 平台依赖的 twikit 内部使用了 match 语句）
- 爬取数据与 `cookies.json` 已通过 `.gitignore` 排除，不会上传至仓库
- 使用抖音/TikTok 前需安装 Playwright 浏览器：`playwright install chromium`

---

## 开源协议

本项目采用 [Apache License 2.0](./LICENSE)。
