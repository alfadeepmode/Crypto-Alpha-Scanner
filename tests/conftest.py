"""Shared pytest fixtures for Crypto Alpha Scanner tests."""

import csv
import os
import random
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Environment isolation
# ---------------------------------------------------------------------------

_TRADING_ENV_KEYS = [
    "TRADING_MODE", "TRADING_EXCHANGE", "LIVE_TRADING",
    "BINANCE_API_KEY", "BINANCE_API_SECRET", "EXECUTION_ENV",
    "ALLOW_MAINNET", "BINANCE_TESTNET", "POSITION_STATE_PATH",
    "PAPER_TRADES_PATH", "AUTO_TRADE", "WATCH_MODE",
    "TRADING_KILL_SWITCH",
]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Remove trading env vars for each test so tests are hermetic."""
    for key in _TRADING_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_config(tmp_path):
    """Return a minimal config dict with all paths pointing to tmp_path."""
    return {
        "trading": {
            "enabled": True,
            "mode": "paper",
            "exchange": "paper",
            "execution_env": "testnet",
            "allow_mainnet": False,
            "base_order_usd": 25.0,
            "max_order_usd": 100.0,
            "max_orders_per_run": 3,
            "min_buy_confidence": 65.0,
            "max_buy_risk": 35.0,
            "min_sell_risk": 70.0,
            "stop_loss_pct": 8.0,
            "take_profit_pct": 18.0,
            "allow_short_entries": True,
            "allow_sells_without_position": False,
            "min_liquidity_usd": 100_000.0,
            "allowed_symbols": ["BTC", "ETH", "SOL", "XRP"],
            "binance_testnet": True,
            "require_future_simulation": True,
            "max_projected_loss_usd": 15.0,
            "min_reward_risk": 1.4,
            "taker_fee_bps": 5.0,
            "slippage_bps": 3.0,
            "funding_cost_bps": 1.0,
            "liquidation_buffer_min_pct": 6.0,
            "paper_trades_path": str(tmp_path / "paper_trades.jsonl"),
            "position_state_path": str(tmp_path / "positions.json"),
        },
        "orchestration": {
            "log_path": str(tmp_path / "orchestration_log.jsonl"),
        },
        "filters": {
            "min_liquidity_usd": 50_000.0,
            "min_transfer_usd": 10_000.0,
            "ignore_contracts": [],
        },
        "analysis": {
            "probability_buy_threshold": 0.62,
            "min_confidence_score": 65.0,
        },
        "schedule": {"interval_minutes": 15},
        "agents": {"temperature": 0.3},
    }


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def btc_token():
    from models.schemas import TokenData
    return TokenData(
        address="BTC", symbol="BTC", name="Bitcoin",
        network="binance", price_usd=100.0,
        liquidity_usd=1_000_000.0, volume_24h=1_000_000.0,
        is_verified=True,
    )


@pytest.fixture
def eth_token():
    from models.schemas import TokenData
    return TokenData(
        address="ETH", symbol="ETH", name="Ethereum",
        network="binance", price_usd=3500.0,
        liquidity_usd=8_000_000.0, volume_24h=250_000_000.0,
        is_verified=True,
    )


@pytest.fixture
def low_token():
    from models.schemas import TokenData
    return TokenData(
        address="LOW", symbol="LOW", name="Low Liq",
        network="ethereum", price_usd=0.01,
        liquidity_usd=1_000.0, volume_24h=500.0,
    )


@pytest.fixture
def buy_signal(btc_token):
    from models.schemas import AlphaSignal
    return AlphaSignal(
        token=btc_token, signal_type="trending",
        confidence=72.0, risk_score=30.0, action="buy",
        reasoning="test buy signal",
    )


@pytest.fixture
def short_signal(btc_token):
    from models.schemas import AlphaSignal
    return AlphaSignal(
        token=btc_token, signal_type="trending",
        confidence=72.0, risk_score=30.0, action="short",
        reasoning="test short signal",
    )


# ---------------------------------------------------------------------------
# Klines CSV fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def klines_csv(tmp_path):
    """Generate a 300-bar synthetic klines CSV for backtest unit tests."""
    rng = random.Random(42)
    price = 50_000.0
    path = tmp_path / "klines_test.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
        for i in range(300):
            price *= 1 + rng.gauss(0.0002, 0.008)
            high = price * (1 + abs(rng.gauss(0, 0.004)))
            low = price * (1 - abs(rng.gauss(0, 0.004)))
            close = price * (1 + rng.gauss(0, 0.002))
            volume = abs(rng.gauss(500, 200)) * 1000
            writer.writerow([
                1_704_067_200_000 + i * 300_000,
                round(price, 2), round(high, 2), round(low, 2),
                round(close, 2), round(volume, 2),
            ])
    return path


@pytest.fixture
def static_klines_csv():
    """Return path to the static klines fixture committed to the repo."""
    return ROOT / "tests" / "fixtures" / "klines_mini.csv"
