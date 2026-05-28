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

        # 1. Trend token'lar
        trending = self.dex.get_trending()
        print(f"  → {len(trending)} trend token bulundu")

        # 2. Yeni token'lar
        new_tokens = self.dex.get_new_pairs("ethereum")
        print(f"  → {len(new_tokens)} yeni token bulundu")

        # 3. Balina hareketleri (Etherscan)
        whale_moves = self.etherscan.get_whale_transfers()
        print(f"  → {len(whale_moves)} balina hareketi bulundu")

        # 4. Reddit sinyalleri
        reddit_signals = self.reddit.search_crypto("crypto alpha")
        print(f"  → {len(reddit_signals)} Reddit sinyali bulundu")

        return {
            "trending": trending,
            "new_tokens": new_tokens,
            "whale_moves": whale_moves,
            "reddit_signals": reddit_signals,
            "total_tokens": len(trending) + len(new_tokens),
        }

    def summary(self, data: dict) -> str:
        """Toplanan verinin özet metni"""
        return f"""VERİ TOPLAMA RAPORU:
• Trend Token: {len(data['trending'])}
• Yeni Token: {len(data['new_tokens'])}
• Balina Hareketi: {len(data['whale_moves'])}
• Reddit Sinyali: {len(data['reddit_signals'])}
• Toplam Taranan: {data['total_tokens']}
"""
