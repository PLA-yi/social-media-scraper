"""
BloggerScraper：博主作品采集模式
  输入博主主页链接（支持短链），采集其最新/流量最高的 N 篇作品并爬取评论。
"""

import asyncio
import os
import re
from typing import Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from douyin.config import OUTPUT_DIR, SCROLL_PAUSE, LOAD_TIMEOUT
from douyin.utils import ensure_dir, safe_text, now_str, save_json, save_csv
from douyin.scraper.base import BaseScraper


class BloggerScraper(BaseScraper):
    """
    sort_mode:
      'latest' — 最新发布
      'hot'    — 流量最高
    """

    def __init__(self, url_input: str, sort_mode: str, count: int, download_videos: bool = False, server=None):
        # 从粘贴内容（可含分享文案）中提取第一个 URL
        m = re.search(r'https?://\S+', url_input)
        self.input_url = m.group(0).rstrip('。,，') if m else url_input.strip()
        slug = re.sub(r'[^A-Za-z0-9_-]', '', self.input_url.split('/')[-1]) or 'blogger'
        super().__init__(slug, download_videos=download_videos, server=server)
        self.sort_mode = sort_mode
        self.count = count

    # ── 解析博主主页链接 ───────────────────────────────────────────────────────

    async def resolve_profile_url(self, page) -> Optional[str]:
        """
        打开用户提供的链接（含短链重定向），读取最终 URL 提取博主 uid。
        成功后尝试从页面获取博主昵称，更新输出目录名。
        """
        await self._log(f"[解析链接] {self.input_url}")
        try:
            await page.goto(self.input_url, timeout=LOAD_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
        except PlaywrightTimeout:
            pass
        await self._wait_if_captcha(page)

        final_url = page.url
        m = re.search(r'/user/([^?#/]+)', final_url)
        if m and m.group(1) not in ('self', ''):
            uid = m.group(1)
            profile_url = f"https://www.douyin.com/user/{uid}"

            # 用博主昵称更新输出目录名
            try:
                name_el = await page.query_selector(
                    '[data-e2e="user-info-nickname"], [data-e2e*="nickname"], '
                    '[class*="nickname"], h1[class*="name"]'
                )
                if name_el:
                    nickname = safe_text(await name_el.inner_text())
                    if nickname:
                        self.run_dir = os.path.join(OUTPUT_DIR, f"{nickname}_{now_str()}")
                        ensure_dir(self.run_dir)
                        await self._log(f"  博主昵称：{nickname}")
            except Exception:
                pass

            await self._log(f"  主页地址：{profile_url}\n")
            return profile_url

        await self._log(f"  [错误] 链接未跳转到博主主页（当前页面：{final_url}）")
        await self._log("  请确认链接是否正确，或直接粘贴抖音博主主页的完整 URL")
        return None

    # ── 切换"最热"排序 ────────────────────────────────────────────────────────

    async def _try_sort_by_hot(self, page):
        """尝试点击主页"最热"Tab；找不到则静默回退。"""
        hot_selectors = [
            "[data-e2e='tab-hot']",
            "[data-e2e='user-tab-hot']",
            "li[class*='tab']:has-text('最热')",
            "span:text-is('最热')",
            "div[role='tab']:has-text('最热')",
        ]
        for sel in hot_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(2000)
                    await self._log("  [排序] 已切换到最热排序\n")
                    return
            except Exception:
                pass

        try:
            tabs = await page.query_selector_all(
                "li[role='tab'], div[role='tab'], [class*='tab-item']"
            )
            for tab in tabs:
                text = safe_text(await tab.inner_text())
                if "最热" in text or "热门" in text:
                    await tab.click()
                    await page.wait_for_timeout(2000)
                    await self._log("  [排序] 已切换到最热排序\n")
                    return
        except Exception:
            pass

        await self._log("  [提示] 未找到最热排序按钮，将使用默认排序（通常为最新发布）\n")

    # ── 博主主页：采集视频列表 ────────────────────────────────────────────────

    async def collect_blogger_videos(self, page, profile_url: str) -> list:
        """滚动博主主页采集视频卡片（含播放量）。"""
        await page.goto(profile_url, timeout=LOAD_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await self._wait_if_captcha(page)

        if self.sort_mode == "hot":
            await self._try_sort_by_hot(page)

        # 自动等待视频列表出现，最多 20 秒
        has_videos = False
        for _ in range(10):
            has_videos = await page.evaluate(
                "() => document.querySelectorAll('a[href*=\"/video/\"]').length > 0"
            )
            if has_videos:
                break
            await page.wait_for_timeout(2000)

        if not has_videos:
            debug = await page.evaluate(
                "() => Array.from(document.querySelectorAll('a[href]')).slice(0,10).map(a=>a.href)"
            )
            await self._log("  [调试] 页面链接：", debug)
            await self._log("  [警告] 未找到视频链接，请确认已进入博主主页且视频可见")
            return []

        videos: list = []
        seen_ids: set = set()
        no_new_rounds = 0

        for _ in range(60):
            if len(videos) >= self.count:
                break

            items = await page.evaluate("""
                () => {
                    let cards = Array.from(document.querySelectorAll('[data-e2e="user-post-item"]'));
                    if (!cards.length) {
                        cards = Array.from(document.querySelectorAll(
                            '[class*="video-list"] li, [class*="videoList"] li, ' +
                            '[class*="post-list"] li, [class*="postList"] li, ' +
                            'ul[class*="list"] li'
                        ));
                    }
                    if (!cards.length) {
                        const links = document.querySelectorAll('a[href*="/video/"]');
                        const parents = new Set();
                        for (const a of links) {
                            if (a.parentElement) parents.add(a.parentElement);
                        }
                        cards = Array.from(parents);
                    }

                    return cards.map(card => {
                        const a = card.querySelector('a[href*="/video/"]');
                        const href = a ? a.href : '';
                        const m = href.match(/\/video\/(\d+)/);
                        const vid = m ? m[1] : '';
                        if (!vid) return null;

                        let title = '';
                        const titleEl = card.querySelector(
                            '[data-e2e*="title"], [class*="title"], [class*="desc"], p[class*="text"]'
                        );
                        if (titleEl) {
                            title = titleEl.innerText.trim();
                        } else {
                            let maxLen = 0;
                            for (const s of card.querySelectorAll('p, span')) {
                                const t = s.innerText.trim();
                                if (t.length > maxLen && !/^\d+(\.\d+)?[万亿]?$/.test(t)) {
                                    maxLen = t.length; title = t;
                                }
                            }
                        }

                        let play_count = '';
                        const playEl = card.querySelector(
                            '[data-e2e*="play"], [class*="play-count"], [class*="playCount"], ' +
                            '[class*="play_count"], [class*="view-count"]'
                        );
                        if (playEl) {
                            play_count = playEl.innerText.trim();
                        } else {
                            for (const el of card.querySelectorAll('span, p, div')) {
                                const t = el.innerText.trim();
                                if (/^\d+(\.\d+)?(万|亿)?$/.test(t) && t) {
                                    play_count = t; break;
                                }
                            }
                        }

                        let like_count = '';
                        const likeEl = card.querySelector(
                            '[data-e2e*="like"], [class*="like-count"], [class*="likeCount"], [class*="digg"]'
                        );
                        if (likeEl) like_count = likeEl.innerText.trim();

                        return { vid, title, play_count, like_count };
                    }).filter(Boolean);
                }
            """)

            before_scroll = len(videos)
            for item in items:
                if len(videos) >= self.count:
                    break
                vid_id = item.get("vid", "")
                if not vid_id or vid_id in seen_ids:
                    continue
                seen_ids.add(vid_id)
                entry = {
                    "video_id": vid_id,
                    "title": safe_text(item.get("title", "")),
                    "play_count": safe_text(item.get("play_count", "")),
                    "like_count": safe_text(item.get("like_count", "")),
                    "url": f"https://www.douyin.com/video/{vid_id}",
                }
                videos.append(entry)
                play_info = f"  播放量：{entry['play_count']}" if entry["play_count"] else ""
                await self._log(f"  [{len(videos):02d}] {entry['title'][:45] or vid_id}{play_info}")

            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(int(SCROLL_PAUSE * 1000))

            if len(videos) == before_scroll:
                no_new_rounds += 1
                if no_new_rounds >= 5:
                    break
            else:
                no_new_rounds = 0

        await self._log(f"\n共收集 {len(videos)} 条视频\n")
        self.videos = videos
        return videos

    # ── 主流程 ────────────────────────────────────────────────────────────────

    async def run(self):
        async with async_playwright() as p:
            browser, context = await self._make_context(p)
            page = await context.new_page()

            await self._handle_login(page, context)

            profile_url = await self.resolve_profile_url(page)
            if not profile_url:
                await browser.close()
                return

            mode_label = "最新发布" if self.sort_mode == "latest" else "流量最高"
            await self._log(f"[采集] {mode_label}前 {self.count} 篇作品")
            videos = await self.collect_blogger_videos(page, profile_url)
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
