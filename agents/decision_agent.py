"""Decision Agent - alpha sinyallerini trade kararına çevirir."""

from models.schemas import AlphaSignal, TradeDecision


class DecisionAgent:
    """Sinyal, risk ve portfoy limitlerinden buy/sell/hold karari uretir."""

    def __init__(self, config: dict):
        trading = config.get("trading", {})
        self.enabled = bool(trading.get("enabled", True))
        self.min_buy_confidence = float(trading.get("min_buy_confidence", 75))
        self.max_buy_risk = float(trading.get("max_buy_risk", 35))
        self.min_sell_risk = float(trading.get("min_sell_risk", 70))
        self.base_order_usd = float(trading.get("base_order_usd", 25))
        self.max_order_usd = float(trading.get("max_order_usd", 100))
        self.stop_loss_pct = float(trading.get("stop_loss_pct", 8))
        self.take_profit_pct = float(trading.get("take_profit_pct", 18))

    def decide(self, signal: AlphaSignal) -> TradeDecision:
        token = signal.token
        side = "hold"
        amount_usd = 0.0
        reason = "Sinyal trade esigini gecmedi"

        if not self.enabled:
            return TradeDecision(token=token, side="hold", reason="Trading config kapali", source_signal=signal)

        if token.price_usd <= 0:
            return TradeDecision(token=token, side="hold", reason="Fiyat yok, emir uretilemez", source_signal=signal)

        if signal.action == "buy" and signal.confidence >= self.min_buy_confidence and signal.risk_score <= self.max_buy_risk:
            side = "buy"
            confidence_multiplier = max(0.5, min(signal.confidence / 100, 1.0))
            amount_usd = min(self.base_order_usd * confidence_multiplier, self.max_order_usd)
            reason = f"AL sinyali: guven {signal.confidence:.0f}, risk {signal.risk_score:.0f}"
        elif signal.action == "sell" or signal.risk_score >= self.min_sell_risk:
            side = "sell"
            amount_usd = self.base_order_usd
            reason = f"SAT/risk sinyali: guven {signal.confidence:.0f}, risk {signal.risk_score:.0f}"

        stop_loss = 0.0
        take_profit = 0.0
        if side == "buy":
            stop_loss = token.price_usd * (1 - self.stop_loss_pct / 100)
            take_profit = token.price_usd * (1 + self.take_profit_pct / 100)

        return TradeDecision(
            token=token,
            side=side,
            amount_usd=round(amount_usd, 2),
            confidence=signal.confidence,
            risk_score=signal.risk_score,
            reason=reason,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            source_signal=signal,
        )

    def decide_batch(self, signals: list[AlphaSignal]) -> list[TradeDecision]:
        return [self.decide(signal) for signal in signals]
