"""
SubredditScraper：Subreddit / 用户主页采集模式
"""

import os
import re
import time

from reddit.config import BASE_URL, REQUEST_PAUSE, OUTPUT_DIR
from reddit.utils import ensure_dir, now_str, save_json, save_csv
from reddit.scraper.base import BaseScraper


class SubredditScraper(BaseScraper):
    def __init__(self, url_input: str, sort_mode: str, count: int, download_videos: bool = False, server=None):
        target, self.target_type = self._parse_input(url_input)
        self.target = target
        slug = re.sub(r"[^A-Za-z0-9_-]", "", target) or "reddit"
        super().__init__(slug, download_videos=download_videos, server=server)
        self.sort_mode = sort_mode
        self.count = count

    @staticmethod
    def _parse_input(raw: str):
        raw = raw.strip()
        m = re.search(r"https?://\S+", raw)
        if m:
            raw = m.group(0).rstrip(".,)")
        if re.search(r"reddit\.com/r/([^/?#\s]+)", raw):
            return re.search(r"reddit\.com/r/([^/?#\s]+)", raw).group(1), "subreddit"
        if re.search(r"reddit\.com/u(?:ser)?/([^/?#\s]+)", raw):
            return re.search(r"reddit\.com/u(?:ser)?/([^/?#\s]+)", raw).group(1), "user"
        if re.match(r"r/([A-Za-z0-9_]+)", raw):
            return re.match(r"r/([A-Za-z0-9_]+)", raw).group(1), "subreddit"
        if re.match(r"u(?:ser)?/([A-Za-z0-9_-]+)", raw):
            return re.match(r"u(?:ser)?/([A-Za-z0-9_-]+)", raw).group(1), "user"
        return raw, "subreddit"

    def collect_posts(self) -> list:
        mode_label = {"latest": "最新发布", "hot": "最热", "top": "最高赞"}.get(self.sort_mode)
        sort_map = {"latest": "new", "hot": "hot", "top": "top"}
        sort = sort_map.get(self.sort_mode, "hot")

        if self.target_type == "user":
            base_url = f"{BASE_URL}/user/{self.target}/submitted.json"
            self._log(f"[采集] u/{self.target} — {mode_label} 前 {self.count} 篇")
        else:
            base_url = f"{BASE_URL}/r/{self.target}/{sort}.json"
            self._log(f"[采集] r/{self.target} — {mode_label} 前 {self.count} 篇")

        self.run_dir = os.path.join(OUTPUT_DIR, f"{self.target}_{now_str()}")
        ensure_dir(self.run_dir)

        params = {"limit": min(100, self.count), "raw_json": 1}
        if self.sort_mode == "top":
            params["t"] = "all"

        posts: list = []
        seen_ids: set = set()
        after: str = ""

        while len(posts) < self.count:
            if after:
                params["after"] = after

            data = self._get(base_url, params=params)
            if not data:
                break

            children = data.get("data", {}).get("children", [])
            if not children:
                break

            for child in children:
                if len(posts) >= self.count:
                    break
                d = child.get("data", {})
                pid = d.get("id", "")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                post = self._parse_submission(d)
                posts.append(post)
                self._log(f"  [{len(posts):02d}] {post['title'][:55]}  ({post['num_comments']} 评论)")

            after = data.get("data", {}).get("after", "")
            if not after or len(posts) >= self.count:
                break
            time.sleep(REQUEST_PAUSE)

        self._log(f"\n共收集 {len(posts)} 个帖子\n")
        self.posts = posts
        return posts

    def run(self):
        self.session = self._init_session()
        posts = self.collect_posts()
        save_json(posts, os.path.join(self.run_dir, "posts.json"))
        save_csv(posts, os.path.join(self.run_dir, "posts.csv"))

        comments_dir = os.path.join(self.run_dir, "comments")
        ensure_dir(comments_dir)

        for idx, post in enumerate(posts, 1):
            self._log(f"\n── [{idx}/{len(posts)}] ", end="")
            comments = self.scrape_comments(post)
            self.all_comments.extend(comments)
            if comments:
                save_json(comments, os.path.join(comments_dir, f"{post['post_id']}.json"))
            if self.download_videos:
                self._download_video(post)

        self._save_summary()
