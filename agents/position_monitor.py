"""Position Monitor — open position SL/TP enforcement.

Bu modül paper ve live modda açık pozisyonları periyodik olarak kontrol eder.
Fiyat SL veya TP seviyesini geçtiğinde otomatik kapanış sinyali üretir.
Bu sinyaller OrchestrationAgent'a beslenerek reduce-only çıkış emrine dönüştürülür.
"""

from __future__ import annotations

from models.schemas import AlphaSignal, TokenData
from tools.portfolio import PositionStore


class PositionMonitor:
    """Checks open positions against current prices and generates exit signals."""

    def __init__(self, config: dict):
        self.config = config
        self.position_store = PositionStore(config)
        trading = config.get("trading", {})
        self.stop_loss_pct = float(trading.get("stop_loss_pct", 8.0))
        self.take_profit_pct = float(trading.get("take_profit_pct", 18.0))

    def check_exits(self, current_prices: dict[str, float]) -> list[AlphaSignal]:
        """Return exit AlphaSignals for any position where price crossed SL or TP.

        Args:
            current_prices: mapping of symbol → current market price.

        Returns:
            List of AlphaSignal with action='sell' (long exit) or 'short_exit'.
        """
        signals: list[AlphaSignal] = []
        state = self.position_store.load()

        for pos in state.get("positions", {}).values():
            symbol = str(pos.get("symbol", ""))
            price = current_prices.get(symbol)
            if price is None or price <= 0:
                continue

            position_side = str(pos.get("position_side", "long"))
            avg_entry = float(pos.get("avg_entry_price", 0.0))
            qty = float(pos.get("qty", 0.0))

            if qty <= 0 or avg_entry <= 0:
                continue

            sl_price, tp_price = self._get_sl_tp(pos, avg_entry, position_side)

            exit_action, exit_reason = self._check_trigger(
                price, sl_price, tp_price, position_side
            )

            if exit_action:
                token = TokenData(
                    address=symbol, symbol=symbol, name=symbol,
                    network="", price_usd=price,
                    liquidity_usd=1_000_000.0, volume_24h=1_000_000.0,
                )
                signal = AlphaSignal(
                    token=token,
                    signal_type="position_monitor",
                    confidence=90.0,
                    risk_score=80.0,
                    action=exit_action,
                    reasoning=exit_reason,
                )
                signals.append(signal)

        return signals

    def get_open_positions(self) -> list[dict]:
        """Return list of open position dicts (qty > 0)."""
        state = self.position_store.load()
        return [
            pos for pos in state.get("positions", {}).values()
            if float(pos.get("qty", 0)) > 0
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_sl_tp(self, pos: dict, avg_entry: float, position_side: str) -> tuple[float, float]:
        """Retrieve stored SL/TP or compute from config defaults."""
        sl = float(pos.get("stop_loss_price", 0.0))
        tp = float(pos.get("take_profit_price", 0.0))

        if sl <= 0:
            if position_side == "long":
                sl = avg_entry * (1.0 - self.stop_loss_pct / 100)
            else:
                sl = avg_entry * (1.0 + self.stop_loss_pct / 100)

        if tp <= 0:
            if position_side == "long":
                tp = avg_entry * (1.0 + self.take_profit_pct / 100)
            else:
                tp = avg_entry * (1.0 - self.take_profit_pct / 100)

        return sl, tp

    def _check_trigger(
        self, price: float, sl_price: float, tp_price: float, position_side: str
    ) -> tuple[str, str]:
        """Return (exit_action, reason) if SL/TP triggered, else ("", "")."""
        if position_side == "long":
            if sl_price > 0 and price <= sl_price:
                return "sell", f"LONG Stop-loss: fiyat {price:.6g} <= SL {sl_price:.6g}"
            if tp_price > 0 and price >= tp_price:
                return "sell", f"LONG Take-profit: fiyat {price:.6g} >= TP {tp_price:.6g}"
        elif position_side == "short":
            if sl_price > 0 and price >= sl_price:
                return "short_exit", f"SHORT Stop-loss: fiyat {price:.6g} >= SL {sl_price:.6g}"
            if tp_price > 0 and price <= tp_price:
                return "short_exit", f"SHORT Take-profit: fiyat {price:.6g} <= TP {tp_price:.6g}"
        return "", ""
