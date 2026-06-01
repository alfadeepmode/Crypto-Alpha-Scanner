"""F2: Signal semantics — futures lifecycle contract tests.

Verifies that LONG/SHORT/LONG_EXIT/SHORT_EXIT are never lost in translation
between TradingView webhook → DecisionAgent → PositionStore.
"""

import pytest
from agents.decision_agent import DecisionAgent
from models.schemas import AlphaSignal, TokenData
from tradingview_webhook import normalize_signal_side


# ---------------------------------------------------------------------------
# F2.1  normalize_signal_side — full table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("long",       ("buy", "LONG")),
    ("buy",        ("buy", "LONG")),
    ("LONG",       ("buy", "LONG")),
    ("BUY",        ("buy", "LONG")),
    ("short",      ("short", "SHORT")),
    ("SHORT",      ("short", "SHORT")),
    ("sell",       ("sell", "LONG_EXIT")),
    ("SELL",       ("sell", "LONG_EXIT")),
    ("long_exit",  ("sell", "LONG_EXIT")),
    ("LONG_EXIT",  ("sell", "LONG_EXIT")),
    ("short_exit", ("short_exit", "SHORT_EXIT")),
    ("SHORT_EXIT", ("short_exit", "SHORT_EXIT")),
    ("exit",       ("short_exit", "SHORT_EXIT")),
    ("EXIT",       ("short_exit", "SHORT_EXIT")),
    ("unknown",    ("watch", "HOLD")),
    ("",           ("watch", "HOLD")),
    ("GARBAGE",    ("watch", "HOLD")),
])
def test_normalize_signal_side_full_table(raw, expected):
    result = normalize_signal_side(raw)
    assert result == expected, f"normalize_signal_side({raw!r}) = {result}, expected {expected}"


def test_normalize_is_deterministic():
    """Same input always produces same output."""
    for raw in ("long", "short", "sell", "short_exit"):
        assert normalize_signal_side(raw) == normalize_signal_side(raw)


# ---------------------------------------------------------------------------
# F2.2  DecisionAgent — four lifecycle sides
# ---------------------------------------------------------------------------

def _token(price: float = 100.0) -> TokenData:
    return TokenData(
        address="BTC", symbol="BTC", name="BTC",
        network="binance", price_usd=price,
        liquidity_usd=1_000_000.0, volume_24h=1_000_000.0, is_verified=True,
    )


def _signal(action: str, confidence: float = 72.0, risk: float = 30.0) -> AlphaSignal:
    return AlphaSignal(
        token=_token(), signal_type="test",
        confidence=confidence, risk_score=risk,
        action=action, reasoning="test",
    )


@pytest.mark.parametrize("action,exp_side,exp_signal_side,exp_position_side,exp_reduce_only", [
    ("buy",        "buy",  "LONG",       "long",  False),
    ("long",       "buy",  "LONG",       "long",  False),
    ("short",      "sell", "SHORT",      "short", False),
    ("sell",       "sell", "LONG_EXIT",  "long",  True),
    ("long_exit",  "sell", "LONG_EXIT",  "long",  True),
    ("short_exit", "buy",  "SHORT_EXIT", "short", True),
])
def test_decision_agent_lifecycle(tmp_config, action, exp_side, exp_signal_side, exp_position_side, exp_reduce_only):
    agent = DecisionAgent(tmp_config)
    signal = _signal(action, confidence=72.0, risk=30.0)
    if action in {"sell", "long_exit"}:
        signal.confidence = 50.0
        signal.risk_score = 72.0  # triggers sell path via min_sell_risk
    decision = agent.decide(signal)

    assert decision.side == exp_side, f"action={action}: side={decision.side} expected={exp_side}: {decision.reason}"
    assert getattr(decision, "signal_side", None) == exp_signal_side, (
        f"action={action}: signal_side={getattr(decision,'signal_side',None)} expected={exp_signal_side}"
    )
    assert getattr(decision, "position_side", None) == exp_position_side
    assert bool(getattr(decision, "reduce_only", False)) == exp_reduce_only


def test_short_not_lost_as_plain_sell(tmp_config):
    """SHORT must not silently become LONG_EXIT."""
    agent = DecisionAgent(tmp_config)
    decision = agent.decide(_signal("short", confidence=72.0, risk=30.0))
    assert getattr(decision, "signal_side", "") == "SHORT"
    assert getattr(decision, "position_side", "") == "short"
    assert not getattr(decision, "reduce_only", True)


def test_short_exit_not_lost_as_watch(tmp_config):
    """SHORT_EXIT must not silently become HOLD."""
    agent = DecisionAgent(tmp_config)
    decision = agent.decide(_signal("short_exit", confidence=72.0, risk=30.0))
    assert getattr(decision, "signal_side", "") == "SHORT_EXIT"
    assert decision.side == "buy"
    assert getattr(decision, "reduce_only", False) is True


# ---------------------------------------------------------------------------
# F2.3 / F2.4  Long & short lifecycle in PositionStore
# ---------------------------------------------------------------------------

def test_long_lifecycle_pnl(tmp_config):
    """Long entry then exit → realized PnL = (exit - avg_entry) * qty."""
    from tools.portfolio import PositionStore
    from models.schemas import TradeDecision

    store = PositionStore(tmp_config)
    token = _token(100.0)

    # Entry
    entry = TradeDecision(token=token, side="buy", amount_usd=100.0)
    entry.signal_side = "LONG"
    entry.position_side = "long"
    entry.reduce_only = False
    entry.qty = 1.0
    store.apply_execution(entry, "paper")

    pos = store.get("BTC", "long")
    assert pos is not None
    assert abs(pos["qty"] - 1.0) < 1e-9
    assert abs(pos["avg_entry_price"] - 100.0) < 1e-9

    # Exit at 120 → gain = 20; use amount_usd = 1 * 120 = 120 to cover full qty
    exit_token = _token(120.0)
    ex = TradeDecision(token=exit_token, side="sell", amount_usd=120.0)
    ex.signal_side = "LONG_EXIT"
    ex.position_side = "long"
    ex.reduce_only = True
    ex.qty = 1.0
    store.apply_execution(ex, "paper")

    pos2 = store.get("BTC", "long")
    assert pos2 is not None
    assert abs(pos2["realized_pnl_usd"] - 20.0) < 0.01


def test_short_lifecycle_pnl(tmp_config):
    """Short entry then exit → realized PnL = (avg_entry - exit) * qty."""
    from tools.portfolio import PositionStore
    from models.schemas import TradeDecision

    store = PositionStore(tmp_config)
    token = _token(100.0)

    entry = TradeDecision(token=token, side="sell", amount_usd=100.0)
    entry.signal_side = "SHORT"
    entry.position_side = "short"
    entry.reduce_only = False
    entry.qty = 1.0
    store.apply_execution(entry, "paper")

    # Exit at 80 → gain = 20
    exit_token = _token(80.0)
    ex = TradeDecision(token=exit_token, side="buy", amount_usd=100.0)
    ex.signal_side = "SHORT_EXIT"
    ex.position_side = "short"
    ex.reduce_only = True
    ex.qty = 1.0
    store.apply_execution(ex, "paper")

    pos = store.get("BTC", "short")
    assert pos is not None
    assert abs(pos["realized_pnl_usd"] - 20.0) < 0.01


# ---------------------------------------------------------------------------
# F2.5  SL/TP set on entry
# ---------------------------------------------------------------------------

def test_long_entry_sets_sl_tp(tmp_config):
    agent = DecisionAgent(tmp_config)
    signal = _signal("buy", 72.0, 30.0)
    decision = agent.decide(signal)
    price = signal.token.price_usd
    assert decision.stop_loss_price == pytest.approx(price * (1 - 8 / 100), rel=1e-4)
    assert decision.take_profit_price == pytest.approx(price * (1 + 18 / 100), rel=1e-4)


def test_short_entry_sets_inverted_sl_tp(tmp_config):
    agent = DecisionAgent(tmp_config)
    signal = _signal("short", 72.0, 30.0)
    decision = agent.decide(signal)
    price = signal.token.price_usd
    assert decision.stop_loss_price == pytest.approx(price * (1 + 8 / 100), rel=1e-4)
    assert decision.take_profit_price == pytest.approx(price * (1 - 18 / 100), rel=1e-4)
