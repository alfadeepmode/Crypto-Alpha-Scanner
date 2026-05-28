import httpx
import os
from typing import Optional
from models.schemas import WhaleMove, TokenData
from datetime import datetime


class EtherscanTool:
    """Etherscan API ile on-chain veri çeker"""

    BASE_URL = "https://api.etherscan.io/api"

    def __init__(self):
        self.api_key = os.getenv("ETHERSCAN_API_KEY", "")

    def get_whale_transfers(self, min_value_eth: float = 100) -> list[WhaleMove]:
        """Büyük transferleri tara (balina hareketleri)"""
        if not self.api_key:
            print("[Etherscan] API anahtarı yok")
            return []

        try:
            resp = httpx.get(self.BASE_URL, params={
                "module": "account",
                "action": "tokentx",
                "sort": "desc",
                "offset": 50,
                "apikey": self.api_key,
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            whales = []
            for tx in data.get("result", []):
                value_eth = float(tx.get("value", 0)) / 10 ** 18
                if value_eth >= min_value_eth:
                    whales.append(WhaleMove(
                        tx_hash=tx.get("hash", ""),
                        token_address=tx.get("contractAddress", ""),
                        token_symbol=tx.get("tokenSymbol", ""),
                        from_address=tx.get("from", ""),
                        to_address=tx.get("to", ""),
                        value_usd=float(tx.get("value", 0)) / 10 ** 18 * 2000,  # eth * 2000
                        network="ethereum",
                        timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                    ))
            return whales
        except Exception as e:
            print(f"[Etherscan] Whale transfer hatası: {e}")
            return []

    def get_token_info(self, address: str) -> Optional[TokenData]:
        """Token kontrat bilgilerini al"""
        if not self.api_key:
            return None
        try:
            resp = httpx.get(self.BASE_URL, params={
                "module": "token",
                "action": "tokeninfo",
                "contractaddress": address,
                "apikey": self.api_key,
            }, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {})
            if not result or isinstance(result, str):
                return None
            return TokenData(
                address=address,
                symbol=result.get("symbol", ""),
                name=result.get("name", ""),
                network="ethereum",
                holders=int(result.get("holderCount", 0)),
                is_verified=True,
            )
        except Exception as e:
            print(f"[Etherscan] Token info hatası: {e}")
            return None
