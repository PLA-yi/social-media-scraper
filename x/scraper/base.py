import os
import asyncio
import json
from twikit import Client

from config import OUTPUT_DIR, REPLY_COUNT, REQUEST_PAUSE
from utils import ensure_dir, safe_text, now_str, save_json, save_csv


class BaseScraper:
    def __init__(self, label: str, server=None):
        self.server = server
        self.label = label
        self.run_dir = os.path.join(
            OUTPUT_DIR, f"{safe_text(label)}_{now_str()}"
        )
        ensure_dir(self.run_dir)
        self.client = None
        self.tweets = []
        self.all_replies = []

    async def _log(self, msg: str, end: str = "\n"):
        if self.server and hasattr(self.server, '_log'):
            res = self.server._log(msg)
            if asyncio.iscoroutine(res):
                await res
        else:
            import sys
            sys.stdout.write(str(msg) + end)
            sys.stdout.flush()

    async def _init_client(self):
        cookie_path = os.path.join(OUTPUT_DIR, "cookies.json")
        if not os.path.exists(cookie_path):
            await self._log(f"\n[错误] 未找到 Cookie 文件：{cookie_path}")
            await self._log("请按以下步骤导出：")
            await self._log("  1. 浏览器安装 Cookie-Editor 扩展（作者 cgagnier）")
            await self._log("  2. 打开并登录 x.com")
            await self._log("  3. 点击 Cookie-Editor → Export → Export as JSON")
            await self._log(f"  4. 将内容粘贴保存到：{cookie_path}")

            if self.server:
                msg = ">>> 请保存 Cookie 后继续 ... "
                if hasattr(self.server, 'request_user_intervention'):
                    req_res = self.server.request_user_intervention(msg)
                    if asyncio.iscoroutine(req_res):
                        await req_res
                if hasattr(self.server, 'user_continue_event'):
                    await self.server.user_continue_event.wait()
                    self.server.user_continue_event.clear()
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, input, "  >>> 请保存 Cookie 后按回车继续 ... ")

            if not os.path.exists(cookie_path):
                await self._log(f"[错误] Cookie 文件仍未找到: {cookie_path}")
                raise FileNotFoundError(f"Cookie 文件不存在: {cookie_path}")

        self.client = Client(language='zh-CN')
        await self.client.load_cookies(cookie_path)
        await self._log("[认证] Cookie 加载成功")

    def _tweet_to_dict(self, tweet) -> dict:
        try:
            author = tweet.user.screen_name if tweet.user else ""
            author_name = tweet.user.name if tweet.user else ""
        except Exception:
            author = ""
            author_name = ""
        return {
            "tweet_id":      str(tweet.id),
            "author":        author,
            "author_name":   author_name,
            "text":          safe_text(tweet.full_text or tweet.text),
            "created_at":    tweet.created_at,
            "like_count":    tweet.favorite_count or 0,
            "retweet_count": tweet.retweet_count or 0,
            "reply_count":   tweet.reply_count or 0,
            "quote_count":   tweet.quote_count or 0,
            "url":           f"https://x.com/{author}/status/{tweet.id}",
        }

    async def scrape_replies(self, tweet_dict: dict) -> list:
        tweet_id = tweet_dict["tweet_id"]
        replies_dir = os.path.join(self.run_dir, "replies")
        ensure_dir(replies_dir)

        replies = []
        try:
            tweet = await self.client.get_tweet_by_id(tweet_id)
            results = await tweet.get_replies()
            collected = 0
            while results and collected < REPLY_COUNT:
                for reply in results:
                    if collected >= REPLY_COUNT:
                        break
                    try:
                        author = reply.user.screen_name if reply.user else ""
                        r = {
                            "reply_id":   str(reply.id),
                            "tweet_id":   tweet_id,
                            "author":     author,
                            "text":       safe_text(reply.full_text or reply.text),
                            "created_at": reply.created_at,
                            "like_count": reply.favorite_count or 0,
                            "is_reply":   True,
                        }
                        replies.append(r)
                        collected += 1
                    except Exception:
                        continue
                if collected < REPLY_COUNT:
                    try:
                        results = await results.next()
                        await asyncio.sleep(REQUEST_PAUSE)
                    except Exception:
                        break
        except Exception as e:
            await self._log(f"  [警告] 获取回复失败 {tweet_id}: {e}")

        if replies:
            save_json(replies, os.path.join(replies_dir, f"{tweet_id}.json"))
            await self._log(f"  [回复] {tweet_dict['text'][:40]}... → {len(replies)} 条")
        return replies

    async def _save_summary(self):
        save_json(self.tweets, os.path.join(self.run_dir, "tweets.json"))
        save_csv(self.tweets, os.path.join(self.run_dir, "tweets.csv"))
        if self.all_replies:
            save_json(self.all_replies, os.path.join(self.run_dir, "all_replies.json"))
            save_csv(self.all_replies, os.path.join(self.run_dir, "all_replies.csv"))
        await self._log(f"\n[完成] 推文: {len(self.tweets)}  回复: {len(self.all_replies)}")
        await self._log(f"[目录] {self.run_dir}")

    async def run(self):
        await self._init_client()
        await self._log("[采集] 正在收集推文...")
        self.tweets = await self.collect_tweets()
        await self._log(f"[采集] 共 {len(self.tweets)} 条推文，开始采集回复...")
        for tweet in self.tweets:
            replies = await self.scrape_replies(tweet)
            self.all_replies.extend(replies)
            await asyncio.sleep(REQUEST_PAUSE)
        await self._save_summary()

    async def collect_tweets(self) -> list:
        raise NotImplementedError
