"""F1: Contract test — alpha model buy threshold vs DecisionAgent approval.

This test is the regression anchor for the G1 gap (confidence mismatch).
It must stay green to prove the two layers agree on when a buy is approved.
"""

import pytest
from agents.alpha_model import HeuristicAlphaModel
from agents.decision_agent import DecisionAgent
from models.schemas import AlphaSignal, TokenData


def _liquid_token(symbol: str = "BTC", price: float = 100.0) -> TokenData:
    return TokenData(
        address=symbol, symbol=symbol, name=symbol,
        network="binance", price_usd=price,
        liquidity_usd=1_000_000.0, volume_24h=1_000_000.0,
        is_verified=True,
    )


def _illiquid_token() -> TokenData:
    return TokenData(
        address="LOW", symbol="LOW", name="Low",
        network="ethereum", price_usd=0.01,
        liquidity_usd=1_000.0, volume_24h=500.0,
    )


# ---------------------------------------------------------------------------
# Core contract
# ---------------------------------------------------------------------------

def test_alpha_buy_signal_approved_by_decision_agent(tmp_config):
    """When alpha model outputs action='buy', DecisionAgent must also approve (not hold)."""
    model = HeuristicAlphaModel()
    agent = DecisionAgent(tmp_config)

    token = _liquid_token()
    result = model.score(token)

    assert result.action == "buy", (
        f"Alpha model did not produce 'buy' for liquid BTC-like token: action={result.action}"
    )

    signal = AlphaSignal(
        token=token, signal_type="trending",
        confidence=result.confidence,
        risk_score=result.risk_score,
        action=result.action,
        reasoning=result.reasoning,
    )
    decision = agent.decide(signal)

    assert decision.side == "buy", (
        f"DecisionAgent held back an alpha 'buy' signal. "
        f"confidence={result.confidence:.2f} vs min_buy_confidence="
        f"{agent.min_buy_confidence:.2f}. "
        f"Increase model score or lower config threshold (G1 contract mismatch)."
    )


def test_alpha_confidence_gte_decision_threshold(tmp_config):
    """Alpha model max confidence must be >= DecisionAgent min_buy_confidence."""
    model = HeuristicAlphaModel()
    agent = DecisionAgent(tmp_config)

    token = _liquid_token()
    result = model.score(token)

    assert result.confidence >= agent.min_buy_confidence, (
        f"Alpha model peak confidence {result.confidence:.2f} < "
        f"DecisionAgent.min_buy_confidence {agent.min_buy_confidence:.2f}. "
        f"Thresholds are misaligned — fix config or model."
    )


# ---------------------------------------------------------------------------
# Boundary values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("confidence,risk,expected_side", [
    (64.9, 30.0, "hold"),   # just below threshold
    (65.0, 30.0, "buy"),    # exactly at threshold
    (65.1, 30.0, "buy"),    # just above
    (80.0, 35.0, "buy"),    # at risk boundary
    (80.0, 35.1, "hold"),   # over risk limit
    (80.0, 70.0, "sell"),   # high risk → sell/long_exit
])
def test_decision_boundary_values(tmp_config, btc_token, confidence, risk, expected_side):
    agent = DecisionAgent(tmp_config)
    signal = AlphaSignal(
        token=btc_token, signal_type="trending",
        confidence=confidence, risk_score=risk,
        action="buy" if risk < 70 else "sell",
        reasoning="boundary test",
    )
    decision = agent.decide(signal)
    assert decision.side == expected_side, (
        f"conf={confidence} risk={risk} → expected side={expected_side}, got {decision.side}: {decision.reason}"
    )


# ---------------------------------------------------------------------------
# Config-driven single source
# ---------------------------------------------------------------------------

def test_both_layers_use_same_config_threshold(tmp_config):
    """Mutate config threshold; both model and agent should agree."""
    tmp_config["trading"]["min_buy_confidence"] = 90.0  # unreachable by model
    agent = DecisionAgent(tmp_config)
    model = HeuristicAlphaModel()

    token = _liquid_token()
    result = model.score(token)
    signal = AlphaSignal(
        token=token, signal_type="trending",
        confidence=result.confidence, risk_score=result.risk_score,
        action=result.action, reasoning="",
    )
    decision = agent.decide(signal)
    # With threshold=90, model confidence ~72 → should be held
    assert decision.side == "hold", (
        "Expected hold when threshold set above alpha model's peak confidence"
    )


def test_illiquid_token_never_buy(tmp_config):
    """Illiquid / high-risk token should not produce buy at any config."""
    model = HeuristicAlphaModel()
    agent = DecisionAgent(tmp_config)

    token = _illiquid_token()
    result = model.score(token)
    signal = AlphaSignal(
        token=token, signal_type="trending",
        confidence=result.confidence, risk_score=result.risk_score,
        action=result.action, reasoning="",
    )
    decision = agent.decide(signal)
    # Either model doesn't produce buy, or if it does RiskManager would catch it,
    # but at contract level we verify the action is not "buy" for an illiquid token.
    assert result.action != "buy" or decision.side == "hold", (
        "Illiquid token should not pass as buy through decision contract"
    )
