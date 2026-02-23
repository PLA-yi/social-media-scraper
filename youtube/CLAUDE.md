# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 依赖要求

- **Python ≥ 3.10**（系统自带的 macOS Python 3.9 不支持 yt-dlp 2025.10.15+）
- **yt-dlp ≥ 2026.02.04**（旧版本无法绕过 YouTube 的 HLS 403 限制）

安装方式（macOS，使用 Homebrew Python 3.12）：

```bash
brew install python@3.12
/opt/homebrew/bin/python3.12 -m pip install yt-dlp --break-system-packages
# yt-dlp 会安装到 /opt/homebrew/bin/yt-dlp
```

## 运行方式

```bash
bash run.sh       # 自动检查并安装依赖后启动
bash setup.sh     # 仅安装/更新依赖
python3 main.py   # 直接运行（已安装依赖时）
```

## 采集原理

使用 **yt-dlp** 调用 YouTube 内部接口，无需 API Key，无需账号登录。

- 关键词搜索：`ytsearchN:keyword`
- 频道视频：`https://www.youtube.com/@username/videos`
- 视频元数据：`yt-dlp --dump-json URL`
- 评论：`yt-dlp --write-comments --extractor-args youtube:player_client=tv_embedded --format sb0/mhtml/best URL`
- 视频下载：`yt-dlp --extractor-args youtube:player_client=tv_embedded URL`（不加 `--cookies-from-browser`）

## 项目结构

```
youtube/
├── main.py           # 入口：询问下载选项 → 选择模式 → 实例化对应爬虫
├── config.py         # 全局常量（OUTPUT_DIR、VIDEO_COUNT、COMMENT_COUNT）
├── utils.py          # ensure_dir / safe_text / now_str / save_json / save_csv
└── scraper/
    ├── __init__.py   # 导出 KeywordScraper、ChannelScraper
    ├── base.py       # BaseScraper：yt-dlp 调用、评论采集、视频下载、汇总
    ├── keyword.py    # KeywordScraper：关键词搜索模式
    └── channel.py    # ChannelScraper：频道 / 博主主页采集模式
```

## 架构概览

### BaseScraper（`scraper/base.py`）

- `_find_ytdlp()` — 自动查找 yt-dlp 路径（优先 `/opt/homebrew/bin/yt-dlp`，兼容 macOS pip user install 非标路径）
- `_run_ytdlp(args)` — 运行 yt-dlp 子进程，返回 stdout
- `_fetch_info(url)` — 获取单个视频完整元数据（`--dump-json`）
- `_fetch_info_list(url, flat)` — 获取播放列表/搜索结果，每行一个 JSON
- `scrape_comments(video)` — 使用 `player_client=tv_embedded` + `--format sb0/mhtml/best` 确保 info.json 写入；`--cookies-from-browser chrome` 用于评论认证
- `_download_video(video)` — 使用 `player_client=tv_embedded`，**不加** `--cookies-from-browser`（加了反而 403）

### KeywordScraper（`scraper/keyword.py`）

`ytsearchN:keyword` → `_fetch_info_list(flat=True)` 快速获取 ID 列表，再逐个 `_fetch_info` 获取详情

### ChannelScraper（`scraper/channel.py`）

- `_parse_input(raw)` — 支持 `@username`、`UCxxxx`、完整 URL，统一转为 `/videos` 页面 URL
- `collect_videos()` — `--flat-playlist` 先获取视频 ID 列表，再逐个 `_fetch_info` 获取详情（播放量等）

## 评论说明

- yt-dlp 评论写入临时文件 `data/{run_dir}/_tmp_comments/{video_id}.info.json`，解析后自动删除
- 必须使用 `player_client=tv_embedded`，否则新版 yt-dlp 在 `--skip-download` 时找不到格式，info.json 不会写入
- 必须加 `--format sb0/mhtml/best` 指定一个必然存在的格式（缩略图），防止格式检查报错中断写入
- **不要**加 `--extractor-args youtube:max_comments=N,0,0,0`，这个参数会导致评论数为 0
- 评论包含 `is_reply` 字段（True 表示是回复，False 表示顶层评论）

## 关键配置（`config.py`）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `OUTPUT_DIR` | `"data"` | 相对项目根目录 |
| `VIDEO_COUNT` | 20 | 默认采集视频数量 |
| `COMMENT_COUNT` | 100 | 每视频最多评论数 |

## 数据输出结构

```
data/
  {关键词或频道名}_{时间戳}/
    videos.json / videos.csv
    comments/{video_id}.json
    videos_media/{video_id}.mp4    # 开启下载时
    all_comments.json / all_comments.csv
```
