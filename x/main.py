import asyncio
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(__file__))

from scraper import KeywordScraper, ProfileScraper
from config import TWEET_COUNT, REPLY_COUNT


def ask(prompt: str, default: str = "") -> str:
    val = input(prompt).strip()
    return val if val else default


async def main():
    print("=" * 50)
    print("  X (Twitter) 内容采集工具")
    print("=" * 50)
    print("请选择采集模式：")
    print("  1. 关键词搜索推文")
    print("  2. 用户主页推文采集")
    mode = ask("请输入模式编号 [1/2]: ", "1")

    if mode == "1":
        keyword = ask("请输入搜索关键词: ")
        if not keyword:
            print("[错误] 关键词不能为空")
            return
        print("排序方式：")
        print("  1. 置顶推文 (Top)")
        print("  2. 最新推文 (Latest)")
        sort_choice = ask("请选择 [1/2]（默认 1）: ", "1")
        product = "Latest" if sort_choice == "2" else "Top"
        count_str = ask(f"采集推文数量（默认 {TWEET_COUNT}）: ", str(TWEET_COUNT))
        count = int(count_str) if count_str.isdigit() else TWEET_COUNT

        scraper = KeywordScraper(keyword=keyword, count=count, product=product)

    elif mode == "2":
        user_input = ask("请输入用户名（支持 @用户名 或完整 URL）: ")
        if not user_input:
            print("[错误] 用户名不能为空")
            return
        count_str = ask(f"采集推文数量（默认 {TWEET_COUNT}）: ", str(TWEET_COUNT))
        count = int(count_str) if count_str.isdigit() else TWEET_COUNT

        scraper = ProfileScraper(user_input=user_input, count=count)

    else:
        print("[错误] 无效模式")
        return

    print(f"\n[配置] 每条推文最多采集 {REPLY_COUNT} 条回复")
    print("[开始] 正在连接 X...\n")
    try:
        await scraper.run()
    except FileNotFoundError as e:
        print(f"\n{e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
