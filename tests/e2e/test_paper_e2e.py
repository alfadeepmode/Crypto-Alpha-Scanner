"""F12.1: Paper E2E test — full automated trading loop.

Tests the complete pipeline:
  signal → decision → risk → simulation → paper exec → position stored
  → position_monitor → exit signal → paper exit exec → realized PnL

No live orders. No network. Fully offline and deterministic.
"""

import pytest
from copy import deepcopy
from agents.orchestration_agent import OrchestrationAgent
from agents.position_monitor import PositionMonitor
from models.schemas import AlphaSignal, TokenData
from tools.exchange_executor import ExchangeExecutor
from tools.portfolio import PositionStore


def _token(symbol: str = "BTC", price: float = 100.0) -> TokenData:
    return TokenData(
        address=symbol, symbol=symbol, name=symbol,
        network="binance", price_usd=price,
        liquidity_usd=1_000_000.0, volume_24h=1_000_000.0,
        is_verified=True,
    )


def _signal(action: str, symbol: str = "BTC", price: float = 100.0,
            confidence: float = 72.0, risk: float = 30.0) -> AlphaSignal:
    return AlphaSignal(
        token=_token(symbol, price),
        signal_type="e2e_test",
        confidence=confidence,
        risk_score=risk,
        action=action,
        reasoning="e2e test signal",
    )


# ---------------------------------------------------------------------------
# F12.1  Full paper cycle: long entry → position stored → SL/TP monitor → exit
# ---------------------------------------------------------------------------

def test_full_long_cycle(tmp_config):
    """Entry → paper exec → position → TP trigger → exit → realized PnL."""
    orch = OrchestrationAgent(tmp_config)
    monitor = PositionMonitor(tmp_config)
    store = PositionStore(tmp_config)

    # 1. Long entry signal
    entry_signal = _signal("buy", "BTC", price=100.0, confidence=72.0, risk=30.0)
    decision, execution = orch.process_signal(entry_signal)

    assert decision.side == "buy", f"Expected buy, got {decision.side}: {decision.reason}"
    assert execution is not None
    assert execution.status == "executed"
    assert execution.mode == "paper"

    # 2. Position must be recorded
    assert store.has_position("BTC", "long"), "Long position not recorded after entry"

    # 3. Position monitor: price at TP (118+) → exit signal
    tp_price = 100.0 * (1 + tmp_config["trading"]["take_profit_pct"] / 100) + 5.0
    exit_signals = monitor.check_exits({"BTC": tp_price})
    assert len(exit_signals) == 1
    exit_sig = exit_signals[0]
    assert exit_sig.action == "sell"

    # 4. Execute exit
    exit_decision, exit_execution = orch.process_signal(exit_sig)
    assert exit_decision.side == "sell", f"Exit decision was {exit_decision.side}: {exit_decision.reason}"
    assert exit_execution is not None
    assert exit_execution.status == "executed"

    # 5. Realized PnL should be positive (TP > entry)
    pos = store.get("BTC", "long")
    assert pos is not None
    assert pos["realized_pnl_usd"] > 0, f"Expected positive PnL, got {pos['realized_pnl_usd']}"


def test_full_short_cycle(tmp_config):
    """Short entry → position → SL trigger → exit."""
    orch = OrchestrationAgent(tmp_config)
    monitor = PositionMonitor(tmp_config)
    store = PositionStore(tmp_config)

    entry = _signal("short", "ETH", price=100.0, confidence=72.0, risk=30.0)
    decision, execution = orch.process_signal(entry)

    assert decision.side == "sell"
    assert getattr(decision, "signal_side", "") == "SHORT"
    assert execution.status == "executed"
    assert store.has_position("ETH", "short")

    # Price drops to TP for short
    tp_price = 100.0 * (1 - tmp_config["trading"]["take_profit_pct"] / 100) - 5.0
    exit_signals = monitor.check_exits({"ETH": tp_price})
    assert len(exit_signals) == 1
    assert exit_signals[0].action == "short_exit"


def test_paper_mode_never_live(tmp_config):
    """All executions in paper mode must have mode='paper'."""
    orch = OrchestrationAgent(tmp_config)
    decisions, executions = orch.process_signals([
        _signal("buy", "BTC"),
        _signal("buy", "ETH"),
    ])
    for ex in executions:
        assert ex.mode == "paper", f"Expected paper mode, got {ex.mode}"


# ---------------------------------------------------------------------------
# F12.2  Kill switch
# ---------------------------------------------------------------------------

def test_kill_switch_blocks_all_new_orders(tmp_config, monkeypatch):
    monkeypatch.setenv("TRADING_KILL_SWITCH", "true")
    executor = ExchangeExecutor(tmp_config)
    from agents.decision_agent import DecisionAgent
    signal = _signal("buy", "BTC")
    decision = DecisionAgent(tmp_config).decide(signal)
    result = executor.execute(decision)
    assert result.status == "rejected"
    assert "KILL_SWITCH" in result.message


# ---------------------------------------------------------------------------
# F12.3  Daily order limit guard
# ---------------------------------------------------------------------------

def test_max_orders_per_run_respected(tmp_config):
    """max_orders_per_run=3 → max 3 executions even with 5 signals."""
    orch = OrchestrationAgent(tmp_config)
    signals = [_signal("buy", sym) for sym in ["BTC", "ETH", "SOL", "XRP", "BTC"]]
    # adjust to allow all 5 symbols
    tmp_config["trading"]["allowed_symbols"] = ["BTC", "ETH", "SOL", "XRP"]
    # need fresh orch with updated config
    orch2 = OrchestrationAgent(tmp_config)
    _, executions = orch2.process_signals(signals)
    assert len(executions) <= tmp_config["trading"]["max_orders_per_run"]


# ---------------------------------------------------------------------------
# F12.5  Scientific acceptance — smoke must still pass offline
# ---------------------------------------------------------------------------

def test_smoke_offline_pipeline_green(tmp_config):
    """Quick end-to-end offline check: scan→filter→analyst→orchestrate→paper."""
    from main import build_sample_raw_data
    from agents.filter_agent import FilterAgent
    from agents.ai_analyst import AIAnalystAgent

    raw = build_sample_raw_data()
    filtered = FilterAgent().run(raw)
    tokens = filtered["trending"] + filtered["new_tokens"]
    signals = AIAnalystAgent().analyze_batch(tokens, filtered["whale_moves"])

    assert signals, "Expected at least one alpha signal from sample data"

    orch = OrchestrationAgent(tmp_config)
    decisions, executions = orch.process_signals(signals)

    assert decisions, "Expected at least one decision"
    buy_decisions = [d for d in decisions if d.side == "buy"]
    assert buy_decisions, (
        "Expected at least one approved buy decision. "
        "Check alpha confidence vs min_buy_confidence threshold (G1)."
    )
    assert executions, "Expected at least one paper execution"
    assert all(e.mode == "paper" for e in executions)
