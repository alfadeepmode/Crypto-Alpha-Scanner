"""F3: FutureSimulator cost engine tests."""

import pytest
from agents.future_simulator import FutureSimulator, SimulationResult
from agents.decision_agent import DecisionAgent
from models.schemas import AlphaSignal, TokenData


def _make_decision(tmp_config, action="buy", confidence=72.0, risk=30.0, price=100.0):
    token = TokenData(
        address="BTC", symbol="BTC", name="BTC", network="binance",
        price_usd=price, liquidity_usd=1_000_000.0, volume_24h=1_000_000.0,
        is_verified=True,
    )
    signal = AlphaSignal(
        token=token, signal_type="test",
        confidence=confidence, risk_score=risk,
        action=action, reasoning="",
    )
    if action in {"sell", "long_exit"}:
        signal.risk_score = 75.0
    return DecisionAgent(tmp_config).decide(signal)


# ---------------------------------------------------------------------------
# F3.1  Long/short PnL symmetry
# ---------------------------------------------------------------------------

def test_long_short_pnl_symmetry(tmp_config):
    """Same SL/TP distance on long and short → equal projected_loss and profit."""
    sim = FutureSimulator(tmp_config)

    long_dec = _make_decision(tmp_config, "buy")
    short_dec = _make_decision(tmp_config, "short")

    long_res = sim.simulate(long_dec)
    short_res = sim.simulate(short_dec)

    assert long_res.projected_loss_usd == pytest.approx(short_res.projected_loss_usd, rel=0.05)
    assert long_res.projected_profit_usd == pytest.approx(short_res.projected_profit_usd, rel=0.05)


# ---------------------------------------------------------------------------
# F3.2  Fee model
# ---------------------------------------------------------------------------

def test_fee_model_exact(tmp_config):
    """fee = notional * 2 * taker_fee_bps / 10000."""
    sim = FutureSimulator(tmp_config)
    dec = _make_decision(tmp_config)
    result = sim.simulate(dec)

    expected_fee = dec.amount_usd * 2 * sim.taker_fee_bps / 10_000
    assert result.fee_cost_usd == pytest.approx(expected_fee, rel=1e-6)


# ---------------------------------------------------------------------------
# F3.3  Slippage model
# ---------------------------------------------------------------------------

def test_slippage_model_exact(tmp_config):
    """slippage = notional * 2 * slippage_bps / 10000."""
    sim = FutureSimulator(tmp_config)
    dec = _make_decision(tmp_config)
    result = sim.simulate(dec)

    expected_slip = dec.amount_usd * 2 * sim.slippage_bps / 10_000
    assert result.slippage_cost_usd == pytest.approx(expected_slip, rel=1e-6)


# ---------------------------------------------------------------------------
# F3.4  Funding model
# ---------------------------------------------------------------------------

def test_funding_cost_positive(tmp_config):
    """Funding cost must be > 0 for a live entry decision."""
    sim = FutureSimulator(tmp_config)
    dec = _make_decision(tmp_config)
    result = sim.simulate(dec)
    assert result.funding_cost_usd > 0


# ---------------------------------------------------------------------------
# F3.5  Exit/reduce-only incurs no NEW risk (but costs still apply)
# ---------------------------------------------------------------------------

def test_sell_reduce_only_approved_without_sl_tp(tmp_config):
    """A reduce-only exit with no SL/TP should be approved (position reduction)."""
    sim = FutureSimulator(tmp_config)
    dec = _make_decision(tmp_config, action="sell")
    # remove sl/tp to simulate exit-only scenario
    dec.stop_loss_price = 0.0
    dec.take_profit_price = 0.0
    result = sim.simulate(dec)
    assert result.approved, f"reduce-only exit blocked: {result.reason}"


# ---------------------------------------------------------------------------
# F3.6  Liquidation buffer
# ---------------------------------------------------------------------------

def test_liquidation_buffer_rejection(tmp_config):
    """Stop too close to entry → reject."""
    tmp_config["trading"]["liquidation_buffer_min_pct"] = 10.0
    tmp_config["trading"]["stop_loss_pct"] = 3.0  # only 3% → below 10% buffer
    sim = FutureSimulator(tmp_config)
    dec = _make_decision(tmp_config)
    result = sim.simulate(dec)
    # 3% SL distance < 10% required buffer
    assert not result.approved
    assert "likidasyon" in result.reason.lower() or "tamponu" in result.reason.lower()


def test_liquidation_buffer_ok(tmp_config):
    """Sufficient buffer → approved."""
    sim = FutureSimulator(tmp_config)  # default 8% SL, 6% buffer
    dec = _make_decision(tmp_config)
    result = sim.simulate(dec)
    assert result.liquidation_buffer_pct >= sim.min_liquidation_buffer_pct


# ---------------------------------------------------------------------------
# F3.7  Gate: rejected decision always becomes hold
# ---------------------------------------------------------------------------

def test_rejected_decision_becomes_hold(tmp_config):
    """After approve_batch, any rejected decision has side=hold."""
    tmp_config["trading"]["max_projected_loss_usd"] = 0.0001  # force rejection
    sim = FutureSimulator(tmp_config)
    dec = _make_decision(tmp_config)
    [result] = sim.approve_batch([dec])
    assert result.side == "hold"
    assert result.amount_usd == 0.0


def test_approved_decision_passes_through(tmp_config):
    """Approved decision retains original side."""
    sim = FutureSimulator(tmp_config)
    dec = _make_decision(tmp_config)
    [result] = sim.approve_batch([dec])
    assert result.side == "buy"


# ---------------------------------------------------------------------------
# F3 — net reward/risk net (not gross)
# ---------------------------------------------------------------------------

def test_net_reward_risk_less_than_gross(tmp_config):
    """Net RR must be lower than gross RR because of costs."""
    sim = FutureSimulator(tmp_config)
    dec = _make_decision(tmp_config)
    result = sim.simulate(dec)

    gross_rr = result.projected_profit_usd / result.projected_loss_usd if result.projected_loss_usd > 0 else 0
    assert result.net_reward_risk <= gross_rr + 1e-9, "Net RR should not exceed gross RR"
    assert result.total_cost_usd > 0


def test_zero_price_rejected(tmp_config):
    """Decision with price=0 must be rejected."""
    from models.schemas import TradeDecision
    sim = FutureSimulator(tmp_config)
    token = TokenData(address="X", symbol="X", name="X", network="b", price_usd=0.0, liquidity_usd=1e6, volume_24h=1e6)
    dec = TradeDecision(token=token, side="buy", amount_usd=25.0)
    result = sim.simulate(dec)
    assert not result.approved
