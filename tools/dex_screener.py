import httpx
from typing import Any, Optional
from models.schemas import TokenData


class DexScreenerTool:
    """DexScreener API ile token/pair verilerini güvenli biçimde çeker."""

    BASE_URL = "https://api.dexscreener.com"
    SEARCH_PATH = "/latest/dex/search"
    TOKEN_PROFILES_PATH = "/token-profiles/latest/v1"
    TOKEN_PAIRS_PATH = "/token-pairs/v1/{chain_id}/{token_address}"

    def __init__(self, client: Any | None = None, timeout: httpx.Timeout | None = None):
        self.client = client or httpx.Client(
            base_url=self.BASE_URL,
            timeout=timeout or httpx.Timeout(10.0, connect=5.0),
            headers={"Accept": "application/json"},
        )

    def search_token(self, query: str) -> Optional[TokenData]:
        """Token adı/adresi ile arama yap."""
        pairs = self.search_pairs(query, limit=1)
        return pairs[0] if pairs else None

    def search_pairs(self, query: str, limit: int = 10) -> list[TokenData]:
        """Token adı/adresi ile arama yapıp birden fazla pair döndür."""
        query = query.strip()
        if not query:
            return []

        data = self._get_json(self.SEARCH_PATH, params={"q": query})
        return [self._pair_to_token(pair) for pair in self._pairs_from_response(data)[:limit]]

    def get_trending(self) -> list[TokenData]:
        """Trend adayı tokenları al.

        DexScreener resmi API referansında `/latest/dex/trending` endpointi yok.
        Bu metot eski public interface'i korur ve güncel `/latest/dex/search`
        endpointiyle yüksek likiditeli majör arama sonuçlarından güvenli liste üretir.
        """
        tokens: list[TokenData] = []
        seen: set[tuple[str, str]] = set()
        for query in ("BTC", "ETH", "SOL", "BNB", "XRP"):
            for token in self.search_pairs(query, limit=10):
                key = (token.network, token.address or token.symbol)
                if key in seen:
                    continue
                seen.add(key)
                tokens.append(token)
                if len(tokens) >= 10:
                    return tokens
        return tokens

    def get_new_pairs(self, chain: str = "ethereum") -> list[TokenData]:
        """Yeni token profillerinden pair verisi üret.

        Eski `/latest/dex/pairs/{chain}` endpointi resmi referansta yok. Güncel
        profil endpointinden aynı chain'e ait token adresleri alınır, sonra
        `/token-pairs/v1/{chainId}/{tokenAddress}` ile ilk pair okunur.
        """
        tokens: list[TokenData] = []
        wanted_chain = chain.lower().strip()
        for profile in self.get_latest_profiles(limit=50):
            chain_id = str(profile.get("chainId") or "").lower()
            token_address = str(profile.get("tokenAddress") or "").strip()
            if chain_id != wanted_chain or not token_address:
                continue
            tokens.extend(self.get_token_pairs(chain_id, token_address, limit=1))
            if len(tokens) >= 10:
                break
        return tokens

    def get_latest_profiles(self, limit: int = 50) -> list[dict[str, Any]]:
        """Güncel token profillerini güvenli liste olarak döndür."""
        profiles = self._get_json(self.TOKEN_PROFILES_PATH)
        if not isinstance(profiles, list):
            return []
        return [profile for profile in profiles[:limit] if isinstance(profile, dict)]

    def get_token_pairs(self, chain_id: str, token_address: str, limit: int = 3) -> list[TokenData]:
        """Belirli token adresi için pair listesini döndür."""
        chain_id = chain_id.lower().strip()
        token_address = token_address.strip()
        if not chain_id or not token_address:
            return []
        path = self.TOKEN_PAIRS_PATH.format(chain_id=chain_id, token_address=token_address)
        pairs = self._pairs_from_response(self._get_json(path))
        return [self._pair_to_token(pair) for pair in pairs[:limit]]

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any | None:
        try:
            resp = self.client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            print(f"[DexScreener] API hata: {exc}")
            return None

    def _pairs_from_response(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            pairs = data.get("pairs", [])
        elif isinstance(data, list):
            pairs = data
        else:
            return []
        if not isinstance(pairs, list):
            return []
        return [pair for pair in pairs if isinstance(pair, dict)]

    def _pair_to_token(self, pair: dict[str, Any]) -> TokenData:
        base = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        liquidity = pair.get("liquidity") if isinstance(pair.get("liquidity"), dict) else {}
        volume = pair.get("volume") if isinstance(pair.get("volume"), dict) else {}
        return TokenData(
            address=str(base.get("address") or pair.get("pairAddress") or ""),
            symbol=str(base.get("symbol") or ""),
            name=str(base.get("name") or base.get("symbol") or ""),
            network=str(pair.get("chainId") or ""),
            price_usd=self._safe_float(pair.get("priceUsd")),
            liquidity_usd=self._safe_float(liquidity.get("usd")),
            volume_24h=self._safe_float(volume.get("h24")),
        )

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default
