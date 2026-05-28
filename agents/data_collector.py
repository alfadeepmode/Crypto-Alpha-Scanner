"""Data Collector Agent - Çeşitli kaynaklardan veri toplar"""

from tools.dex_screener import DexScreenerTool
from tools.etherscan import EtherscanTool
from tools.reddit_scraper import RedditScraperTool
from tools.whale_alert import WhaleAlertTool
from models.schemas import TokenData, WhaleMove, SocialSignal


class DataCollectorAgent:
    """Tüm kaynaklardan veri toplama ajanı"""

    def __init__(self):
        self.dex = DexScreenerTool()
        self.etherscan = EtherscanTool()
        self.reddit = RedditScraperTool()
        self.whale_alert = WhaleAlertTool()

    def collect_all(self) -> dict:
        """Tüm kaynaklardan veri topla"""
        print("[DataCollector] Veri toplanıyor...")

        trending = self._safe_collect("trend token", self.dex.get_trending)
        print(f"  → {len(trending)} trend token bulundu")

        new_tokens = self._safe_collect("yeni token", lambda: self.dex.get_new_pairs("ethereum"))
        print(f"  → {len(new_tokens)} yeni token bulundu")

        whale_moves = self._safe_collect("balina hareketi", self.etherscan.get_whale_transfers)
        print(f"  → {len(whale_moves)} balina hareketi bulundu")

        reddit_signals = self._safe_collect("Reddit sinyali", lambda: self.reddit.search_crypto("crypto alpha"))
        print(f"  → {len(reddit_signals)} Reddit sinyali bulundu")

        return {
            "trending": trending,
            "new_tokens": new_tokens,
            "whale_moves": whale_moves,
            "reddit_signals": reddit_signals,
            "total_tokens": len(trending) + len(new_tokens),
        }

    def _safe_collect(self, label: str, fn):
        try:
            result = fn()
        except Exception as exc:
            print(f"[DataCollector] {label} kaynağı hata verdi: {exc}")
            return []
        if result is None:
            return []
        if not isinstance(result, list):
            print(f"[DataCollector] {label} beklenmeyen veri tipi: {type(result).__name__}")
            return []
        return result

    def summary(self, data: dict) -> str:
        """Toplanan verinin özet metni"""
        return f"""VERİ TOPLAMA RAPORU:
• Trend Token: {len(data['trending'])}
• Yeni Token: {len(data['new_tokens'])}
• Balina Hareketi: {len(data['whale_moves'])}
• Reddit Sinyali: {len(data['reddit_signals'])}
• Toplam Taranan: {data['total_tokens']}
"""
