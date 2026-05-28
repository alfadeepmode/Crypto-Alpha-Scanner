import httpx
from typing import Optional
from models.schemas import TokenData


class DexScreenerTool:
    """DexScreener API ile token verilerini çeker"""

    BASE_URL = "https://api.dexscreener.com/latest/dex"

    def search_token(self, query: str) -> Optional[TokenData]:
        """Token adı/adresi ile arama yap"""
        try:
            resp = httpx.get(f"{self.BASE_URL}/search", params={"q": query}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
            pair = pairs[0]
            return TokenData(
                address=pair.get("baseToken", {}).get("address", ""),
                symbol=pair.get("baseToken", {}).get("symbol", ""),
                name=pair.get("baseToken", {}).get("name", ""),
                network=pair.get("chainId", ""),
                price_usd=float(pair.get("priceUsd", 0)),
                liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)),
                volume_24h=float(pair.get("volume", {}).get("h24", 0)),
            )
        except Exception as e:
            print(f"[DexScreener] Hata: {e}")
            return None

    def get_trending(self) -> list[TokenData]:
        """Trend token'ları al"""
        try:
            resp = httpx.get(f"{self.BASE_URL}/trending", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            tokens = []
            for pair in data.get("pairs", [])[:10]:
                tokens.append(TokenData(
                    address=pair.get("baseToken", {}).get("address", ""),
                    symbol=pair.get("baseToken", {}).get("symbol", ""),
                    name=pair.get("baseToken", {}).get("name", ""),
                    network=pair.get("chainId", ""),
                    price_usd=float(pair.get("priceUsd", 0)),
                    liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)),
                    volume_24h=float(pair.get("volume", {}).get("h24", 0)),
                ))
            return tokens
        except Exception as e:
            print(f"[DexScreener] Trending hatası: {e}")
            return []

    def get_new_pairs(self, chain: str = "ethereum") -> list[TokenData]:
        """Yeni token çiftlerini al"""
        try:
            resp = httpx.get(f"{self.BASE_URL}/pairs/{chain}", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            tokens = []
            for pair in data.get("pairs", [])[:10]:
                tokens.append(TokenData(
                    address=pair.get("baseToken", {}).get("address", ""),
                    symbol=pair.get("baseToken", {}).get("symbol", ""),
                    name=pair.get("baseToken", {}).get("name", ""),
                    network=pair.get("chainId", ""),
                    price_usd=float(pair.get("priceUsd", 0)),
                    liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)),
                    volume_24h=float(pair.get("volume", {}).get("h24", 0)),
                ))
            return tokens
        except Exception as e:
            print(f"[DexScreener] New pairs hatası: {e}")
            return []
