import re
import asyncio

from config import TWEET_COUNT, REQUEST_PAUSE
from scraper.base import BaseScraper


class ProfileScraper(BaseScraper):
    def __init__(self, user_input: str, count: int = TWEET_COUNT, server=None):
        username = self._parse_input(user_input)
        super().__init__(label=username, server=server)
        self.username = username
        self.count = count

    @staticmethod
    def _parse_input(raw: str) -> str:
        raw = raw.strip()
        # 支持完整 URL：https://x.com/@username 或 https://twitter.com/username
        m = re.search(r'(?:x\.com|twitter\.com)/@?([A-Za-z0-9_]+)', raw)
        if m:
            return m.group(1)
        # 支持 @username
        if raw.startswith('@'):
            return raw[1:]
        return raw

    async def collect_tweets(self) -> list:
        user = await self.client.get_user_by_screen_name(self.username)
        tweets = []
        results = await user.get_tweets('Tweets', count=20)
        while results and len(tweets) < self.count:
            for tweet in results:
                if len(tweets) >= self.count:
                    break
                tweets.append(self._tweet_to_dict(tweet))
            if len(tweets) < self.count:
                try:
                    results = await results.next()
                    await asyncio.sleep(REQUEST_PAUSE)
                except Exception:
                    break
        await self._log(f"[用户] @{self.username} 采集到 {len(tweets)} 条推文")
        return tweets
