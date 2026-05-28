"""Filter Agent - Toplanan veriyi filtreler ve zenginleştirir"""

from models.schemas import TokenData, WhaleMove, SocialSignal
import yaml
import os


class FilterAgent:
    """Verileri filtreleme ve ön işleme ajanı"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)

    def _load_config(self, path: str) -> dict:
        try:
            with open(path) as f:
                return yaml.safe_load(f)
        except:
            return {}

    def filter_tokens(self, tokens: list[TokenData]) -> list[TokenData]:
        """Token'ları filtrele (düşük likidite olanları at)"""
        min_liquidity = self.config.get("filters", {}).get("min_liquidity_usd", 50000)
        ignore_list = self.config.get("filters", {}).get("ignore_contracts", [])

        filtered = []
        for t in tokens:
            if t.address in ignore_list:
                continue
            if t.liquidity_usd < min_liquidity:
                continue
            filtered.append(t)

        print(f"[Filter] {len(tokens)} → {len(filtered)} token (likidite < ${min_liquidity})")
        return filtered

    def filter_whales(self, whales: list[WhaleMove]) -> list[WhaleMove]:
        """Balina hareketlerini filtrele"""
        min_value = self.config.get("filters", {}).get("min_transfer_usd", 10000)
        filtered = [w for w in whales if w.value_usd >= min_value]
        print(f"[Filter] {len(whales)} → {len(filtered)} balina (min ${min_value})")
        return filtered

    def filter_signals(self, signals: list[SocialSignal]) -> list[SocialSignal]:
        """Sosyal sinyalleri filtrele"""
        filtered = [s for s in signals if len(s.content) > 10]
        print(f"[Filter] {len(signals)} → {len(filtered)} sosyal sinyal")
        return filtered

    def run(self, data: dict) -> dict:
        """Tüm filtrelemeleri uygula"""
        filtered = {
            "trending": self.filter_tokens(data.get("trending", [])),
            "new_tokens": self.filter_tokens(data.get("new_tokens", [])),
            "whale_moves": self.filter_whales(data.get("whale_moves", [])),
            "reddit_signals": self.filter_signals(data.get("reddit_signals", [])),
        }
        return filtered
