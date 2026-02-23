#!/usr/bin/env python3
"""
TikTok 数据爬虫 — 入口
"""

import asyncio
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional

from tiktok.config import VIDEO_COUNT
from tiktok.scraper import KeywordScraper, BloggerScraper


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _ask_positive_int(prompt: str) -> Optional[int]:
    val = _ask(prompt)
    if val.isdigit() and int(val) > 0:
        return int(val)
    print("  请输入正整数，退出。")
    return None


def main():
    print("=" * 52)
    print("  TikTok 数据爬虫")
    print("=" * 52)

    dl_ans = _ask("\n是否同时下载视频素材？(y/n)：").lower()
    download_videos = dl_ans in ("y", "yes", "是")
    if download_videos:
        print("  已开启视频下载，视频将保存至输出目录的 videos_media/ 文件夹")

    print("\n请选择采集模式：")
    print("  1. 关键词搜索视频")
    print("  2. 创作者作品采集")
    mode = _ask("\n请输入模式（1/2）：")

    if mode == "1":
        keyword = _ask("请输入搜索关键词：")
        if not keyword:
            print("关键词不能为空，退出。")
            return
        count = _ask_positive_int(f"请输入采集视频数量（默认 {VIDEO_COUNT}）：")
        if count is None:
            count = VIDEO_COUNT
        asyncio.run(KeywordScraper(keyword, count, download_videos=download_videos).run())

    elif mode == "2":
        print("请粘贴创作者主页链接（支持短链 vm.tiktok.com，也可粘贴含链接的分享文案）：")
        url_input = _ask("链接：")
        if not url_input:
            print("链接不能为空，退出。")
            return
        print("\n采集方式：")
        print("  1. 最新发布的作品")
        print("  2. 流量最高的作品")
        sub = _ask("请选择（1/2）：")
        if sub not in ("1", "2"):
            print("无效选择，退出。")
            return
        count = _ask_positive_int("请输入采集数量：")
        if count is None:
            return
        sort_mode = "latest" if sub == "1" else "hot"
        asyncio.run(BloggerScraper(url_input, sort_mode, count, download_videos=download_videos).run())

    else:
        print("无效选择，退出。")


if __name__ == "__main__":
    main()
