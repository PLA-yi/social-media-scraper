# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 运行方式

```bash
# 一键运行（自动检查并安装依赖）
bash run.sh

# 直接运行
python3 main.py

# 首次安装依赖
bash setup.sh
```

## 项目结构

```
douyin/
├── main.py              # 入口：交互菜单，实例化并调用对应爬虫
├── config.py            # 全局常量（OUTPUT_DIR、COMMENT_COUNT 等）
├── utils.py             # 工具函数（ensure_dir、save_json、save_csv 等）
├── scraper/
│   ├── __init__.py      # 导出 KeywordScraper、BloggerScraper
│   ├── base.py          # BaseScraper：登录、验证码、评论采集、汇总
│   ├── keyword.py       # KeywordScraper：关键词搜索模式
│   └── blogger.py       # BloggerScraper：博主作品采集模式
├── data/                # 输出数据目录（运行时自动创建子目录）
├── requirements.txt
├── run.sh
└── setup.sh
```

## 架构概览

### BaseScraper（`scraper/base.py`）

所有爬虫的共用基类，包含：
- `_make_context()` — 创建 Playwright 浏览器及上下文（统一 UA、locale、viewport）
- `_handle_login()` — 加载本地 Cookie（`data/cookies.json`），失效则等待用户手动登录并重新保存
- `_wait_if_captcha()` — 检测验证码弹窗，暂停等待用户手动完成
- `scrape_comments()` + `_parse_comment_item()` — 滚动评论区采集评论
- `_download_video()` — yt-dlp 下载视频到 `videos_media/`（自动查找 macOS pip user install 非标路径）
- `_save_summary()` — 汇总输出 all_comments.json / all_comments.csv

### KeywordScraper（`scraper/keyword.py`）

继承 `BaseScraper`，关键词搜索模式：
1. `collect_videos()` — 滚动搜索结果页，采集指定数量的视频（ID、标题、作者、点赞数）
2. `_enrich_video_info()` — 从搜索卡片容器向上遍历 5 层提取元数据
3. `run()` — 登录 → 采集视频列表 → 逐条爬取评论 → 汇总

### BloggerScraper（`scraper/blogger.py`）

继承 `BaseScraper`，博主作品采集模式：
1. `resolve_profile_url()` — 打开用户粘贴的链接（支持短链 `v.douyin.com`），跟随重定向提取博主 uid，尝试获取昵称更新输出目录名
2. `_try_sort_by_hot()` — 尝试点击主页"最热"Tab，找不到则静默回退
3. `collect_blogger_videos()` — 自动等待（最多 20s）视频列表加载，滚动采集视频卡片（含播放量）
4. `run()` — 登录 → 解析链接 → 采集视频列表 → 逐条爬取评论 → 可选下载视频 → 汇总

## 数据输出结构

```
data/
  cookies.json                         # 登录 Cookie（两种模式共用）
  {关键词或博主昵称}_{时间戳}/
    videos.json / videos.csv           # 视频列表
    comments/
      {video_id}.json                  # 单视频评论
    videos_media/
      {video_id}.mp4                   # 下载的视频（开启下载时）
    all_comments.json / all_comments.csv
```

## 关键配置（`config.py`）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `OUTPUT_DIR` | `"data"` | 数据输出目录 |
| `VIDEO_COUNT` | 20 | 关键词搜索默认视频数量 |
| `COMMENT_COUNT` | 500 | 每视频最多评论数 |
| `SCROLL_PAUSE` | 2.0s | 滚动间隔，防反爬 |
| `HEADLESS` | False | 是否无头模式 |
| `LOAD_TIMEOUT` | 30000ms | 页面加载超时 |

## DOM 解析策略

抖音对 class 名做混淆，所有选择器均采用双层策略：
- **优先**：`data-e2e` 语义属性（相对稳定）
- **回退**：class 名关键词模糊匹配（`[class*="nickname"]`）+ 结构遍历

博主主页视频卡片采集使用三层回退：`[data-e2e="user-post-item"]` → class 名列表容器 → 所有 `/video/` 链接的父元素。
