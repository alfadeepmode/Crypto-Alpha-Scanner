import httpx
import os
from typing import Optional
from models.schemas import SocialSignal


class RedditScraperTool:
    """Reddit'ten kripto ile ilgili gönderileri toplar"""

    def __init__(self):
        self.client_id = os.getenv("REDDIT_CLIENT_ID", "")
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        self.user_agent = os.getenv("REDDIT_USER_AGENT", "CryptoAlphaScanner/1.0")

    def get_hot_posts(self, subreddit: str = "CryptoCurrency", limit: int = 10) -> list[SocialSignal]:
        """Belirtilen subreddit'teki popüler gönderileri al"""
        try:
            headers = {"User-Agent": self.user_agent}
            url = f"https://www.reddit.com/r/{subreddit}/hot.json"
            resp = httpx.get(url, headers=headers, params={"limit": limit}, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            signals = []
            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                signals.append(SocialSignal(
                    source="reddit",
                    content=p.get("title", ""),
                    engagement=p.get("score", 0),
                    url=f"https://reddit.com{p.get('permalink', '')}",
                ))
            return signals
        except Exception as e:
            print(f"[Reddit] Hata: {e}")
            return []

    def search_crypto(self, query: str = "crypto alpha signal", limit: int = 10) -> list[SocialSignal]:
        """Kripto ile ilgili arama yap"""
        try:
            headers = {"User-Agent": self.user_agent}
            url = "https://www.reddit.com/search.json"
            resp = httpx.get(url, headers=headers, params={"q": query, "limit": limit, "sort": "new"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            signals = []
            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                signals.append(SocialSignal(
                    source="reddit",
                    content=p.get("title", ""),
                    engagement=p.get("score", 0),
                    url=f"https://reddit.com{p.get('permalink', '')}",
                ))
            return signals
        except Exception as e:
            print(f"[Reddit] Search hatası: {e}")
            return []
