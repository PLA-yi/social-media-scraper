#!/usr/bin/env python3
"""
YouTube 数据爬虫 — 入口
"""

from typing import Optional

from config import VIDEO_COUNT
from scraper import KeywordScraper, ChannelScraper


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _ask_positive_int(prompt: str, default: int = None) -> Optional[int]:
    val = _ask(prompt)
    if not val and default is not None:
        return default
    if val.isdigit() and int(val) > 0:
        return int(val)
    print("  请输入正整数，退出。")
    return None


def main():
    print("=" * 52)
    print("  YouTube 数据爬虫")
    print("=" * 52)

    dl_ans = _ask("\n是否同时下载视频素材？(y/n)：").lower()
    download_videos = dl_ans in ("y", "yes")
    if download_videos:
        print("  已开启视频下载，视频将保存至输出目录的 videos_media/ 文件夹")

    print("\n请选择采集模式：")
    print("  1. 关键词搜索视频")
    print("  2. 频道 / 博主主页采集")
    mode = _ask("\n请输入模式（1/2）：")

    if mode == "1":
        keyword = _ask("请输入搜索关键词：")
        if not keyword:
            print("关键词不能为空，退出。")
            return
        count = _ask_positive_int(
            f"请输入采集视频数量（直接回车默认 {VIDEO_COUNT}）：", default=VIDEO_COUNT
        )
        if count is None:
            return
        KeywordScraper(keyword, count, download_videos=download_videos).run()

    elif mode == "2":
        print("\n支持格式：")
        print("  @username              — YouTube 用户名")
        print("  UCxxxxxxxxxxxxxxxxxxxxxx — 频道 ID")
        print("  https://www.youtube.com/@username")
        print("  https://www.youtube.com/channel/UCxxxxxx")
        channel_input = _ask("请输入频道链接或用户名：")
        if not channel_input:
            print("输入不能为空，退出。")
            return

        print("\n排序方式：")
        print("  1. 最新发布（date）")
        print("  2. 最多播放（viewCount）")
        print("  3. 相关度（relevance）")
        sub = _ask("请选择（1/2/3）：")
        sort_map = {"1": "date", "2": "viewCount", "3": "relevance"}
        if sub not in sort_map:
            print("无效选择，退出。")
            return
        sort_mode = sort_map[sub]

        count = _ask_positive_int(
            f"请输入采集数量（直接回车默认 {VIDEO_COUNT}）：", default=VIDEO_COUNT
        )
        if count is None:
            return

        ChannelScraper(channel_input, sort_mode, count, download_videos=download_videos).run()

    else:
        print("无效选择，退出。")


if __name__ == "__main__":
    main()
