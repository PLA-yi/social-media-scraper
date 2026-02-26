# 社交媒体爬虫控制面板

[English](./README.md)

基于 **FastAPI + Vue 3** 构建的统一 Web 可视化平台，整合了抖音、TikTok、Reddit、X（推特）、YouTube 五个平台的爬虫。所有操作均在浏览器中完成，支持实时日志流式输出和 AI 评论数据分析。

**当前版本：v1.2.1**

---

## 功能特性

- **五平台统一管理** — 抖音、TikTok、Reddit、X、YouTube
- **关键词搜索 & 博主/频道采集** — 每个平台均支持两种模式
- **安全模式 & 快速模式** — 安全模式顺序采集；快速模式开 3 个并发标签页，速度约为安全模式的 3 倍（仅限抖音/TikTok 关键词搜索）
- **暂停 / 停止控制** — 随时暂停（可恢复）或停止（已采集数据立即保存）（仅限抖音/TikTok）
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

## 爬取模式（抖音 / TikTok）

| 模式 | 工作方式 | 速度 |
|------|---------|------|
| **安全模式** | 单标签页，逐视频顺序采集 | 基准 |
| **快速模式** | 同一浏览器会话中 3 个并发标签页 | 约 3 倍 |

两种模式共用相同的登录会话和评论解析逻辑，快速模式无需额外配置。

### 暂停 / 停止

采集运行中，UI 顶部会出现两个控制按钮：

- **⏸ 暂停** — 挂起采集（浏览器保持打开），再次点击可恢复
- **■ 停止** — 终止运行，已采集数据立即保存

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
encrypt/           # 签名工具包（ABogus、XBogus、XGnarly）
douyin/ tiktok/ reddit/ x/ youtube/   # 各平台爬虫
```

核心设计模式：
- **`platform_env()` 上下文管理器** — 为每个平台临时隔离 `sys.path` 与 `sys.modules`，防止五个平台的 `config`/`utils` 模块命名冲突
- **SSE 日志队列** — 所有 `print()` 替换为 `self._log()` → `asyncio.Queue` → `/api/logs` 事件流
- **用户介入机制** — `request_user_intervention()` 挂起爬虫并等待前端"继续执行"按钮，替代阻塞式 `input()`
- **ScrapeControl 状态机** — `idle / running / paused / stopped` 四种状态，通过 `pause_event` 和 `stop_event` 实现协作式取消

---

## 更新日志

### v1.2.1
- **快速爬取模式**（抖音/TikTok 关键词）：同一浏览器会话中 3 路并发标签页，速度约为安全模式 3 倍
- **暂停 / 停止控制**：新增 `/api/pause`、`/api/stop` 端点；采集进行中 UI 显示控制按钮
- **修复**：TikTok 评论区无法自动展开的问题（将 `data-e2e='comments'` 加入点击选择器首位并增加重试逻辑）
- 新增 `encrypt/` 签名工具包（ABogus、XBogus、XGnarly）

### v1.2.0
- 统一 FastAPI + Vue 3 面板替代纯 CLI 工作流
- SSE 实时日志流式输出
- AI 评论分析面板（支持 4 家服务商）
- 高级搜索过滤：按发布时间/热度排序、时间窗口精确筛选

---

## 注意事项

- Python **3.10+**（X 平台依赖的 twikit 内部使用了 match 语句）
- 爬取数据与 `cookies.json` 已通过 `.gitignore` 排除，不会上传至仓库
- 使用抖音/TikTok 前需安装 Playwright 浏览器：`playwright install chromium`

---

## 开源协议

本项目采用 [Apache License 2.0](./LICENSE)。
