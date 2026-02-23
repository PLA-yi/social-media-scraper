# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 运行方式

```bash
bash run.sh       # 自动检查并安装依赖后启动
bash setup.sh     # 仅安装/更新依赖
python3 main.py   # 直接运行（已安装依赖时）
```

## 项目结构

```
reddit/
├── main.py           # 入口：询问下载选项 → 选择模式 → 实例化对应爬虫
├── config.py         # 全局常量（BASE_URL、POST_COUNT、REQUEST_PAUSE 等）
├── utils.py          # ensure_dir / safe_text / now_str / save_json / save_csv
└── scraper/
    ├── __init__.py   # 导出 KeywordScraper、SubredditScraper
    ├── base.py       # BaseScraper：HTTP 请求、评论采集、视频下载、汇总
    ├── keyword.py    # KeywordScraper：关键词搜索模式
    └── subreddit.py  # SubredditScraper：Subreddit / 用户主页采集模式
```

## Cookie 认证

本项目通过真实浏览器 Cookie 绕过 Reddit 的匿名限制（未登录状态下 JSON API 返回 403）。

Cookie 文件路径：`data/cookies.json`（启动时若不存在，脚本会打印导出步骤并等待）。

导出方式：Chrome 安装 Cookie-Editor 插件（作者 cgagnier） → 打开 reddit.com → Export as JSON → 粘贴到文件：
```bash
pbpaste > "/path/to/reddit/data/cookies.json"
```

Cookie 失效后重新导出即可，无需改代码。

## 架构概览

**与抖音/TikTok 的核心差异**：本项目使用 Reddit 公开 JSON API（`requests`），无需 Playwright 浏览器自动化。

### BaseScraper（`scraper/base.py`）

- `_get(url, params)` — HTTP GET，含 429 限流等待（尊重 `Retry-After` 头）和 3 次自动重试
- `scrape_comments(post)` — 请求 `{permalink}.json`，递归扁平化嵌套评论树
- `_flatten_comments()` — 递归处理 Reddit 评论树（`kind=t1` 才是评论，`more` 对象跳过）
- `_download_video(post)` — yt-dlp 下载视频帖到 `videos_media/`（仅 `is_video=True` 的帖子），自动查找非标 yt-dlp 路径
- `_save_summary()` — 输出 `all_comments.json` / `all_comments.csv`

### KeywordScraper（`scraper/keyword.py`）

调用 `GET /search.json?q=keyword&sort=relevance&type=link`，使用 `after` 参数分页，采集帖子列表后逐条爬取评论。

### SubredditScraper（`scraper/subreddit.py`）

支持多种输入格式（`r/Python`、`u/username`、完整 URL），`_parse_input()` 统一解析为 `(名称, 类型)`。

- Subreddit：`GET /r/{sub}/{sort}.json`
- 用户：`GET /user/{username}/submitted.json`
- sort_mode：`latest`→`new`，`hot`→`hot`，`top`→`top?t=all`

## Reddit API 数据结构说明

- 帖子对象 `kind=t3`，评论对象 `kind=t1`，`more` 对象代表"加载更多"（当前实现跳过，即热门帖子的折叠评论不会被采集）
- 评论的 `parent_id` 格式为 `t1_xxx`（回复评论）或 `t3_xxx`（顶层评论），输出时去掉前缀
- 视频帖 `is_video=True`，下载时使用帖子 permalink 而非 URL 字段（yt-dlp 可直接解析 Reddit 页面）

## 数据输出结构

```
data/
  {关键词或目标名称}_{时间戳}/
    posts.json / posts.csv              # 帖子列表（含标题、作者、分数、评论数等）
    comments/{post_id}.json            # 单帖评论（含嵌套深度 depth、parent_id）
    videos_media/{post_id}.mp4         # 下载的视频（开启下载且为视频帖时）
    all_comments.json / all_comments.csv
```

## 关键配置（`config.py`）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `BASE_URL` | `https://www.reddit.com` | Reddit 域名 |
| `OUTPUT_DIR` | `"data"` | 相对项目根目录 |
| `POST_COUNT` | 20 | 默认采集帖子数量 |
| `COMMENT_COUNT` | 500 | 每帖最多评论数 |
| `REQUEST_PAUSE` | 1.5s | 请求间隔，避免限流 |
