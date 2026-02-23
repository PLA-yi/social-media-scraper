"""
ChannelScraper：频道 / 博主主页采集模式
"""

import os
import re

from utils import ensure_dir, save_json, save_csv
from .base import BaseScraper


class ChannelScraper(BaseScraper):
    def __init__(self, channel_input: str, sort_mode: str, count: int,
                 download_videos: bool = False, server=None):
        self.sort_mode = sort_mode
        self.count     = count
        self.channel_url, slug = self._parse_input(channel_input)
        super().__init__(slug, download_videos=download_videos, server=server)

    @staticmethod
    def _parse_input(raw: str):
        """
        解析多种频道输入格式，返回 (yt-dlp 可用的 URL, 用于命名输出目录的 slug)。
        支持：
          @username
          https://www.youtube.com/@username
          https://www.youtube.com/channel/UCxxxx
          UCxxxx（频道 ID）
          https://www.youtube.com/c/name
          https://www.youtube.com/user/name
        """
        raw = raw.strip()

        # 已经是完整 URL
        if raw.startswith("http"):
            # 提取 slug 用于目录命名
            m = re.search(r"youtube\.com/(?:@|channel/|c/|user/)([\w.-]+)", raw)
            slug = m.group(1) if m else "channel"
            # 确保 URL 指向视频列表
            base = raw.split("?")[0].rstrip("/")
            if not base.endswith("/videos"):
                base += "/videos"
            return base, slug

        # @username
        if raw.startswith("@"):
            slug = raw.lstrip("@")
            return f"https://www.youtube.com/{raw}/videos", slug

        # UCxxxx 频道 ID
        if re.match(r"UC[\w-]{20,}", raw):
            return f"https://www.youtube.com/channel/{raw}/videos", raw[:12]

        # 其他（当 @username 处理）
        slug = raw.lstrip("@")
        return f"https://www.youtube.com/@{slug}/videos", slug

    def collect_videos(self) -> list:
        sort_label = {
            "date":       "最新发布",
            "viewCount":  "最多播放",
            "relevance":  "相关度",
        }.get(self.sort_mode, self.sort_mode)
        self._log(f"[采集] {self.channel_url} — {sort_label} 前 {self.count} 个视频")

        # yt-dlp 排序参数
        extra_args = ["--playlist-end", str(self.count)]
        if self.sort_mode == "viewCount":
            # yt-dlp 暂不支持直接按播放量排序频道列表，改用 /videos?view=0（最多播放）
            url = self.channel_url.replace("/videos", "/videos?view=0&sort=p")
        elif self.sort_mode == "date":
            url = self.channel_url
        else:
            url = self.channel_url

        items = self._fetch_info_list(url, flat=True)

        # flat=True 时只有基本信息，需要逐个获取详情以拿到播放量
        videos = []
        for d in items[:self.count]:
            vid = d.get("id") or d.get("url", "").split("v=")[-1]
            if not vid:
                continue
            # 获取完整详情
            full = self._fetch_info(f"https://www.youtube.com/watch?v={vid}")
            if full:
                video = self._parse_video(full)
            else:
                video = self._parse_video(d)
                video["video_id"] = vid
                video["url"] = f"https://www.youtube.com/watch?v={vid}"
            if not video["video_id"]:
                continue
            videos.append(video)
            self._log(f"  [{len(videos):02d}] {video['title'][:55]}  ({video['view_count']:,} 播放)")

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
