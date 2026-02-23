import asyncio

from config import TWEET_COUNT, REQUEST_PAUSE
from scraper.base import BaseScraper


class KeywordScraper(BaseScraper):
    def __init__(self, keyword: str, count: int = TWEET_COUNT, product: str = "Top", server=None):
        super().__init__(label=keyword, server=server)
        self.keyword = keyword
        self.count = count
        self.product = product  # "Top" or "Latest"

    async def collect_tweets(self) -> list:
        tweets = []
        results = await self.client.search_tweet(self.keyword, self.product, count=20)
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
        await self._log(f"[关键词] \"{self.keyword}\" 搜索到 {len(tweets)} 条推文")
        return tweets
