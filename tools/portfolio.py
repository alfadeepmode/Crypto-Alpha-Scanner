"""Paper/live position state helpers for trade risk checks.

The state file is local JSON and contains no secrets. It lets the scanner reject
sell signals when no position exists and update paper positions after execution.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from models.schemas import TradeDecision


class PositionStore:
    """Small JSON-backed position store keyed by uppercase token symbol."""

    def __init__(self, config: dict):
        trading = config.get("trading", {})
        default_path = trading.get("position_state_path", "data/positions.json")
        self.path = Path(os.getenv("POSITION_STATE_PATH", default_path))

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"positions": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"positions": {}}
        if not isinstance(data, dict):
            return {"positions": {}}
        data.setdefault("positions", {})
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def get(self, symbol: str) -> dict[str, Any] | None:
        return self.load().get("positions", {}).get(symbol.upper())

    def has_position(self, symbol: str) -> bool:
        pos = self.get(symbol)
        return bool(pos and float(pos.get("qty", 0)) > 0)

    def apply_execution(self, decision: TradeDecision, mode: str) -> dict[str, Any]:
        """Update local position state after an executed buy/sell."""
        data = self.load()
        positions = data.setdefault("positions", {})
        symbol = decision.token.symbol.upper()
        price = float(decision.token.price_usd or 0)
        amount_usd = float(decision.amount_usd or 0)
        if price <= 0 or amount_usd <= 0:
            return data

        now = datetime.now().isoformat()
        current = positions.get(symbol, {"symbol": symbol, "qty": 0.0, "cost_usd": 0.0, "realized_pnl_usd": 0.0})
        qty = float(current.get("qty", 0.0))
        cost = float(current.get("cost_usd", 0.0))
        realized = float(current.get("realized_pnl_usd", 0.0))

        if decision.side == "buy":
            buy_qty = amount_usd / price
            qty += buy_qty
            cost += amount_usd
        elif decision.side == "sell" and qty > 0:
            sell_qty = min(qty, amount_usd / price)
            avg_cost = cost / qty if qty else 0.0
            realized += (price - avg_cost) * sell_qty
            qty -= sell_qty
            cost = max(0.0, cost - avg_cost * sell_qty)

        if qty <= 1e-12:
            qty = 0.0
            cost = 0.0

        positions[symbol] = {
            "symbol": symbol,
            "qty": qty,
            "cost_usd": cost,
            "avg_entry_price": cost / qty if qty else 0.0,
            "last_price": price,
            "realized_pnl_usd": realized,
            "mode": mode,
            "updated_at": now,
        }
        data["updated_at"] = now
        self.save(data)
        return data
