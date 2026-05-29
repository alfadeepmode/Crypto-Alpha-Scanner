"""Risk Manager - trade kararlarini sermaye ve guvenlik limitlerinden gecirir."""

from models.schemas import TradeDecision
from tools.portfolio import PositionStore


class RiskManager:
    """Tek kosuda emir sayisi, tutar ve token kalite limitlerini uygular."""

    def __init__(self, config: dict):
        trading = config.get("trading", {})
        self.max_orders_per_run = int(trading.get("max_orders_per_run", 3))
        self.max_order_usd = float(trading.get("max_order_usd", 100))
        self.min_liquidity_usd = float(trading.get("min_liquidity_usd", 100000))
        self.allow_sells_without_position = bool(trading.get("allow_sells_without_position", False))
        self.allowed_symbols = {s.upper() for s in trading.get("allowed_symbols", ["BTC", "ETH", "SOL", "XRP"])}
        self.position_store = PositionStore(config)

    def approve_batch(self, decisions: list[TradeDecision]) -> list[TradeDecision]:
        approved = []
        order_count = 0

        for decision in decisions:
            if decision.side == "hold":
                approved.append(decision)
                continue

            signal_side = getattr(decision, "signal_side", "")
            position_side = getattr(decision, "position_side", "long")
            reduce_only = bool(getattr(decision, "reduce_only", False))

            if decision.token.symbol.upper() not in self.allowed_symbols:
                approved.append(self._reject(decision, "Sembol trading allowlist disinda"))
                continue

            if order_count >= self.max_orders_per_run:
                approved.append(self._reject(decision, "Kosudaki maksimum emir sayisi asildi"))
                continue

            if decision.amount_usd <= 0 or decision.amount_usd > self.max_order_usd:
                approved.append(self._reject(decision, "Emir tutari risk limitleri disinda"))
                continue

            if signal_side in {"LONG", "SHORT"} and decision.token.liquidity_usd < self.min_liquidity_usd:
                approved.append(self._reject(decision, "Likidite trading icin yetersiz"))
                continue

            if reduce_only and not self.allow_sells_without_position:
                if not self.position_store.has_position(decision.token.symbol, position_side=position_side):
                    approved.append(self._reject(decision, f"{position_side} pozisyon yok; reduce-only emri kapali"))
                    continue

            approved.append(decision)
            order_count += 1

        return approved

    def _reject(self, decision: TradeDecision, reason: str) -> TradeDecision:
        decision.side = "hold"
        decision.amount_usd = 0.0
        decision.reason = f"Risk reddi: {reason}"
        if hasattr(decision, "reject_reason"):
            decision.reject_reason = reason
        return decision
