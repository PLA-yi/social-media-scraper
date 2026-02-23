# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 依赖要求

- **Python ≥ 3.10**（系统自带 macOS Python 3.9 不支持 twikit 的 `Type | Type` 语法）
- **twikit ≥ 2.0.0**

安装方式（macOS，使用 Homebrew Python 3.12）：

```bash
brew install python@3.12   # 若未安装
/opt/homebrew/bin/python3.12 -m pip install twikit --break-system-packages
```

## 运行方式

```bash
bash run.sh       # 自动检查并安装依赖后启动（使用 python3.12）
bash setup.sh     # 仅安装/更新依赖
/opt/homebrew/bin/python3.12 main.py   # 直接运行
```

## 项目结构

```
x/
├── main.py           # 入口：选择模式 → 实例化对应爬虫 → asyncio.run
├── config.py         # 全局常量（TWEET_COUNT、REPLY_COUNT、REQUEST_PAUSE）
├── utils.py          # ensure_dir / safe_text / now_str / save_json / save_csv
└── scraper/
    ├── __init__.py   # 导出 KeywordScraper、ProfileScraper
    ├── base.py       # BaseScraper：twikit 客户端、Cookie 加载、回复采集、汇总
    ├── keyword.py    # KeywordScraper：关键词搜索模式
    └── profile.py    # ProfileScraper：用户主页采集模式
```

## Cookie 认证

本项目通过 Cookie 文件绕过 X 的 API 限制，无需官方 API Key（付费）。

Cookie 文件路径：`data/cookies.json`（启动时若不存在，脚本会打印导出步骤并退出）。

导出方式：
1. 浏览器安装 Cookie-Editor 扩展（作者 cgagnier）
2. 打开并登录 x.com
3. 点击 Cookie-Editor → Export → **Export as JSON**
4. 将内容粘贴保存到 `data/cookies.json`

Cookie 失效后重新导出即可，无需改代码。

## 采集原理

使用 **twikit** 库调用 X 内部接口，无需 API Key，无需 Playwright。

- 关键词搜索：`client.search_tweet(query, product='Top'/'Latest')`
- 用户推文：`client.get_user_by_screen_name(username)` → `user.get_tweets('Tweets')`
- 推文回复：`tweet.get_replies()`
- 分页：`results.next()`

## 架构概览

### BaseScraper（`scraper/base.py`）

- `_init_client()` — 加载 Cookie，初始化 `twikit.Client`
- `_tweet_to_dict(tweet)` — 将 twikit Tweet 对象转为字典（处理属性缺失）
- `scrape_replies(tweet_dict)` — 获取推文回复，分页直到达到 `REPLY_COUNT` 上限
- `_save_summary()` — 输出 `tweets.json/csv` + `all_replies.json/csv`
- `run()` — 入口：init → collect_tweets → scrape_replies → save

### KeywordScraper（`scraper/keyword.py`）

`client.search_tweet(keyword, product)` → 分页 `.next()` 收集到指定数量

### ProfileScraper（`scraper/profile.py`）

- `_parse_input(raw)` — 支持 `@username`、`x.com/@username`、`twitter.com/username`
- `collect_tweets()` — `get_user_by_screen_name` → `user.get_tweets('Tweets')` + 分页

## 注意事项

- twikit 全异步，入口必须用 `asyncio.run(main())`
- X 反爬较严，`REQUEST_PAUSE = 1.0` 秒，不要设太小
- `tweet.full_text` 优先于 `tweet.text`（长推文可能被截断）
- Cookie 有效期通常数周，失效后重新导出

## 数据输出结构

```
data/
  cookies.json          # Cookie-Editor 导出
  {关键词或用户名}_{时间戳}/
    tweets.json / tweets.csv
    replies/{tweet_id}.json
    all_replies.json / all_replies.csv
```

## 关键配置（`config.py`）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `OUTPUT_DIR` | `"data"` | 相对项目根目录 |
| `TWEET_COUNT` | 20 | 默认采集推文数量 |
| `REPLY_COUNT` | 50 | 每条推文最多回复数 |
| `REQUEST_PAUSE` | 1.0s | 请求间隔 |
