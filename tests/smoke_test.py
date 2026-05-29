#!/usr/bin/env python3
"""Offline smoke test for Crypto Alpha Scanner.

This test avoids live APIs and live trading. It validates the local decision,
risk, simulation, paper execution, and futures-style signal semantics with
deterministic sample data.
"""

from pathlib import Path
from copy import deepcopy
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.ai_analyst import AIAnalystAgent
from agents.filter_agent import FilterAgent
from agents.orchestration_agent import OrchestrationAgent
from models.schemas import AlphaSignal, TokenData
from main import build_sample_raw_data, load_config
from tradingview_webhook import normalize_signal_side


def _token(symbol: str = "BTC") -> TokenData:
    return TokenData(address=symbol, symbol=symbol, name=symbol, network="binance", price_usd=100.0, liquidity_usd=1_000_000.0, volume_24h=1_000_000.0)


def assert_webhook_normalization() -> None:
    cases = {
        "long": ("buy", "LONG"),
        "buy": ("buy", "LONG"),
        "short": ("short", "SHORT"),
        "sell": ("sell", "LONG_EXIT"),
        "long_exit": ("sell", "LONG_EXIT"),
        "short_exit": ("short_exit", "SHORT_EXIT"),
        "exit": ("short_exit", "SHORT_EXIT"),
        "unknown": ("watch", "HOLD"),
    }
    for raw, expected in cases.items():
        got = normalize_signal_side(raw)
        if got != expected:
            raise AssertionError(f"normalization failed for {raw}: expected {expected}, got {got}")


def main() -> int:
    assert_webhook_normalization()

    config = load_config()
    raw = build_sample_raw_data()
    filtered = FilterAgent().run(raw)
    tokens = filtered["trending"] + filtered["new_tokens"]
    signals = AIAnalystAgent().analyze_batch(tokens, filtered["whale_moves"])

    if not signals:
        raise AssertionError("expected at least one alpha signal")

    decisions, executions = OrchestrationAgent(config).process_signals(signals)

    if not decisions:
        raise AssertionError("expected at least one trade decision")

    buy_decisions = [d for d in decisions if d.side == "buy"]
    if not buy_decisions:
        raise AssertionError("expected at least one approved buy decision")

    if not executions:
        raise AssertionError("expected at least one paper execution")

    if any(e.mode != "paper" for e in executions):
        raise AssertionError("smoke test must stay in paper mode")

    first_buy = buy_decisions[0]
    sell_signal = AlphaSignal(
        token=first_buy.token,
        signal_type="smoke_sell",
        confidence=80,
        risk_score=75,
        action="sell",
        reasoning="smoke sell after paper position",
    )
    sell_decision, sell_execution = OrchestrationAgent(config).process_signal(sell_signal)
    if sell_decision.side != "sell":
        raise AssertionError(f"expected sell decision with existing long position, got {sell_decision.side}: {sell_decision.reason}")
    if sell_execution is None or sell_execution.status != "executed":
        raise AssertionError("expected executed paper sell")

    futures_config = deepcopy(config)
    futures_config["trading"]["allowed_symbols"] = ["BTC", "ETH", "SOL", "XRP", "ADA"]
    futures_config["trading"]["paper_trades_path"] = "data/smoke_futures_paper.jsonl"
    futures_config["trading"]["position_state_path"] = "data/smoke_futures_positions.json"

    short_signal = AlphaSignal(token=_token("BTC"), signal_type="smoke_short", confidence=90, risk_score=20, action="short", reasoning="smoke short")
    short_decision, short_execution = OrchestrationAgent(futures_config).process_signal(short_signal)
    if getattr(short_decision, "signal_side", "") != "SHORT" or short_decision.side != "sell":
        raise AssertionError(f"expected SHORT sell decision, got {short_decision.side}/{getattr(short_decision, 'signal_side', '')}: {short_decision.reason}")
    if short_execution is None or short_execution.status != "executed":
        raise AssertionError("expected executed paper short entry")

    short_exit_signal = AlphaSignal(token=_token("BTC"), signal_type="smoke_short_exit", confidence=80, risk_score=30, action="short_exit", reasoning="smoke short exit")
    short_exit_decision, short_exit_execution = OrchestrationAgent(futures_config).process_signal(short_exit_signal)
    if getattr(short_exit_decision, "signal_side", "") != "SHORT_EXIT" or short_exit_decision.side != "buy":
        raise AssertionError(f"expected SHORT_EXIT buy decision, got {short_exit_decision.side}/{getattr(short_exit_decision, 'signal_side', '')}: {short_exit_decision.reason}")
    if short_exit_execution is None or short_exit_execution.status != "executed":
        raise AssertionError("expected executed paper short exit")

    batch_config = deepcopy(config)
    batch_config["trading"]["allowed_symbols"] = ["BTC", "ETH", "SOL", "XRP", "ADA"]
    batch_config["trading"]["max_orders_per_run"] = 3
    batch_config["trading"]["paper_trades_path"] = "data/smoke_batch_paper.jsonl"
    batch_config["trading"]["position_state_path"] = "data/smoke_batch_positions.json"
    batch_signals = []
    for symbol in ["BTC", "ETH", "SOL", "XRP", "ADA"]:
        batch_signals.append(AlphaSignal(token=_token(symbol), signal_type="batch_limit", confidence=90, risk_score=20, action="buy", reasoning="batch limit smoke"))
    batch_decisions, batch_executions = OrchestrationAgent(batch_config).process_signals(batch_signals)
    if len(batch_executions) != 3:
        raise AssertionError(f"expected max 3 executions, got {len(batch_executions)}")
    if sum(1 for d in batch_decisions if d.side == "hold") != 2:
        raise AssertionError("expected 2 held decisions after max_orders_per_run")

    old_env = {"TRADING_MODE": os.environ.get("TRADING_MODE"), "TRADING_EXCHANGE": os.environ.get("TRADING_EXCHANGE"), "LIVE_TRADING": os.environ.get("LIVE_TRADING"), "BINANCE_API_KEY": os.environ.get("BINANCE_API_KEY"), "BINANCE_API_SECRET": os.environ.get("BINANCE_API_SECRET")}
    os.environ["TRADING_MODE"] = "live"
    os.environ["TRADING_EXCHANGE"] = "binance"
    os.environ["LIVE_TRADING"] = "true"
    os.environ.pop("BINANCE_API_KEY", None)
    os.environ.pop("BINANCE_API_SECRET", None)
    try:
        live_decision, live_execution = OrchestrationAgent(config).process_signal(batch_signals[0])
        if live_execution is None or live_execution.status != "rejected" or "BINANCE_API_KEY" not in live_execution.message:
            raise AssertionError("expected missing Binance key rejection before ccxt import")
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print(f"smoke ok: {len(signals)} signals, {len(decisions) + len(batch_decisions)} decisions, {len(executions) + 1 + len(batch_executions)} executions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
