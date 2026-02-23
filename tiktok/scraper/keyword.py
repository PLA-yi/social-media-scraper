"""
KeywordScraper：关键词搜索模式
  根据关键词搜索 TikTok 视频，采集视频列表后逐条爬取评论。
"""

import asyncio
import os
import re
from urllib.parse import quote

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from tiktok.config import BASE_URL, OUTPUT_DIR, SCROLL_PAUSE, LOAD_TIMEOUT
from tiktok.utils import ensure_dir, safe_text, save_json, save_csv
from tiktok.scraper.base import BaseScraper


class KeywordScraper(BaseScraper):
    def __init__(self, keyword: str, count: int, download_videos: bool = False, server=None):
        super().__init__(keyword, download_videos=download_videos, server=server)
        self.keyword = keyword
        self.count = count

    # ── 搜索页：收集视频列表 ──────────────────────────────────────────────────

    async def collect_videos(self, page) -> list:
        """滚动搜索结果页，采集指定数量的视频信息。"""
        await self._log(f"[搜索] 关键词：{self.keyword}，目标数量：{self.count}")
        encoded = quote(self.keyword)
        url = f"{BASE_URL}/search/video?q={encoded}"
        await page.goto(url, timeout=LOAD_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await self._wait_if_captcha(page)

        try:
            await page.wait_for_selector("a[href*='/video/']", timeout=20_000)
        except PlaywrightTimeout:
            await self._wait_if_captcha(page)
            await page.wait_for_timeout(3000)

        videos: list = []
        seen_ids: set = set()

        for _ in range(40):
            if len(videos) >= self.count:
                break

            links = await page.eval_on_selector_all(
                "a[href*='/video/']",
                "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))"
            )

            for item in links:
                if len(videos) >= self.count:
                    break
                href = item.get("href", "")
                m = re.search(r"/video/(\d+)", href)
                if not m:
                    continue
                vid_id = m.group(1)
                if vid_id in seen_ids:
                    continue
                seen_ids.add(vid_id)

                info = await self._enrich_video_info(page, vid_id, href)
                videos.append(info)
                await self._log(f"  [{len(videos):02d}] {info['title'][:45] or info['url']}")

            await page.evaluate("window.scrollBy(0, 900)")
            await page.wait_for_timeout(int(SCROLL_PAUSE * 1000))

        await self._log(f"\n共收集 {len(videos)} 条视频\n")
        self.videos = videos
        return videos

    async def _enrich_video_info(self, page, vid_id: str, href: str) -> dict:
        """从搜索结果卡片提取视频标题、作者、点赞数。"""
        base = {
            "video_id": vid_id,
            "title": "",
            "author": "",
            "like_count": "",
            "url": href if href.startswith("http") else f"{BASE_URL}/video/{vid_id}",
        }
        try:
            info = await page.evaluate(
                """(vid) => {
                    const link = document.querySelector('a[href*="/video/' + vid + '"]');
                    if (!link) return {};
                    let el = link;
                    for (let i = 0; i < 6; i++) {
                        el = el.parentElement;
                        if (!el) break;
                        const titleEl = el.querySelector(
                            '[data-e2e*="video-desc"], [class*="video-meta-title"], ' +
                            '[class*="title"], [class*="desc"]'
                        );
                        const authorEl = el.querySelector(
                            '[data-e2e*="author"], [class*="author"], ' +
                            'a[href*="/@"], [class*="username"]'
                        );
                        const likeEl = el.querySelector(
                            '[data-e2e*="like"], [class*="like-count"], [class*="LikeCount"]'
                        );
                        if (titleEl || authorEl) {
                            return {
                                title: titleEl ? titleEl.innerText.trim() : '',
                                author: authorEl ? authorEl.innerText.trim() : '',
                                like_count: likeEl ? likeEl.innerText.trim() : '',
                            };
                        }
                    }
                    return {};
                }""",
                vid_id,
            )
            base.update(info)
        except Exception:
            pass
        return base

    # ── 主流程 ────────────────────────────────────────────────────────────────

    async def run(self):
        async with async_playwright() as p:
            browser, context = await self._make_context(p)
            page = await context.new_page()

            await self._handle_login(page, context)

            videos = await self.collect_videos(page)
            save_json(videos, os.path.join(self.run_dir, "videos.json"))
            save_csv(videos, os.path.join(self.run_dir, "videos.csv"))

            comments_dir = os.path.join(self.run_dir, "comments")
            ensure_dir(comments_dir)
            for idx, video in enumerate(videos, 1):
                await self._log(f"\n── [{idx}/{len(videos)}] ", end="")
                comments = await self.scrape_comments(page, video)
                self.all_comments.extend(comments)
                if comments:
                    save_json(
                        comments,
                        os.path.join(comments_dir, f"{video['video_id']}.json"),
                    )
                if self.download_videos:
                    await self._download_video(video)
                await page.wait_for_timeout(1500 + (idx % 4) * 400)

            await self._save_summary()
            await browser.close()
