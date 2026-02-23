# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

本仓库整合了 5 个核心社交媒体爬虫程序：抖音（`douyin/`）、TikTok（`tiktok/`）、Reddit（`reddit/`）、X（`x/`）和 YouTube（`youtube/`）。

最初，这些爬虫是基于命令行的独立 CLI 工具。为了提升体验，系统现已全面升级重构为 **FastAPI + Vue 3 的统一 Web 可视化全栈架构**。所有的终端交互（如打印日志、等待手动验证码等）均已通过异步事件进行全解耦并转移至前端处理。

## 运行方式 & 常用命令

### 启动服务
```bash
# 方式 1 - 一键启动（自动打开浏览器）：
./Start_Scraper.command

# 方式 2 - 手动启动（可查看服务端日志）：
python3 server.py
# 浏览器访问 http://localhost:8000
```

### 停止服务
```bash
kill -9 $(lsof -t -i :8000)
```

### 安装依赖
各平台有独立的 `requirements.txt`，可按需单独安装：
```bash
pip install -r douyin/requirements.txt
pip install -r tiktok/requirements.txt
pip install -r reddit/requirements.txt
pip install -r x/requirements.txt
pip install -r youtube/requirements.txt
```
YouTube 爬虫还依赖系统级 `yt-dlp`（优先查找 `$PATH`，回退到 `~/Library/Python/*/bin/yt-dlp`，最终回退到 `python3 -m yt_dlp`）。

## 系统架构与模块结构

```
Social media_01/
├── server.py                 # FastAPI 核心：路由、动态导入、SSE 日志
├── static/
│   └── index.html            # Web UI（Vue 3 + Tailwind CSS，单文件，无构建步骤）
├── data/                     # 全局统一的数据输出目录（cookies.json 也在此）
├── Start_Scraper.command     # macOS 一键启动脚本
├── douyin/                   # Playwright 浏览器自动化
├── tiktok/                   # Playwright 浏览器自动化
├── reddit/                   # requests HTTP 客户端（无浏览器）
├── x/                        # twikit 异步客户端（Python 3.10+ required）
└── youtube/                  # yt-dlp 子进程调用
```

## API 端点总览（`server.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 返回 `static/index.html` |
| `POST` | `/api/scrape` | 启动爬虫任务（`platform`, `target`, `mode`, `count`） |
| `POST` | `/api/resume` | 解除用户介入挂起（点击 Resume 按钮） |
| `GET` | `/api/logs` | SSE 实时日志流（爬虫日志） |
| `GET` | `/api/data/files` | 列出 `data/` 下所有子文件夹，含 `meta`（`has_all_comments`） |
| `POST` | `/api/data/clean-empty` | 删除 `data/` 下所有无文件的空白文件夹 |
| `POST` | `/api/chat` | AI 数据分析，返回 **SSE 流式输出**（`provider`, `api_key`, `folder_paths[]`, `prompt`） |

`/api/scrape` 的 `mode` 取值：
- `douyin`/`tiktok`：`keyword` 或 `blogger`
- `reddit`：`keyword` 或 `subreddit`（映射到 `SubredditScraper`）
- `youtube`：`keyword` 或 `channel`（映射到 `ChannelScraper`）
- `x`：`keyword` 或 `user`（映射到 `ProfileScraper`）

## 核心架构机制（重点）

### 1. 动态 `sys.path` 环境隔离（`platform_env`）

**问题**：5 个项目都有各自的 `import config` / `import utils`，从外部 `server.py` 加载时会产生 `ModuleNotFoundError` 或命名空间冲突。

**实现**（`server.py:46`）：`platform_env(platform_name)` 上下文管理器：
1. 将对应平台目录临时插入 `sys.path[0]`
2. 将 `config`、`utils`、`main`、`scraper.*` 等冲突模块从 `sys.modules` 暂时移出
3. 将 `{platform}.config` 别名为全局 `config`，使覆盖（OUTPUT_DIR 等）生效
4. `yield` 后恢复原始状态

**关键**：`scraper.run()` 的调用必须在 `with platform_env(platform):` 块内部完成，否则动态导入的模块会找不到依赖。

### 2. 异步/同步调度（`run_scraper` 中的 `inspect` 检测）

`server.py` 的 `run_scraper()` 通过 `inspect.iscoroutinefunction(scraper.run)` 判断执行方式：
- **X（twikit）**：原生 async → `await scraper.run()`
- **其他 4 个平台**：同步 → `await asyncio.get_event_loop().run_in_executor(None, scraper.run)`

添加新平台时无需修改调度逻辑，只需确保 `run()` 方法签名正确即可。

### 3. 同步爬虫的异步安全日志（`_log` 线程安全桥接）

同步爬虫（Reddit、YouTube）运行在线程池中，无法直接 `await`。其 `_log()` 使用如下模式将日志转发到 async 的 `log_queue`：
```python
def _log(self, msg):
    res = self.server._log(msg)
    if asyncio.iscoroutine(res):
        try:
            loop = asyncio.get_running_loop()  # 在主线程有 loop 时
            loop.create_task(res)
        except RuntimeError:
            asyncio.run_coroutine_threadsafe(res, self._loop)  # 线程中
```
`self._loop` 在 `__init__` 中通过 `asyncio.get_running_loop()` 捕获并保存。

### 4. SSE 实时日志（`_log()` + `log_queue`）

所有 `print()` 均已被废除。爬虫通过 `self._log(msg)` 发送日志，`ServerAdapter` 将其推入 `asyncio.Queue`，`/api/logs` 的 SSE 生成器持续读取队列并以 `data: {...}\n\n` 格式推送至前端。SSE 使用 1 秒超时轮询，超时时发送 `: keep-alive\n\n` 心跳防止连接断开。

### 5. 用户介入流程（`ACTION_REQUIRED`）

原 `input()` 阻塞模式已被替换：
1. 爬虫调用 `await self.server.request_user_intervention(msg)` → 向前端发送 `{"type": "ACTION_REQUIRED", ...}`
2. 爬虫调用 `await self.server.user_continue_event.wait()` 进入休眠
3. 用户在 UI 点击"Resume"→ `POST /api/resume` → `resume_event.set()` → 爬虫唤醒

### 6. `OUTPUT_DIR` 全局覆盖

`server.py` 启动时立即导入各平台 `config` 模块并覆盖 `OUTPUT_DIR` 为根目录的 `data/`，防止数据散落在各平台子目录中。**顺序重要**：必须先覆盖 `config.OUTPUT_DIR`，再导入使用它的 scraper 模块（`platform_env` 的别名机制保证了这一点）。

## 各平台爬虫内部结构

每个平台子目录（`douyin/`, `tiktok/` 等）均遵循相同模式：

```
{platform}/
├── config.py          # OUTPUT_DIR、计数限制、延迟等常量（会被 server.py 覆盖）
├── utils.py           # 平台专属辅助函数
├── main.py            # 已弃用的 CLI 入口，不再使用
├── requirements.txt
└── scraper/
    ├── __init__.py
    ├── base.py         # BaseScraper：初始化、_log()、Cookie 加载、数据导出
    ├── keyword.py      # KeywordScraper：关键词搜索模式
    └── blogger.py      # BloggerScraper/SubredditScraper/ChannelScraper/ProfileScraper
```

**添加新平台**时需要：
1. 在 `server.py` 顶部覆盖 `{platform}_config.OUTPUT_DIR`
2. 在 `run_scraper()` 的 `if/elif` 链中添加平台分支
3. 确保 `BaseScraper.__init__` 接受 `server=adapter` 参数并将 `_log()` 路由到 `adapter._log()`
4. 同步爬虫需在 `__init__` 中保存 `self._loop = asyncio.get_running_loop()` 供线程安全日志使用

## 平台关键差异

| 平台 | 驱动 | 鉴权方式 | 异步模式 |
|------|------|----------|----------|
| 抖音 | Playwright（Chromium） | 手动登录 + `data/cookies.json` | 同步，`run_in_executor` 包装 |
| TikTok | Playwright（Chromium） | 手动登录 + `data/cookies.json` | 同步，`run_in_executor` 包装 |
| Reddit | requests | Cookie-Editor JSON 导出至 `data/cookies.json` | 同步，`run_in_executor` 包装 |
| X | twikit | Cookie-Editor JSON 导出至 `data/cookies.json` | 原生 async（`await scraper.run()`） |
| YouTube | yt-dlp 子进程 | 无需鉴权（公开 API） | 同步，`run_in_executor` 包装 |

**抖音 vs TikTok**：抖音使用硬编码 DOM 选择器（`[data-e2e='comment-item']`）；TikTok 使用 6 级动态选择器检测，且因计数单位不同（K/M/B vs 万/亿）需要不同的解析逻辑。locale 设置也不同：抖音用 `zh-CN`，TikTok 用 `en-US`。

**评论采集策略对比**：

| 平台 | 方式 | 分页机制 | 最大轮次 |
|------|------|----------|----------|
| 抖音 | Playwright JS，`[data-e2e='comment-item']` | 滚动 | 60 次 |
| TikTok | Playwright JS，动态选择器检测 | 滚动 + 手动展开 | 60 次 |
| Reddit | HTTP `/{sub}/{id}.json` 递归 | JSON 树递归 | — |
| X | twikit `tweet.get_replies()` | `.next()` 分页 | — |
| YouTube | yt-dlp `--write-comments` | yt-dlp 内部处理 | — |

## Cookie 管理

所有平台共用 `data/cookies.json`，但格式和来源不同：

- **抖音/TikTok**：由 Playwright `context.cookies()` 直接写入，格式为 `[{"name":..., "value":..., "domain":...}]`
- **Reddit/X**：需用户通过浏览器插件（如 Cookie-Editor）手动导出，支持两种格式：
  - Cookie-Editor 列表格式：`[{"name":..., "value":..., "domain":...}]`
  - Netscape 字典格式：`{"reddit.com": [{"name":..., "value":...}]}`
- **YouTube**：不使用 Cookie

Cookie 过期后，Playwright 平台会检测登录状态并触发用户介入流程重新登录；Reddit/X 需手动重新导出。

## 数据输出格式

每次运行在 `data/` 下生成时间戳目录：
```
data/{run_label}_{YYYYMMDD_HHMMSS}/
├── videos.json / videos.csv        # 视频/帖子/推文元数据
├── all_comments.json / .csv        # 聚合所有评论（AI 分析的唯一数据源）
└── comments/
    └── {item_id}.json              # 每条内容的评论（单独文件）
```

## AI 分析功能（`/api/chat`）

### 数据源
**固定读取 `all_comments.json`**，不读取其他文件。文件不存在时返回 `{"error": "NO_COMMENTS_FILE"}`，前端据此展示警告并阻止发送。

`/api/data/files` 响应中的 `meta[folderName].has_all_comments` 布尔值供前端在选择文件夹时即时判断可用性。

### 评论数据预处理
原始 JSON 冗余字段多（约 10 倍），服务端解析后压缩为每行一条的紧凑格式：
```
[数据概览] 共 N 条评论，来自文件夹：xxx

[用户名](N赞): 评论内容
...
[以上为前 N 条，剩余 M 条因上下文限制未载入]
```
`MAX_CONTENT_CHARS = 20000`，压缩后约可载入 400 条（视评论长度而定）。

### 流式输出（SSE）
`/api/chat` 返回 `StreamingResponse(media_type="text/event-stream")`，逐 token 转发 AI 响应。事件格式：
- `{"type": "delta", "content": "..."}` — 正常 token
- `{"type": "done"}` — 流结束
- `{"type": "error", "message": "..."}` — 上游 API 错误

前端根据 `Content-Type` 头判断是否为流：`application/json` 表示校验错误，`text/event-stream` 表示正常流式响应。

### 支持的 AI 提供商

| provider 值 | 服务 | 模型 |
|------------|------|------|
| `moonshot` | Moonshot Kimi | `moonshot-v1-32k` |
| `zhipu` | 智谱 ChatGLM | `glm-4` |
| `minimax` | MiniMax | `abab6.5s-chat` |
| `openrouter` | OpenRouter | `openai/gpt-4o-mini` |

所有请求固定 `max_tokens: 2048` 保留输出预算。路径遍历攻击已在服务端阻断（`startswith(data_dir)` 检查）。
