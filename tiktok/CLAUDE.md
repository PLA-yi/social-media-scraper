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
tiktok/
├── main.py          # 入口：询问下载选项 → 选择模式 → 实例化对应爬虫
├── config.py        # 全局常量（BASE_URL、OUTPUT_DIR、COMMENT_COUNT 等）
├── utils.py         # ensure_dir / safe_text / now_str / save_json / save_csv
└── scraper/
    ├── __init__.py  # 导出 KeywordScraper、BloggerScraper
    ├── base.py      # BaseScraper：登录、验证码、评论采集、视频下载、汇总
    ├── keyword.py   # KeywordScraper：关键词搜索模式
    └── blogger.py   # BloggerScraper：创作者主页采集模式
```

## 架构概览

### BaseScraper（`scraper/base.py`）

所有爬虫的共用基类：
- `_make_context()` — Playwright Chromium 上下文（UA、locale=en-US、viewport）
- `_handle_login()` — 加载 `data/cookies.json`，过期则等待手动登录并重新保存
- `_wait_if_captcha()` — 检测验证码弹窗（英文 "Verify"），暂停等待手动完成
- `_detect_comment_selector()` — 动态探测评论元素选择器，找不到时打印调试信息
- `_try_open_comments()` — 自动点击评论图标按钮（TikTok 需要手动展开评论区）
- `scrape_comments()` — 打开视频页 → 点击评论按钮 → 动态探测选择器 → 滚动采集
- `_download_video()` — yt-dlp 下载到 `videos_media/`（自动查找非标路径）
- `_save_summary()` — 输出 `all_comments.json` / `all_comments.csv`

### KeywordScraper（`scraper/keyword.py`）

关键词搜索模式：导航到 `/search/video?q={keyword}` → 滚动采集视频链接 → 逐条爬取评论

### BloggerScraper（`scraper/blogger.py`）

创作者作品采集模式：
1. `resolve_profile_url()` — 打开链接（支持 `vm.tiktok.com` 短链），跟随重定向提取 `@username`
2. `_try_sort_by_hot()` — 尝试点击 "Popular" Tab，找不到则静默回退
3. `collect_blogger_videos()` — 自动等待（最多 20s）视频列表加载，滚动采集视频卡片

## TikTok 特有说明

**评论区需动态探测**：TikTok DOM 结构与抖音不同，评论选择器不固定，`_detect_comment_selector()` 按优先级探测 6 个候选选择器。如全部失败，会打印页面中含 `comment` 的 `data-e2e` 属性值和 class 名用于调试。

**评论区需先点击展开**：部分 TikTok 页面评论区默认收起，`scrape_comments()` 调用 `_try_open_comments()` 自动点击评论图标。

**视频卡片播放量单位**：K / M / B（区别于抖音的万/亿）。

## 数据输出结构

```
data/
  cookies.json
  {创作者名或关键词}_{时间戳}/
    videos.json / videos.csv
    comments/{video_id}.json
    videos_media/{video_id}.mp4    # 开启下载时
    all_comments.json / all_comments.csv
```

## 关键配置（`config.py`）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `BASE_URL` | `https://www.tiktok.com` | TikTok 域名 |
| `OUTPUT_DIR` | `"data"` | 数据输出目录（相对项目根） |
| `COMMENT_COUNT` | 500 | 每视频最多评论数 |
| `SCROLL_PAUSE` | 2.0s | 滚动间隔，防反爬 |
| `HEADLESS` | False | 显示浏览器窗口 |
| `LOAD_TIMEOUT` | 30000ms | 页面加载超时 |
