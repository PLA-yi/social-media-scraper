"""
KeywordScraper：关键词搜索模式
"""

import os
import time

from reddit.config import BASE_URL, REQUEST_PAUSE
from reddit.utils import ensure_dir, save_json, save_csv
from reddit.scraper.base import BaseScraper


class KeywordScraper(BaseScraper):
    def __init__(self, keyword: str, count: int, download_videos: bool = False, server=None):
        super().__init__(keyword, download_videos=download_videos, server=server)
        self.keyword = keyword
        self.count = count

    def collect_posts(self) -> list:
        self._log(f"[搜索] 关键词：{self.keyword}，目标数量：{self.count}")

        posts: list = []
        seen_ids: set = set()
        after: str = ""

        while len(posts) < self.count:
            params = {
                "q":      self.keyword,
                "sort":   "relevance",
                "type":   "link",
                "limit":  min(100, self.count - len(posts)),
            }
            if after:
                params["after"] = after

            data = self._get(f"{BASE_URL}/search.json", params=params)
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
                self._log(f"  [{len(posts):02d}] r/{post['subreddit']}  {post['title'][:50]}")

            after = data.get("data", {}).get("after", "")
            if not after:
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
