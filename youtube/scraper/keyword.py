"""
KeywordScraper：关键词搜索模式
"""

import os

from utils import ensure_dir, save_json, save_csv
from .base import BaseScraper


class KeywordScraper(BaseScraper):
    def __init__(self, keyword: str, count: int, download_videos: bool = False, server=None):
        super().__init__(keyword, download_videos=download_videos, server=server)
        self.keyword = keyword
        self.count   = count

    def collect_videos(self) -> list:
        self._log(f"[搜索] 关键词：{self.keyword}，目标数量：{self.count}")
        self._log("  正在获取搜索结果...")

        # 先用 flat=True 快速拿到视频 ID 列表
        search_url = f"ytsearch{self.count}:{self.keyword}"
        items = self._fetch_info_list(search_url, flat=True)

        videos = []
        for d in items[:self.count]:
            vid = d.get("id") or d.get("url", "").split("v=")[-1].split("&")[0]
            if not vid:
                continue
            # 逐个获取完整详情（含播放量）
            self._log(f"  [{len(videos)+1:02d}/{self.count}] 获取详情...", end="\r")
            full = self._fetch_info(f"https://www.youtube.com/watch?v={vid}")
            video = self._parse_video(full if full else d)
            if not video["video_id"]:
                video["video_id"] = vid
                video["url"] = f"https://www.youtube.com/watch?v={vid}"
            videos.append(video)
            self._log(f"  [{len(videos):02d}] {video['channel_title']}  {video['title'][:50]}")

        self._log(f"\n共收集 {len(videos)} 个视频\n")
        self.videos = videos
        return videos

    def run(self):
        videos = self.collect_videos()
        save_json(videos, os.path.join(self.run_dir, "videos.json"))
        save_csv(videos, os.path.join(self.run_dir, "videos.csv"))

        comments_dir = os.path.join(self.run_dir, "comments")
        ensure_dir(comments_dir)

        for idx, video in enumerate(videos, 1):
            self._log(f"\n── [{idx}/{len(videos)}] ", end="")
            comments = self.scrape_comments(video)
            self.all_comments.extend(comments)
            if comments:
                save_json(comments, os.path.join(comments_dir, f"{video['video_id']}.json"))
            if self.download_videos:
                self._download_video(video)

        self._save_summary()
