"""Future Simulator - live emirden once paper projection kapisi."""

from dataclasses import dataclass
from models.schemas import TradeDecision


@dataclass
class SimulationResult:
    approved: bool
    reason: str
    projected_loss_usd: float = 0.0
    projected_profit_usd: float = 0.0
    risk_units: float = 0.0


class FutureSimulator:
    """Karari stop-loss/take-profit ve risk limitleriyle ileriye donuk simule eder."""

    def __init__(self, config: dict):
        trading = config.get("trading", {})
        self.max_projected_loss_usd = float(trading.get("max_projected_loss_usd", 15))
        self.min_reward_risk = float(trading.get("min_reward_risk", 1.4))
        self.require_simulation = bool(trading.get("require_future_simulation", True))

    def simulate(self, decision: TradeDecision) -> SimulationResult:
        if not self.require_simulation:
            return SimulationResult(True, "Future simulation kapali")

        if decision.side == "hold":
            return SimulationResult(True, "Hold karari icin emir yok")

        if decision.side == "sell":
            return SimulationResult(True, "Sell karari pozisyon azaltma olarak kabul edildi")

        price = decision.token.price_usd
        if price <= 0 or decision.amount_usd <= 0:
            return SimulationResult(False, "Fiyat veya emir tutari gecersiz")

        if decision.stop_loss_price <= 0 or decision.take_profit_price <= 0:
            return SimulationResult(False, "Stop-loss/take-profit yok")

        qty = decision.amount_usd / price
        projected_loss = max(0.0, (price - decision.stop_loss_price) * qty)
        projected_profit = max(0.0, (decision.take_profit_price - price) * qty)
        reward_risk = projected_profit / projected_loss if projected_loss else 0.0

        if projected_loss > self.max_projected_loss_usd:
            return SimulationResult(False, "Simulasyon reddi: maksimum zarar limiti asildi", projected_loss, projected_profit, reward_risk)

        if reward_risk < self.min_reward_risk:
            return SimulationResult(False, "Simulasyon reddi: odul/risk orani dusuk", projected_loss, projected_profit, reward_risk)

        return SimulationResult(True, "Future simulation onayi", projected_loss, projected_profit, reward_risk)

    def approve_batch(self, decisions: list[TradeDecision]) -> list[TradeDecision]:
        approved = []
        for decision in decisions:
            result = self.simulate(decision)
            if not result.approved:
                decision.side = "hold"
                decision.amount_usd = 0.0
                decision.reason = result.reason
            else:
                decision.reason = f"{decision.reason} | {result.reason}"
            approved.append(decision)
        return approved
