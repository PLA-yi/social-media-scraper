"""
KeywordScraper：关键词搜索模式
  根据关键词搜索抖音视频，采集视频列表后逐条爬取评论。
"""

import asyncio
import os
import re
from datetime import datetime, timedelta

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from douyin.config import OUTPUT_DIR, SCROLL_PAUSE, LOAD_TIMEOUT
from douyin.utils import ensure_dir, safe_text, save_json, save_csv, parse_time_text_to_hours
from douyin.scraper.base import BaseScraper


class KeywordScraper(BaseScraper):
    def __init__(self, keyword: str, count: int, download_videos: bool = False, server=None, sort_by: str = "1", time_filter: int = 0):
        super().__init__(keyword, download_videos=download_videos, server=server)
        self.keyword = keyword
        self.count = count
        self.sort_by = sort_by
        self.time_filter = time_filter

    # ── 搜索页：排序 Tab 点击 ────────────────────────────────────────────────

    async def _apply_sort_tab(self, page):
        """点击正确的排序 Tab，确保 URL 参数实际生效。"""
        # 抖音搜索结果页顶部 Tab：综合 / 最新 / 最热
        # sort_by="0" → 综合（不点击），sort_by="1" → 最新，sort_by="2" → 最热
        if self.sort_by == "0":
            await self._log("  [排序] 使用「综合推荐」排序（默认，不切换 Tab）")
            return
        tab_label = "最新" if self.sort_by == "1" else "最热"
        try:
            # Tab 通常是 <span> 或 <div>，文字内容匹配
            tabs = await page.query_selector_all(
                "[data-e2e='search-tab-item'], "
                ".search-filter-item, "
                "[class*='tab-item'], "
                "[class*='TabItem']"
            )
            for tab in tabs:
                txt = (await tab.inner_text()).strip()
                if tab_label in txt:
                    await tab.click()
                    await page.wait_for_timeout(2000)
                    await self._log(f"  [排序] 已切换至「{tab_label}」Tab")
                    return
            await self._log(f"  [排序] 未找到「{tab_label}」Tab，依赖 URL 参数")
        except Exception as e:
            await self._log(f"  [排序] Tab 点击异常：{e}")

    # ── 搜索页：收集视频列表 ──────────────────────────────────────────────────

    async def collect_videos(self, page) -> list:
        """滚动搜索结果页，采集指定数量的视频信息。"""
        await self._log(f"[搜索] 关键词：{self.keyword}，目标数：{self.count}，排序：{self.sort_by}，时间限制：{self.time_filter}小时")

        from urllib.parse import quote
        url_params = ["type=video"]
        # sort_type: 1=最新发布, 2=最多点赞(最热), 0/不传=综合推荐
        if self.sort_by in ["1", "2"]:
            url_params.append(f"sort_type={self.sort_by}")

        # 官方粗粒度时间过滤（仅最新排序有效）：1=一天内, 7=一周内, 180=半年内
        if self.sort_by == "1" and self.time_filter > 0:
            if self.time_filter <= 24:
                url_params.append("publish_time=1")
            elif self.time_filter <= 168:
                url_params.append("publish_time=7")
            elif self.time_filter <= 4320:
                url_params.append("publish_time=180")

        encoded_kw = quote(self.keyword)
        params_str = "&".join(url_params)
        url = f"https://www.douyin.com/search/{encoded_kw}?{params_str}"
        await self._log(f"[搜索] 请求 URL: {url}")

        await page.goto(url, timeout=LOAD_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await self._wait_if_captcha(page)

        # 等待视频卡片出现
        try:
            await page.wait_for_selector("a[href*='/video/']", timeout=20_000)
        except PlaywrightTimeout:
            await self._wait_if_captcha(page)
            await page.wait_for_timeout(3000)

        # 通过点击排序 Tab 确保排序生效（URL 参数有时被前端重置）
        await self._apply_sort_tab(page)

        videos: list = []
        seen_ids: set = set()

        now = datetime.now()

        for _ in range(40):
            await self._check_control()
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

                info = await self._enrich_video_info(page, vid_id)
                hours_ago = parse_time_text_to_hours(info.get("publish_time", ""))

                # 时间限制过滤逻辑（sort_by == "1"）
                if self.sort_by == "1" and self.time_filter > 0:
                    if hours_ago < 0:
                        await self._log(f"  [跳过] {info['title'][:20]}... 无法解析发布时间。")
                        seen_ids.add(vid_id)
                        continue
                    if hours_ago > self.time_filter:
                        await self._log(f"  [跳过] {info['title'][:20]}... 超过时间限制 ({info.get('publish_time')}, 约 {hours_ago:.1f} 小时前)")
                        await self._log(f"  [打断] 按最新排序且遇到超过限制的视频，直接停止扫描。")
                        self.videos = videos
                        return videos

                seen_ids.add(vid_id)
                videos.append(info)

                # 格式化输出
                if self.sort_by == "1":
                    await self._log(f"  [{len(videos):02d}] (发布时间: {info.get('publish_time', '未知')}) | {info['title'][:45] or info['url']}")
                elif self.sort_by == "2":
                    await self._log(f"  [{len(videos):02d}] (点赞: {info.get('like_count', '未知')}, 收藏: {info.get('collect_count', '未知')}) | {info['title'][:45] or info['url']}")
                else:
                    await self._log(f"  [{len(videos):02d}] {info['title'][:45] or info['url']}")

            await page.evaluate("window.scrollBy(0, 900)")
            await page.wait_for_timeout(int(SCROLL_PAUSE * 1000))

        await self._log(f"\n共收集 {len(videos)} 条视频\n")
        self.videos = videos
        return videos

    async def _enrich_video_info(self, page, vid_id: str) -> dict:
        """从搜索结果卡片提取视频标题、作者、点赞数、收藏数和发布时间。"""
        base = {
            "video_id": vid_id,
            "title": "",
            "author": "",
            "like_count": "",
            "collect_count": "",
            "publish_time": "",
            "url": f"https://www.douyin.com/video/{vid_id}",
        }
        try:
            info = await page.evaluate(
                """(vid) => {
                    const link = document.querySelector('a[href*="/video/' + vid + '"]');
                    if (!link) return {};

                    // 向上找到视频卡片容器（LI 或带 data-e2e 的容器）
                    let container = link;
                    for (let i = 0; i < 10; i++) {
                        const p = container.parentElement;
                        if (!p || p === document.body) break;
                        container = p;
                        if (p.tagName === 'LI'
                            || p.getAttribute('data-e2e') === 'search-video-item'
                            || (p.className && (p.className.includes('card') || p.className.includes('Card')))) {
                            break;
                        }
                    }

                    // ── 标题 ──
                    const titleEl = container.querySelector(
                        '[data-e2e*="title"], [data-e2e*="video-title"], ' +
                        '[class*="video-title"], [class*="VideoTitle"], ' +
                        '[class*="title"]:not([class*="author"]):not([class*="user"])'
                    );

                    // ── 作者 ──
                    const authorEl = container.querySelector(
                        '[data-e2e*="nickname"], [data-e2e*="author-name"], ' +
                        '[class*="nickname"], [class*="NickName"], ' +
                        '[class*="author-name"], [class*="AuthorName"]'
                    );

                    // ── 发布时间 ──
                    let pubTime = '';
                    const timeSelectors = [
                        '[data-e2e*="video-time"]', '[class*="publish-time"]',
                        '[class*="PublishTime"]', '[class*="video-time"]',
                        '.time', '[class*="-time"]'
                    ];
                    for (const sel of timeSelectors) {
                        const el = container.querySelector(sel);
                        if (el) { pubTime = el.innerText.trim(); if (pubTime) break; }
                    }
                    if (!pubTime) {
                        const allText = container.innerText || '';
                        const relMatch = allText.match(/(\d+\s*(?:分钟前|小时前|天前|周前)|昨天|前天|刚刚|刚)/);
                        if (relMatch) pubTime = relMatch[0];
                        else {
                            const dtMatch = allText.match(/((?:20\d{2}[-/.年])?\s*(?:1[0-2]|0?[1-9])[-/.月]\s*(?:3[01]|[12][0-9]|0?[1-9])[日]?)/);
                            if (dtMatch) pubTime = dtMatch[0];
                        }
                    }

                    // ── 点赞数 ──
                    // 优先 data-e2e，其次 class 包含 like/digg，再从互动区域扫描数字
                    let likeCount = '';
                    const likeEl = container.querySelector(
                        '[data-e2e*="like-count"], [data-e2e*="digg-count"], ' +
                        '[class*="like-count"], [class*="LikeCount"], ' +
                        '[class*="digg-count"], [class*="DiggCount"]'
                    );
                    if (likeEl) {
                        likeCount = likeEl.innerText.trim();
                    } else {
                        // 找互动数据容器，取其中第一个纯数字（带K/W/万/亿等单位）
                        const statContainer = container.querySelector(
                            '[class*="stat"], [class*="Stat"], [class*="interact"], [class*="Interact"], ' +
                            '[class*="action"], [class*="Action"]'
                        );
                        const searchIn = statContainer || container;
                        for (const el of searchIn.querySelectorAll('span, em, strong, p')) {
                            const t = el.innerText.trim();
                            if (/^[\d.,]+[KkWwMm万亿]?$/.test(t) && t !== '0') {
                                likeCount = t; break;
                            }
                        }
                    }

                    // ── 收藏数 ──
                    let collectCount = '';
                    const collectEl = container.querySelector(
                        '[data-e2e*="collect"], [data-e2e*="favorite"], ' +
                        '[class*="collect-count"], [class*="CollectCount"], ' +
                        '[class*="favorite-count"], [class*="FavoriteCount"]'
                    );
                    if (collectEl) {
                        collectCount = collectEl.innerText.trim();
                    } else {
                        // 取互动区域第二个数字型文本作为收藏
                        const statContainer = container.querySelector(
                            '[class*="stat"], [class*="Stat"], [class*="interact"], [class*="Interact"], ' +
                            '[class*="action"], [class*="Action"]'
                        );
                        const searchIn = statContainer || container;
                        let numCount = 0;
                        for (const el of searchIn.querySelectorAll('span, em, strong, p')) {
                            const t = el.innerText.trim();
                            if (/^[\d.,]+[KkWwMm万亿]?$/.test(t) && t !== '0') {
                                numCount++;
                                if (numCount === 2) { collectCount = t; break; }
                            }
                        }
                    }

                    return {
                        title: titleEl ? titleEl.innerText.trim() : '',
                        author: authorEl ? authorEl.innerText.trim() : '',
                        like_count: likeCount,
                        collect_count: collectCount,
                        publish_time: pubTime,
                    };
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
            try:
                for idx, video in enumerate(videos, 1):
                    await self._check_control()
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
            except Exception:
                raise
            finally:
                await self._save_summary()
                await browser.close()
