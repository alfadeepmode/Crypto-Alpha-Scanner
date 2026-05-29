"""Decision Agent - alpha sinyallerini trade kararına çevirir."""

from models.schemas import AlphaSignal, TradeDecision


class DecisionAgent:
    """Sinyal, risk ve portfoy limitlerinden buy/sell/hold karari uretir.

    `TradeDecision.side` exchange direction olarak backward-compatible tutulur:
    - long entry  -> buy
    - long exit   -> sell
    - short entry -> sell
    - short exit  -> buy

    Futures anlamı runtime attribute olarak eklenir; mevcut schema kırılmaz.
    """

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
        self.allow_short_entries = bool(trading.get("allow_short_entries", True))

    def decide(self, signal: AlphaSignal) -> TradeDecision:
        token = signal.token
        action = str(signal.action or "watch").lower()
        side = "hold"
        signal_side = "HOLD"
        position_side = "none"
        reduce_only = False
        amount_usd = 0.0
        reason = "Sinyal trade esigini gecmedi"

        if not self.enabled:
            return self._attach_semantics(TradeDecision(token=token, side="hold", reason="Trading config kapali", source_signal=signal), signal_side, position_side, reduce_only)

        if token.price_usd <= 0:
            return self._attach_semantics(TradeDecision(token=token, side="hold", reason="Fiyat yok, emir uretilemez", source_signal=signal), signal_side, position_side, reduce_only)

        if action in {"buy", "long"} and signal.confidence >= self.min_buy_confidence and signal.risk_score <= self.max_buy_risk:
            side = "buy"
            signal_side = "LONG"
            position_side = "long"
            confidence_multiplier = max(0.5, min(signal.confidence / 100, 1.0))
            amount_usd = min(self.base_order_usd * confidence_multiplier, self.max_order_usd)
            reason = f"LONG sinyali: guven {signal.confidence:.0f}, risk {signal.risk_score:.0f}"
        elif action == "short" and self.allow_short_entries and signal.confidence >= self.min_buy_confidence and signal.risk_score <= self.max_buy_risk:
            side = "sell"
            signal_side = "SHORT"
            position_side = "short"
            confidence_multiplier = max(0.5, min(signal.confidence / 100, 1.0))
            amount_usd = min(self.base_order_usd * confidence_multiplier, self.max_order_usd)
            reason = f"SHORT sinyali: guven {signal.confidence:.0f}, risk {signal.risk_score:.0f}"
        elif action in {"sell", "long_exit"} or signal.risk_score >= self.min_sell_risk:
            side = "sell"
            signal_side = "LONG_EXIT"
            position_side = "long"
            reduce_only = True
            amount_usd = self.base_order_usd
            reason = f"LONG EXIT/risk sinyali: guven {signal.confidence:.0f}, risk {signal.risk_score:.0f}"
        elif action == "short_exit":
            side = "buy"
            signal_side = "SHORT_EXIT"
            position_side = "short"
            reduce_only = True
            amount_usd = self.base_order_usd
            reason = f"SHORT EXIT sinyali: guven {signal.confidence:.0f}, risk {signal.risk_score:.0f}"

        stop_loss = 0.0
        take_profit = 0.0
        if signal_side == "LONG":
            stop_loss = token.price_usd * (1 - self.stop_loss_pct / 100)
            take_profit = token.price_usd * (1 + self.take_profit_pct / 100)
        elif signal_side == "SHORT":
            stop_loss = token.price_usd * (1 + self.stop_loss_pct / 100)
            take_profit = token.price_usd * (1 - self.take_profit_pct / 100)

        decision = TradeDecision(
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
        return self._attach_semantics(decision, signal_side, position_side, reduce_only)

    def _attach_semantics(self, decision: TradeDecision, signal_side: str, position_side: str, reduce_only: bool) -> TradeDecision:
        decision.signal_side = signal_side
        decision.order_side = decision.side if decision.side in {"buy", "sell"} else "none"
        decision.position_side = position_side
        decision.reduce_only = reduce_only
        decision.notional_usd = decision.amount_usd
        decision.qty = decision.amount_usd / decision.token.price_usd if decision.token.price_usd > 0 and decision.amount_usd > 0 else 0.0
        decision.reject_reason = ""
        return decision

    def decide_batch(self, signals: list[AlphaSignal]) -> list[TradeDecision]:
        return [self.decide(signal) for signal in signals]
