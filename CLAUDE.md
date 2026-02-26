# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

本仓库整合了 5 个核心社交媒体爬虫程序：抖音（`douyin/`）、TikTok（`tiktok/`）、Reddit（`reddit/`）、X（`x/`）和 YouTube（`youtube/`）。

最初，这些爬虫是基于命令行的独立 CLI 工具。为了提升体验，系统现已全面升级重构为 **FastAPI + Vue 3 的统一 Web 可视化全栈架构**。所有的终端交互（如打印日志、等待手动验证码等）均已通过异步事件进行全解耦并转移至前端处理。

## 运行与开发测试命令

### 1. 启动服务（常规运行）
```bash
# 方式 1 - 一键启动（自动打开浏览器）：
./Start_Scraper.command

# 方式 2 - 手动启动（可查看服务端日志）：
python3 server.py
# 浏览器访问 http://localhost:8000
```
**停止服务**：`kill -9 $(lsof -t -i :8000)`

### 2. 依赖安装
各平台有独立的 `requirements.txt`，可按需单独安装。在开发时：
```bash
pip install -r douyin/requirements.txt
pip install -r tiktok/requirements.txt
pip install -r reddit/requirements.txt
pip install -r x/requirements.txt
pip install -r youtube/requirements.txt
pip install fastapi uvicorn pydantic httpx
```
*Note: YouTube 爬虫还依赖系统级 `yt-dlp`（优先查找 `$PATH`，回退到 `~/Library/Python/*/bin/yt-dlp`）。

### 3. 开发测试
- **独立运行脚本测试**：如果是独立调试某平台的逻辑（如 DOM 选择器解析），你可以直接在根目录创建临时测试脚本（如 `test_douyin_search.py`），使用相应的 `Scraper` 实例去采集并输出结果。
  - **重要注意事项**：为了防止命名冲突问题（各平台有各自的 `config`/`utils`），你需要使用 `server.py` 里的 `platform_env("douyin")` 上下文去加载平台里的代码：
    ```python
    import asyncio
    from server import platform_env, ServerAdapter
    
    async def main():
        adapter = ServerAdapter()
        with platform_env("douyin"):
            from douyin.scraper.keyword import KeywordScraper
            s = KeywordScraper("关键词", 5, False, adapter)
            await s.run()
            
    asyncio.run(main())
    ```
- 目前没有标准化的集成测试框架（如 pytest），需依赖 `python3 server.py` 控制台的实时调试或编写临时的 runner 脚本执行。

## 核心架构与机制摘要

### 1. 动态 `sys.path` 环境隔离（`platform_env`）
**痛点**：5 个平台的子目录里都有各自的 `import config` / `import utils`。如果在外部的 `server.py` 直接并行加载，会造成 `ModuleNotFoundError` 和命名空间相互污染。
**解决**：`platform_env(platform_name)` 是一个 context manager（在 `server.py` 中）。
它不仅把 `{platform_name}` 插入 `sys.path[0]`，还把已加载的冲突模块（如全局的`config`模块）从 `sys.modules` 中暂时移出替换，等代码块执行完毕后再恢复原始状态。

### 2. 混合调度（async / sync）
`server.py` 里的 `run_scraper` 调用通过 `inspect.iscoroutinefunction(scraper.run)` 来决定运行方式：
- **原生 async（X / twikit）**：直接 `await scraper.run()`
- **同步/阻塞 Playwright 进程（其它平台）**：丢到线程池里 `await asyncio.get_event_loop().run_in_executor(None, scraper.run)`

### 3. Log 桥接与 UI 阻断机制
所有平台原来的 `print()` 已全部改成 `self._log()`。底层是通过将字典对象入队 `asyncio.Queue`，在前端路由 `/api/logs` 开设 SSE 流式轮询拉取。
同时如果遇到人机验证（如要求输入验证码或登录），会用 `request_user_intervention()` 进行 `event.wait()` 挂起，直到前端调用 `/api/resume` 才会恢复工作。

### 4. 复杂高级搜索过滤（Time & Sort logic）
如果遇到“按特定小时内的数据来筛选搜索”的需求，由于官方的平台多数只提供粗粒度的搜索筛选（如一天内、一周内），我们需要借助 **“代码层的精准筛选”**。
- **机制**：在 TikTok 和 Douyin 的 `KeywordScraper` 类中，注入 `sort_by` 和 `time_filter` 字段。其中 `sort_by` 仅包含两种模式：`1` (最新发布) 和 `2` (最热/最多点赞)。
- **数据抓取**：利用 Playwright 的 `page.evaluate()` 精准采集 DOM 层上的“发布时间文本”（如 "3天前"、"5 hours ago"）。
- **Python层解析**：统一交给 `utils.parse_time_text_to_hours(time_text)` 转换为距离现在的小时的 float 值。
- **采集阻断（Break/Continue）**：如果此时超出了 `time_filter` 且排序类型为 `最新发布 (sort_by="1")`，则后文均为老数据，直接 `break` 外层循环提前结束爬虫采集，节省开销。

## 代码结构地图
- `server.py`：路由与逻辑控制核心。
- `static/index.html`：Vue3 单文件面板，整合配置以及大语言模型的流式分析。
- `data/`：统领全局的输出数据目录（保存各种 Cookie json 及所有提取内容）。
- `douyin/`, `tiktok/`, `reddit/`, `x/`, `youtube/`：爬虫主目录。每个平台统一含有如下的文件范式：
  - `config.py`（平台配置的默认值，输出目录常常被 `server.py` 在启动时覆盖）
  - `utils.py`（特权化的解析支持函数，如格式化日期解析）
  - `scraper/base.py`：公共基类与日志打印、下载辅助功能
  - `scraper/keyword.py`：普通关键词搜索并进行视频爬梳循环控制的主逻辑
  - `scraper/blogger.py` 或同类文件：提取特定用户频道内的帖子
