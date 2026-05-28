import httpx
import os
from typing import Optional
from models.schemas import WhaleMove
from datetime import datetime


class WhaleAlertTool:
    """Whale Alert API ile büyük kripto transferlerini izler"""

    BASE_URL = "https://api.whale-alert.io/v1"

    def __init__(self):
        self.api_key = os.getenv("WHALE_ALERT_API_KEY", "")

    def get_recent_transfers(self, min_value_usd: int = 100000) -> list[WhaleMove]:
        """Son büyük transferleri al"""
        if not self.api_key:
            print("[WhaleAlert] API anahtarı yok")
            return []

        try:
            resp = httpx.get(
                f"{self.BASE_URL}/transactions",
                params={"api_key": self.api_key, "min_value": min_value_usd, "limit": 20},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            whales = []
            for tx in data.get("transactions", []):
                whales.append(WhaleMove(
                    tx_hash=tx.get("hash", ""),
                    token_address=tx.get("address", ""),
                    token_symbol=tx.get("symbol", "UNKNOWN"),
                    from_address=tx.get("from", {}).get("address", ""),
                    to_address=tx.get("to", {}).get("address", ""),
                    value_usd=float(tx.get("value_usd", 0)),
                    network=tx.get("blockchain", "unknown"),
                    timestamp=datetime.fromtimestamp(int(tx.get("timestamp", 0))),
                    is_buy="exchange" in tx.get("to", {}).get("owner", "").lower(),
                ))
            return whales
        except Exception as e:
            print(f"[WhaleAlert] Hata: {e}")
            return []
