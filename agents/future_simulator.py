"""Future Simulator - paper/research projection gate before execution.

This module is intentionally conservative. It estimates gross risk/reward and then
subtracts estimated friction costs before approving a decision. It does not enable
live trading by itself.
"""

from dataclasses import dataclass
from models.schemas import TradeDecision


@dataclass
class SimulationResult:
    approved: bool
    reason: str
    projected_loss_usd: float = 0.0
    projected_profit_usd: float = 0.0
    risk_units: float = 0.0
    fee_cost_usd: float = 0.0
    slippage_cost_usd: float = 0.0
    funding_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    net_projected_profit_usd: float = 0.0
    net_reward_risk: float = 0.0
    liquidation_buffer_pct: float = 100.0


class FutureSimulator:
    """Run a conservative pre-execution projection for paper/live decisions."""

    def __init__(self, config: dict):
        trading = config.get("trading", {})
        self.max_projected_loss_usd = float(trading.get("max_projected_loss_usd", 15))
        self.min_reward_risk = float(trading.get("min_reward_risk", 1.4))
        self.require_simulation = bool(trading.get("require_future_simulation", True))
        self.taker_fee_bps = float(trading.get("taker_fee_bps", 5.0))
        self.slippage_bps = float(trading.get("slippage_bps", 3.0))
        self.funding_cost_bps = float(trading.get("funding_cost_bps", 1.0))
        self.min_liquidation_buffer_pct = float(trading.get("liquidation_buffer_min_pct", 6.0))

    def simulate(self, decision: TradeDecision) -> SimulationResult:
        if not self.require_simulation:
            return SimulationResult(True, "Future simulation kapali")

        if decision.side == "hold":
            return SimulationResult(True, "Hold karari icin emir yok")

        price = float(decision.token.price_usd or 0)
        amount_usd = float(decision.amount_usd or 0)
        if price <= 0 or amount_usd <= 0:
            return SimulationResult(False, "Fiyat veya emir tutari gecersiz")

        reduce_only = bool(getattr(decision, "reduce_only", False))
        if reduce_only and not decision.stop_loss_price and not decision.take_profit_price:
            return SimulationResult(True, "Reduce-only cikis: yeni pozisyon riski yok")

        if decision.stop_loss_price <= 0 or decision.take_profit_price <= 0:
            return SimulationResult(False, "Stop-loss/take-profit yok")

        qty = amount_usd / price
        is_short = getattr(decision, "position_side", "long") == "short" or getattr(decision, "signal_side", "") == "SHORT"

        if is_short:
            projected_loss = max(0.0, (decision.stop_loss_price - price) * qty)
            projected_profit = max(0.0, (price - decision.take_profit_price) * qty)
            liquidation_buffer_pct = max(0.0, (decision.stop_loss_price - price) / price * 100)
        else:
            projected_loss = max(0.0, (price - decision.stop_loss_price) * qty)
            projected_profit = max(0.0, (decision.take_profit_price - price) * qty)
            liquidation_buffer_pct = max(0.0, (price - decision.stop_loss_price) / price * 100)

        notional_round_trip = amount_usd * 2
        fee_cost = notional_round_trip * self.taker_fee_bps / 10000
        slippage_cost = notional_round_trip * self.slippage_bps / 10000
        funding_cost = amount_usd * self.funding_cost_bps / 10000
        total_cost = fee_cost + slippage_cost + funding_cost
        net_profit = projected_profit - total_cost
        net_reward_risk = net_profit / projected_loss if projected_loss > 0 else 0.0

        decision.expected_fee_usd = round(fee_cost, 6) if hasattr(decision, "expected_fee_usd") else 0.0
        decision.expected_slippage_usd = round(slippage_cost, 6) if hasattr(decision, "expected_slippage_usd") else 0.0
        decision.expected_funding_usd = round(funding_cost, 6) if hasattr(decision, "expected_funding_usd") else 0.0
        decision.expected_total_cost_usd = round(total_cost, 6) if hasattr(decision, "expected_total_cost_usd") else 0.0
        decision.expected_gross_profit_usd = round(projected_profit, 6) if hasattr(decision, "expected_gross_profit_usd") else 0.0
        decision.expected_gross_loss_usd = round(projected_loss, 6) if hasattr(decision, "expected_gross_loss_usd") else 0.0
        decision.expected_net_profit_usd = round(net_profit, 6) if hasattr(decision, "expected_net_profit_usd") else 0.0
        decision.expected_reward_risk = round(net_reward_risk, 6) if hasattr(decision, "expected_reward_risk") else 0.0

        result = SimulationResult(
            True,
            "Future simulation onayi",
            projected_loss,
            projected_profit,
            net_reward_risk,
            fee_cost,
            slippage_cost,
            funding_cost,
            total_cost,
            net_profit,
            net_reward_risk,
            liquidation_buffer_pct,
        )

        if projected_loss > self.max_projected_loss_usd:
            result.approved = False
            result.reason = "Simulasyon reddi: maksimum zarar limiti asildi"
        elif net_profit <= 0:
            result.approved = False
            result.reason = "Simulasyon reddi: maliyet sonrasi beklenen kar negatif"
        elif net_reward_risk < self.min_reward_risk:
            result.approved = False
            result.reason = "Simulasyon reddi: net odul/risk orani dusuk"
        elif liquidation_buffer_pct < self.min_liquidation_buffer_pct:
            result.approved = False
            result.reason = "Simulasyon reddi: stop mesafesi/likidasyon tamponu yetersiz"

        return result

    def approve_batch(self, decisions: list[TradeDecision]) -> list[TradeDecision]:
        approved = []
        for decision in decisions:
            result = self.simulate(decision)
            if not result.approved:
                decision.side = "hold"
                decision.amount_usd = 0.0
                decision.reason = result.reason
                if hasattr(decision, "reject_reason"):
                    decision.reject_reason = result.reason
            else:
                decision.reason = f"{decision.reason} | {result.reason} net_rr={result.net_reward_risk:.2f} cost=${result.total_cost_usd:.4f}"
            approved.append(decision)
        return approved
