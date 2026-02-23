"""
BaseScraper：Reddit 爬虫基础类

认证方式：从真实浏览器导出 Cookie，脚本携带 Cookie 请求 Reddit JSON API。
无需 Playwright，无需 API Key，无需在脚本内登录。

Cookie 导出步骤：
  1. 用 Chrome/Firefox 打开 https://www.reddit.com 并登录
  2. 安装插件 Cookie-Editor（Chrome: https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm）
  3. 点击插件图标 → Export → Export as JSON → 复制全部内容
  4. 新建文件 Social media/reddit/data/cookies.json，把复制的内容粘贴进去保存
  5. 再次运行脚本即可（Cookie 有效期通常数周至数月）
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from reddit.config import BASE_URL, OUTPUT_DIR, COMMENT_COUNT, REQUEST_PAUSE, USER_AGENT
from reddit.utils import ensure_dir, safe_text, now_str, save_json, save_csv

COOKIE_FILE = os.path.join(OUTPUT_DIR, "cookies.json")

# 模拟真实浏览器请求头
BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.reddit.com/",
    "X-Requested-With": "XMLHttpRequest",
}


class BaseScraper:
    def __init__(self, run_label: str, download_videos: bool = False, server=None):
        self.server = server
        self._loop = None
        if server:
            try:
                self._loop = __import__('asyncio').get_running_loop()
            except RuntimeError:
                pass
        self.run_dir = os.path.join(OUTPUT_DIR, f"{run_label}_{now_str()}")
        ensure_dir(self.run_dir)
        self.posts: list = []
        self.all_comments: list = []
        self.download_videos = download_videos
        self.session = None


    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, end: str = "\\n"):
        if self.server and hasattr(self.server, '_log'):
            res = self.server._log(msg)
            if __import__('asyncio').iscoroutine(res):
                try:
                    loop = __import__('asyncio').get_running_loop()
                    loop.create_task(res)
                except RuntimeError:
                    if hasattr(self, '_loop') and self._loop and getattr(self._loop, 'is_closed', lambda: False)() == False:
                        __import__('asyncio').run_coroutine_threadsafe(res, self._loop)
        else:
            sys.stdout.write(str(msg) + end)
            sys.stdout.flush()


    def _request_intervention(self, text: str):
        if self.server and hasattr(self.server, 'request_user_intervention'):
            res = self.server.request_user_intervention(text)
            if __import__('asyncio').iscoroutine(res) and getattr(self, '_loop', None):
                fut = __import__('asyncio').run_coroutine_threadsafe(res, self._loop)
                # optionally wait for the message to be queued
        else:
            input(text)

    # ── Session 初始化 ────────────────────────────────────────────────────────

    def _init_session(self) -> requests.Session:
        """创建携带真实浏览器 Cookie 的 Session。"""
        session = requests.Session()
        session.headers.update(BASE_HEADERS)

        ensure_dir(OUTPUT_DIR)

        if not os.path.exists(COOKIE_FILE):
            self._print_cookie_guide()
            self._request_intervention("  >>> 完成后按回车继续 ... ")
            if self.server and hasattr(self.server, 'user_continue_event'):
                while not self.server.user_continue_event.is_set():
                    time.sleep(0.5)
                self.server.user_continue_event.clear()

        if os.path.exists(COOKIE_FILE):
            loaded = self._load_cookies(session)
            if loaded:
                self._log(f"[认证] 已加载 {loaded} 个 Cookie\n")
            else:
                self._log("[警告] Cookie 文件为空或格式不正确，将以未登录状态请求\n")
        else:
            self._log("[警告] 未找到 Cookie 文件，将以未登录状态请求\n")

        return session

    def _load_cookies(self, session: requests.Session) -> int:
        """
        从 Cookie-Editor 导出的 JSON 文件加载 Cookie。
        支持两种格式：
          - Cookie-Editor 格式：[{"name": ..., "value": ..., "domain": ...}]
          - Netscape 格式：{"reddit.com": [{"name": ..., "value": ...}]}
        """
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._log(f"  [错误] 读取 Cookie 文件失败：{e}")
            return 0

        count = 0

        # Cookie-Editor 导出格式（列表）
        if isinstance(data, list):
            for c in data:
                name = c.get("name", "")
                value = c.get("value", "")
                domain = c.get("domain", ".reddit.com")
                path = c.get("path", "/")
                if name and value:
                    session.cookies.set(name, value, domain=domain, path=path)
                    count += 1

        # 字典格式
        elif isinstance(data, dict):
            for domain, cookies in data.items():
                if isinstance(cookies, list):
                    for c in cookies:
                        name = c.get("name", "")
                        value = c.get("value", "")
                        if name and value:
                            session.cookies.set(name, value, domain=domain)
                            count += 1

        return count

    def _print_cookie_guide(self):
        self._log("\n" + "=" * 56)
        self._log("  首次使用：需要导出浏览器 Cookie")
        self._log("=" * 56)
        self._log(f"""
步骤：
  1. 用 Chrome 打开 https://www.reddit.com 并登录账号

  2. 安装 Cookie-Editor 插件：
     在 Chrome 应用商店搜索「Cookie-Editor」安装
     （作者：cgagnier，图标为橙色饼干）

  3. 打开 reddit.com，点击 Cookie-Editor 图标
     → 点击右下角「Export」→「Export as JSON」
     → 自动复制到剪贴板

  4. 在终端运行：
     mkdir -p "{os.path.abspath(OUTPUT_DIR)}"
     pbpaste > "{os.path.abspath(COOKIE_FILE)}"

     （或手动新建该文件并粘贴内容）

  5. 完成后按回车，脚本自动加载 Cookie 继续运行
     Cookie 有效期通常为数周，失效后重复步骤 3-4 即可
""")

    # ── HTTP 请求 ─────────────────────────────────────────────────────────────

    def _get(self, url: str, params: dict = None) -> Optional[dict]:
        """带限流等待和自动重试的 GET 请求。"""
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=15)

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 15))
                    self._log(f"  [限流] 等待 {wait}s ...")
                    time.sleep(wait)
                    continue

                if resp.status_code == 403:
                    self._log(f"  [403] Cookie 可能已失效，请重新导出 Cookie 后再运行")
                    return None

                self._log(f"  [HTTP {resp.status_code}] {url}")
                return None

            except Exception as e:
                self._log(f"  [请求错误] {e}（第 {attempt + 1} 次）")
                time.sleep(2)

        return None

    # ── 时间格式化 ────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_time(utc_ts) -> str:
        try:
            return datetime.fromtimestamp(float(utc_ts), tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            return ""

    # ── 帖子解析 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_submission(d: dict) -> dict:
        return {
            "post_id":      d.get("id", ""),
            "title":        safe_text(d.get("title", "")),
            "subreddit":    d.get("subreddit", ""),
            "author":       d.get("author", "[deleted]"),
            "score":        d.get("score", 0),
            "upvote_ratio": d.get("upvote_ratio", 0),
            "num_comments": d.get("num_comments", 0),
            "is_video":     d.get("is_video", False),
            "url":          d.get("url", ""),
            "permalink":    d.get("permalink", ""),
            "selftext":     safe_text(d.get("selftext", ""))[:500],
            "time":         BaseScraper._fmt_time(d.get("created_utc", 0)),
        }

    # ── 评论采集 ──────────────────────────────────────────────────────────────

    def scrape_comments(self, post: dict) -> list:
        """获取帖子全部评论，递归展开嵌套评论树。"""
        label = (post["title"] or post["post_id"])[:40]
        self._log(f"[评论] {label}")

        permalink = post["permalink"].rstrip("/")
        url = f"{BASE_URL}{permalink}.json"
        data = self._get(url, params={"limit": 500, "depth": 10})

        if not data or len(data) < 2:
            self._log("  [跳过] 无法获取评论")
            return []

        comments: list = []
        seen_ids: set = set()
        self._flatten_comments(
            data[1].get("data", {}).get("children", []),
            post["post_id"],
            comments,
            seen_ids,
        )

        time.sleep(REQUEST_PAUSE)
        self._log(f"  → 共采集 {len(comments)} 条评论（含子评论）")
        return comments

    def _flatten_comments(
        self,
        children: list,
        post_id: str,
        out: list,
        seen_ids: set,
        depth: int = 0,
    ):
        """递归展开 Reddit 嵌套评论树。"""
        for child in children:
            if len(out) >= COMMENT_COUNT:
                return
            if child.get("kind") != "t1":
                continue
            d = child.get("data", {})
            cid = d.get("id", "")
            if not cid or cid in seen_ids:
                continue

            text = safe_text(d.get("body", ""))
            if not text or text in ("[deleted]", "[removed]"):
                continue

            seen_ids.add(cid)
            parent_raw = d.get("parent_id", "")
            parent_id = parent_raw.split("_", 1)[-1] if "_" in parent_raw else parent_raw

            out.append({
                "comment_id": cid,
                "post_id":    post_id,
                "parent_id":  parent_id,
                "depth":      depth,
                "author":     d.get("author", "[deleted]"),
                "text":       text,
                "score":      d.get("score", 0),
                "time":       self._fmt_time(d.get("created_utc", 0)),
            })

            replies = d.get("replies", "")
            if isinstance(replies, dict):
                sub_children = replies.get("data", {}).get("children", [])
                self._flatten_comments(sub_children, post_id, out, seen_ids, depth + 1)

    # ── 视频下载 ──────────────────────────────────────────────────────────────

    def _download_video(self, post: dict):
        """使用 yt-dlp 下载视频帖到 videos_media/ 目录。"""
        if not post.get("is_video") and not post.get("url", "").endswith(
            (".mp4", ".gif", ".gifv")
        ):
            return

        media_dir = os.path.join(self.run_dir, "videos_media")
        ensure_dir(media_dir)
        download_url = f"{BASE_URL}{post['permalink']}"
        out_tmpl = os.path.join(media_dir, f"{post['post_id']}.%(ext)s")

        yt_dlp_bin = shutil.which("yt-dlp")
        if not yt_dlp_bin:
            for candidate in sorted(
                glob.glob(os.path.expanduser("~/Library/Python/*/bin/yt-dlp")),
                reverse=True,
            ):
                if os.path.isfile(candidate):
                    yt_dlp_bin = candidate
                    break

        cmd = (
            [yt_dlp_bin, "--no-warnings", "--merge-output-format", "mp4",
             "-o", out_tmpl, download_url]
            if yt_dlp_bin
            else [shutil.which("python3") or sys.executable, "-m", "yt_dlp",
                  "--no-warnings", "--merge-output-format", "mp4",
                  "-o", out_tmpl, download_url]
        )

        self._log(f"  [下载] {post['post_id']} ...", end="\r")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                self._log(f"  [下载完成] {post['post_id']}          ")
            else:
                err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "未知错误"
                self._log(f"  [下载失败] {post['post_id']}: {err[:120]}")
        except subprocess.TimeoutExpired:
            self._log(f"  [下载超时] {post['post_id']}：下载超过 300 秒")
        except Exception as e:
            self._log(f"  [下载错误] {e}")

    # ── 汇总保存 ──────────────────────────────────────────────────────────────

    def _save_summary(self):
        if not self.all_comments:
            self._log("\n[汇总] 未采集到评论")
            return
        save_json(self.all_comments, os.path.join(self.run_dir, "all_comments.json"))
        save_csv(self.all_comments, os.path.join(self.run_dir, "all_comments.csv"))
        self._log(
            f"\n[完成] {len(self.posts)} 个帖子 · {len(self.all_comments)} 条评论"
            f"\n[路径] {self.run_dir}/"
        )
