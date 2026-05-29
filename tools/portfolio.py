"""Paper/live position state helpers for trade risk checks.

The state file is local JSON and contains no secrets. It lets the scanner reject
reduce-only exit signals when no matching position exists and update paper
positions after execution.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from models.schemas import TradeDecision


class PositionStore:
    """Small JSON-backed position store keyed by uppercase token symbol and side."""

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

    def _key(self, symbol: str, position_side: str = "long") -> str:
        side = (position_side or "long").lower()
        return f"{symbol.upper()}:{side}"

    def get(self, symbol: str, position_side: str = "long") -> dict[str, Any] | None:
        positions = self.load().get("positions", {})
        key = self._key(symbol, position_side)
        if key in positions:
            return positions[key]
        # Backward compatibility with older state files keyed only by symbol.
        if position_side == "long":
            return positions.get(symbol.upper())
        return None

    def has_position(self, symbol: str, position_side: str = "long") -> bool:
        pos = self.get(symbol, position_side)
        return bool(pos and float(pos.get("qty", 0)) > 0)

    def apply_execution(self, decision: TradeDecision, mode: str) -> dict[str, Any]:
        """Update local position state after an executed paper/live decision."""
        data = self.load()
        positions = data.setdefault("positions", {})
        symbol = decision.token.symbol.upper()
        price = float(decision.token.price_usd or 0)
        amount_usd = float(decision.amount_usd or 0)
        if price <= 0 or amount_usd <= 0:
            return data

        signal_side = getattr(decision, "signal_side", "LONG" if decision.side == "buy" else "LONG_EXIT")
        position_side = getattr(decision, "position_side", "short" if signal_side in {"SHORT", "SHORT_EXIT"} else "long")
        key = self._key(symbol, position_side)

        now = datetime.now().isoformat()
        current = positions.get(key, {"symbol": symbol, "position_side": position_side, "qty": 0.0, "cost_usd": 0.0, "realized_pnl_usd": 0.0})
        qty = float(current.get("qty", 0.0))
        cost = float(current.get("cost_usd", 0.0))
        realized = float(current.get("realized_pnl_usd", 0.0))

        entry_signal = signal_side in {"LONG", "SHORT"}
        exit_signal = signal_side in {"LONG_EXIT", "SHORT_EXIT"} or bool(getattr(decision, "reduce_only", False))

        if entry_signal:
            entry_qty = amount_usd / price
            qty += entry_qty
            cost += amount_usd
        elif exit_signal and qty > 0:
            exit_qty = min(qty, amount_usd / price)
            avg_cost = cost / qty if qty else 0.0
            if position_side == "short":
                realized += (avg_cost - price) * exit_qty
            else:
                realized += (price - avg_cost) * exit_qty
            qty -= exit_qty
            cost = max(0.0, cost - avg_cost * exit_qty)

        if qty <= 1e-12:
            qty = 0.0
            cost = 0.0

        positions[key] = {
            "symbol": symbol,
            "position_side": position_side,
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
