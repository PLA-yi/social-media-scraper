"""
KeywordScraperFast：抖音并行多标签页模式

流程：
  1. 浏览器采集视频列表（与安全模式相同）
  2. 同一浏览器上下文中开 3 个并发标签页同时采集评论
     （复用 BaseScraper.scrape_comments，无需额外签名）

速度提升：3 路并发同时采集评论，比安全模式快约 3 倍。
"""

import asyncio
import os

from playwright.async_api import async_playwright

from douyin.config import OUTPUT_DIR
from douyin.utils import ensure_dir, save_json, save_csv
from douyin.scraper.base import BaseScraper

_CONCURRENCY = 3   # 并发标签页数量（过多会增加反爬风险）


class KeywordScraperFast(BaseScraper):
    def __init__(self, keyword: str, count: int, download_videos: bool = False,
                 server=None, sort_by: str = "0", time_filter: int = 0):
        super().__init__(keyword, download_videos=download_videos, server=server)
        self.keyword     = keyword
        self.count       = count
        self.sort_by     = sort_by
        self.time_filter = time_filter

    # ── 视频采集（复用安全模式）──────────────────────────────────────────

    async def collect_videos(self, page) -> list:
        from douyin.scraper.keyword import KeywordScraper
        tmp = KeywordScraper.__new__(KeywordScraper)
        tmp.__dict__.update(self.__dict__)
        return await tmp.collect_videos(page)

    # ── 单视频评论采集（并发任务单元）────────────────────────────────────

    async def _process_video(self, idx: int, total: int, video: dict,
                              context,
                              comments_dir: str,
                              semaphore: asyncio.Semaphore) -> list:
        async with semaphore:
            await self._check_control()
            label = (video["title"] or video["video_id"])[:35]
            await self._log(f"── [{idx}/{total}] {label}")

            tab = await context.new_page()
            try:
                comments = await self.scrape_comments(tab, video)
                if comments:
                    save_json(comments, os.path.join(comments_dir, f"{video['video_id']}.json"))
                return comments
            except Exception as e:
                await self._log(f"  [错误] {e}")
                return []
            finally:
                await tab.close()

    # ── 主流程 ────────────────────────────────────────────────────────────

    async def run(self):
        async with async_playwright() as p:
            browser, context = await self._make_context(p)
            try:
                # ① 浏览器采集视频列表
                page = await context.new_page()
                await self._handle_login(page, context)
                videos = await self.collect_videos(page)
                await page.close()

                if not videos:
                    await self._log("[错误] 未采集到视频，退出。")
                    await self._save_summary()
                    return

                save_json(videos, os.path.join(self.run_dir, "videos.json"))
                save_csv(videos,  os.path.join(self.run_dir, "videos.csv"))

                # ② 并发多标签页采集评论（复用同一浏览器上下文）
                comments_dir = os.path.join(self.run_dir, "comments")
                ensure_dir(comments_dir)
                total = len(videos)
                await self._log(
                    f"\n[快速] 开始并发采集评论（{_CONCURRENCY} 路并发标签页 · 同一浏览器会话）\n"
                )

                semaphore = asyncio.Semaphore(_CONCURRENCY)
                tasks = [
                    self._process_video(i, total, v, context, comments_dir, semaphore)
                    for i, v in enumerate(videos, 1)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, list):
                        self.all_comments.extend(r)
                    elif isinstance(r, Exception):
                        await self._log(f"  [错误] {r}")

            finally:
                await browser.close()

        await self._save_summary()
