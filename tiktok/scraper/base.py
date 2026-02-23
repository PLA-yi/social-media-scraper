"""
BaseScraper：所有爬虫共用的基础能力
  - 浏览器上下文创建
  - 登录 / Cookie 管理
  - 验证码检测与等待
  - 视频评论采集
  - 结果汇总保存
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from typing import Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from tiktok.config import (
    BASE_URL, OUTPUT_DIR, COMMENT_COUNT, SCROLL_PAUSE,
    LOAD_TIMEOUT, HEADLESS, USER_AGENT,
)
from tiktok.utils import ensure_dir, safe_text, now_str, save_json, save_csv


class BaseScraper:
    def __init__(self, run_label: str, download_videos: bool = False, server=None):
        self.server = server
        self.run_dir = os.path.join(OUTPUT_DIR, f"{run_label}_{now_str()}")
        ensure_dir(self.run_dir)
        self.videos: list = []
        self.all_comments: list = []
        self.download_videos = download_videos


    # ── Logging ───────────────────────────────────────────────────────────────

    async def _log(self, msg: str, end: str = "\n"):
        if self.server and hasattr(self.server, '_log'):
            res = self.server._log(msg)
            if __import__('asyncio').iscoroutine(res):
                await res
        else:
            sys.stdout.write(str(msg) + end)
            sys.stdout.flush()

    # ── 浏览器上下文 ──────────────────────────────────────────────────────────

    async def _make_context(self, playwright):
        browser = await playwright.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        return browser, context

    # ── 登录 ──────────────────────────────────────────────────────────────────

    async def _is_logged_in(self, page) -> bool:
        try:
            # TikTok 登录态：头像出现，或登录按钮消失
            el = await page.query_selector(
                "[data-e2e='nav-user-avatar'], "
                "[class*='avatar'], "
                "[data-e2e='login-status-button']"
            )
            if el:
                text = safe_text(await el.inner_text())
                return "Log in" not in text and "登录" not in text
            return False
        except Exception:
            return False

    async def _handle_login(self, page, context):
        """优先加载本地 Cookie；失效则等待用户手动登录后重新保存。"""
        cookie_file = os.path.join(OUTPUT_DIR, "cookies.json")
        ensure_dir(OUTPUT_DIR)

        if os.path.exists(cookie_file):
            await self._log("\n[登录] 检测到本地 Cookie，正在加载...")
            with open(cookie_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
            await page.goto(BASE_URL, timeout=LOAD_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            if await self._is_logged_in(page):
                await self._log("  Cookie 有效，已自动登录。\n")
                return
            await self._log("  Cookie 已过期，需要重新登录。\n")

        await self._log("\n[登录] 请在弹出的浏览器中：")
        await self._log("  1. 点击右上角「Log in」")
        await self._log("  2. 选择登录方式完成登录")
        await self._log("  3. 如出现验证码请手动完成")
        await self._log("  4. 确认页面顶部出现头像后，回到终端按回车\n")
        await page.goto(BASE_URL, timeout=LOAD_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        if self.server:
            msg = ">>> 登录完成后继续 ... "
            if hasattr(self.server, 'request_user_intervention'):
                req_res = self.server.request_user_intervention(msg)
                if __import__('asyncio').iscoroutine(req_res):
                    await req_res
            if hasattr(self.server, 'user_continue_event'):
                await self.server.user_continue_event.wait()
                self.server.user_continue_event.clear()
        else:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, input, "  >>> 登录完成后按回车继续 ... ")
        await page.wait_for_timeout(1500)

        cookies = await context.cookies()
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        await self._log(f"  Cookie 已保存 → {cookie_file}\n")

    # ── 验证码检测 ────────────────────────────────────────────────────────────

    async def _wait_if_captcha(self, page):
        """检测到验证码弹窗时暂停，等待用户手动完成。"""
        selectors = [
            "[class*='captcha']",
            "[id*='captcha']",
            "text=Verify",
            "text=verify you are human",
            "text=请完成验证",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await self._log("  [验证码] 检测到验证码，请在浏览器中手动完成...")
                    if self.server:
                        msg = ">>> 验证码完成后继续 ... "
                        if hasattr(self.server, 'request_user_intervention'):
                            req_res = self.server.request_user_intervention(msg)
                            if __import__('asyncio').iscoroutine(req_res):
                                await req_res
                        if hasattr(self.server, 'user_continue_event'):
                            await self.server.user_continue_event.wait()
                            self.server.user_continue_event.clear()
                    else:
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, input, "  >>> 验证码完成后按回车 ... ")
                    await page.wait_for_timeout(1500)
                    return
            except Exception:
                pass

    # ── 评论采集 ──────────────────────────────────────────────────────────────

    async def _detect_comment_selector(self, page) -> str:
        """
        探测当前页面实际使用的评论条目选择器。
        返回匹配到的选择器字符串，找不到则返回空字符串，并打印调试信息。
        """
        candidates = [
            "[data-e2e='comment-item']",
            "[data-e2e='comment-list-item']",
            "[class*='CommentItemContainer']",
            "[class*='comment-item']",
            "[class*='CommentItem']",
            "[class*='DivCommentItem']",
        ]
        for sel in candidates:
            els = await page.query_selector_all(sel)
            if els:
                await self._log(f"  [选择器] 匹配到评论元素：{sel}  共 {len(els)} 条")
                return sel

        # 找不到时，打印页面上带有 data-e2e 属性的元素 & 有 comment 关键词的 class
        await self._log("  [调试] 未匹配到评论元素，扫描页面中的 data-e2e 和 comment class：")
        debug = await page.evaluate("""
            () => {
                const e2e = Array.from(document.querySelectorAll('[data-e2e]'))
                    .map(el => el.getAttribute('data-e2e'))
                    .filter((v, i, a) => a.indexOf(v) === i)
                    .filter(v => v && v.toLowerCase().includes('comment'));
                const cls = Array.from(document.querySelectorAll('[class]'))
                    .map(el => el.className)
                    .join(' ')
                    .split(/\s+/)
                    .filter((v, i, a) => a.indexOf(v) === i)
                    .filter(v => v.toLowerCase().includes('comment'))
                    .slice(0, 20);
                return { e2e, cls };
            }
        """)
        await self._log(f"    data-e2e (含 comment)：{debug['e2e']}")
        await self._log(f"    class (含 comment)：{debug['cls']}")
        return ""

    async def _try_open_comments(self, page):
        """尝试自动点击评论展开按钮（TikTok 某些页面需要）。"""
        open_selectors = [
            "[data-e2e='comment-icon']",
            "[data-e2e='browse-comment-icon']",
            "[aria-label*='comment' i]",
            "[aria-label*='Comment' i]",
            "button[class*='comment' i]",
            "span[class*='comment' i]",
        ]
        for sel in open_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await page.wait_for_timeout(2000)
                    return
            except Exception:
                pass

    async def scrape_comments(self, page, video: dict) -> list:
        """打开视频页，自动等待评论区加载后采集评论。"""
        label = (video["title"] or video["video_id"])[:35]
        await self._log(f"[评论] {label}")
        try:
            await page.goto(video["url"], timeout=LOAD_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
        except PlaywrightTimeout:
            await self._log("  [超时] 跳过")
            return []

        await self._wait_if_captcha(page)

        # 尝试自动点击评论按钮（部分页面需要）
        await self._try_open_comments(page)

        # 循环等待评论区出现，最多 20 秒
        comment_sel = ""
        for _ in range(10):
            comment_sel = await self._detect_comment_selector(page)
            if comment_sel:
                break
            await page.wait_for_timeout(2000)
        if not comment_sel:
            await self._log("  [跳过] 未能识别评论元素结构，跳过此视频")
            return []

        # 找到评论的可滚动父容器
        scroll_js = f"""
            () => {{
                const item = document.querySelector({json.dumps(comment_sel)});
                let el = item ? item.parentElement : null;
                while (el && el !== document.body) {{
                    const style = getComputedStyle(el);
                    if ((style.overflowY === 'auto' || style.overflowY === 'scroll')
                            && el.scrollHeight > el.clientHeight) {{
                        el.scrollTop += 1500;
                        return true;
                    }}
                    el = el.parentElement;
                }}
                window.scrollBy(0, 1500);
                return false;
            }}
        """

        comments: list = []
        seen_ids: set = set()
        no_new_rounds = 0

        for _ in range(60):
            if len(comments) >= COMMENT_COUNT:
                break

            items = await page.query_selector_all(comment_sel)
            before = len(comments)
            for item in items:
                if len(comments) >= COMMENT_COUNT:
                    break
                try:
                    c = await self._parse_comment_item(item, video["video_id"])
                    if c and c["comment_id"] not in seen_ids:
                        seen_ids.add(c["comment_id"])
                        comments.append(c)
                except Exception as e:
                    await self._log(f"  [警告] 提取评论数据时发生错误: {e}")

            if len(comments) == before:
                no_new_rounds += 1
                if no_new_rounds >= 4:
                    break
            else:
                no_new_rounds = 0
                await self._log(f"  已采集 {len(comments)} 条...", end="\r")

            await page.evaluate(scroll_js)
            await page.wait_for_timeout(int(SCROLL_PAUSE * 1000))

        await self._log(f"  → 共采集 {len(comments)} 条评论")
        return comments

    async def _parse_comment_item(self, item, video_id: str) -> Optional[dict]:
        """从评论 DOM 元素提取文本、用户名、点赞数、时间。"""
        result = await item.evaluate("""
            (el) => {
                // ── 评论正文 ──────────────────────────────────────────────
                let text = '';
                // 优先 data-e2e，回退到 class 关键词，再回退到最长 p/span
                const textEl = el.querySelector(
                    '[data-e2e="comment-text"], [class*="CommentText"], ' +
                    '[class*="comment-text"], p[class*="text"], span[class*="text"]'
                );
                if (textEl) {
                    text = textEl.innerText.trim();
                } else {
                    let maxLen = 0;
                    for (const s of el.querySelectorAll('p, span')) {
                        const t = s.innerText.trim();
                        if (t.length > maxLen && !/^\d+(\.\d+)?[KMB]?$/.test(t)
                                && !/ago$/i.test(t)) {
                            maxLen = t.length; text = t;
                        }
                    }
                }

                // ── 用户名 ────────────────────────────────────────────────
                let username = '';
                const userEl = el.querySelector(
                    '[data-e2e="comment-username-1"], [data-e2e="comment-username"], ' +
                    '[class*="UserName"], [class*="username"], a[href*="/@"]'
                );
                if (userEl) username = userEl.innerText.trim();

                // ── 时间 ──────────────────────────────────────────────────
                let time = '';
                for (const s of el.querySelectorAll('span, p')) {
                    const t = s.innerText.trim();
                    if (/\d+\s*(s|m|h|d|w)$/.test(t)
                        || /\d+\s*(second|minute|hour|day|week|month|year)/i.test(t)
                        || /ago/i.test(t)) {
                        time = t; break;
                    }
                }

                // ── 点赞数 ────────────────────────────────────────────────
                let like = '';
                const likeEl = el.querySelector(
                    '[data-e2e="comment-like-count"], [class*="LikeCount"], ' +
                    '[class*="like-count"], [class*="likeCount"]'
                );
                if (likeEl) like = likeEl.innerText.trim();

                return { text, username, time, like };
            }
        """)

        text = safe_text(result.get("text", ""))
        if not text:
            return None

        username = safe_text(result.get("username", ""))
        comment_id = f"{video_id}_{hash(username + text) & 0xFFFFFFFF:08x}"
        return {
            "comment_id": comment_id,
            "video_id": video_id,
            "username": username,
            "text": text,
            "like_count": safe_text(result.get("like", "")),
            "time": safe_text(result.get("time", "")),
        }

    # ── 视频下载 ──────────────────────────────────────────────────────────────

    async def _download_video(self, video: dict):
        """使用 yt-dlp 下载视频文件到 videos_media/ 目录。"""
        media_dir = os.path.join(self.run_dir, "videos_media")
        ensure_dir(media_dir)
        out_tmpl = os.path.join(media_dir, f"{video['video_id']}.%(ext)s")
        yt_dlp_bin = shutil.which("yt-dlp")
        if not yt_dlp_bin:
            # macOS pip user install 常见路径
            for candidate in sorted(__import__('glob').glob(
                os.path.expanduser("~/Library/Python/*/bin/yt-dlp")
            ), reverse=True):
                if os.path.isfile(candidate):
                    yt_dlp_bin = candidate
                    break
        if yt_dlp_bin:
            cmd = [yt_dlp_bin, "--no-warnings", "-o", out_tmpl, video["url"]]
        else:
            python_bin = shutil.which("python3") or sys.executable
            cmd = [python_bin, "-m", "yt_dlp", "--no-warnings", "-o", out_tmpl, video["url"]]
        await self._log(f"  [下载] {video['video_id']} ...", end="\r")
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            )
            if result.returncode == 0:
                await self._log(f"  [下载完成] {video['video_id']}          ")
            else:
                err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "未知错误"
                await self._log(f"  [下载失败] {video['video_id']}: {err[:120]}")
        except subprocess.TimeoutExpired:
            await self._log(f"  [下载超时] {video['video_id']}：下载超过 300 秒")
        except Exception as e:
            await self._log(f"  [下载错误] {e}")

    # ── 汇总保存 ──────────────────────────────────────────────────────────────

    async def _save_summary(self):
        if not self.all_comments:
            await self._log("\n[汇总] 未采集到评论")
            return
        save_json(self.all_comments, os.path.join(self.run_dir, "all_comments.json"))
        save_csv(self.all_comments, os.path.join(self.run_dir, "all_comments.csv"))
        await self._log(
            f"\n[完成] {len(self.videos)} 个视频 · {len(self.all_comments)} 条评论"
            f"\n[路径] {self.run_dir}/"
        )
