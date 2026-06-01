"""F7: PositionMonitor SL/TP enforcement tests."""

import pytest
from agents.position_monitor import PositionMonitor
from models.schemas import TradeDecision, TokenData


def _setup_position(tmp_config, symbol: str, side: str, qty: float, avg_entry: float):
    """Helper: write a position directly into the store."""
    from tools.portfolio import PositionStore
    store = PositionStore(tmp_config)
    data = store.load()
    key = f"{symbol.upper()}:{side}"
    data["positions"][key] = {
        "symbol": symbol.upper(),
        "position_side": side,
        "qty": qty,
        "cost_usd": qty * avg_entry,
        "avg_entry_price": avg_entry,
        "last_price": avg_entry,
        "realized_pnl_usd": 0.0,
        "mode": "paper",
        "updated_at": "2024-01-01T00:00:00",
    }
    store.save(data)


# ---------------------------------------------------------------------------
# Long position
# ---------------------------------------------------------------------------

def test_long_stop_loss_triggers_sell(tmp_config):
    _setup_position(tmp_config, "BTC", "long", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    # Default SL = 100 * (1 - 8%) = 92.0; trigger at 90
    signals = monitor.check_exits({"BTC": 90.0})
    assert len(signals) == 1
    sig = signals[0]
    assert sig.action == "sell"
    assert "Stop-loss" in sig.reasoning
    assert sig.token.symbol == "BTC"


def test_long_take_profit_triggers_sell(tmp_config):
    _setup_position(tmp_config, "BTC", "long", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    # Default TP = 100 * (1 + 18%) = 118.0; trigger at 120
    signals = monitor.check_exits({"BTC": 120.0})
    assert len(signals) == 1
    assert signals[0].action == "sell"
    assert "Take-profit" in signals[0].reasoning


def test_long_price_between_sl_tp_no_signal(tmp_config):
    _setup_position(tmp_config, "BTC", "long", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    signals = monitor.check_exits({"BTC": 105.0})
    assert signals == []


# ---------------------------------------------------------------------------
# Short position
# ---------------------------------------------------------------------------

def test_short_stop_loss_triggers_exit(tmp_config):
    _setup_position(tmp_config, "BTC", "short", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    # Short SL = 100 * (1 + 8%) = 108.0; trigger at 110
    signals = monitor.check_exits({"BTC": 110.0})
    assert len(signals) == 1
    assert signals[0].action == "short_exit"
    assert "Stop-loss" in signals[0].reasoning


def test_short_take_profit_triggers_exit(tmp_config):
    _setup_position(tmp_config, "BTC", "short", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    # Short TP = 100 * (1 - 18%) = 82.0; trigger at 80
    signals = monitor.check_exits({"BTC": 80.0})
    assert len(signals) == 1
    assert signals[0].action == "short_exit"
    assert "Take-profit" in signals[0].reasoning


def test_short_price_between_sl_tp_no_signal(tmp_config):
    _setup_position(tmp_config, "BTC", "short", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    signals = monitor.check_exits({"BTC": 95.0})
    assert signals == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_positions_returns_empty(tmp_config):
    monitor = PositionMonitor(tmp_config)
    signals = monitor.check_exits({"BTC": 50000.0})
    assert signals == []


def test_zero_qty_position_ignored(tmp_config):
    from tools.portfolio import PositionStore
    store = PositionStore(tmp_config)
    data = store.load()
    data["positions"]["BTC:long"] = {
        "symbol": "BTC", "position_side": "long",
        "qty": 0.0, "cost_usd": 0.0, "avg_entry_price": 100.0,
        "last_price": 100.0, "realized_pnl_usd": 0.0,
        "mode": "paper", "updated_at": "2024-01-01",
    }
    store.save(data)
    monitor = PositionMonitor(tmp_config)
    signals = monitor.check_exits({"BTC": 90.0})
    assert signals == []


def test_missing_price_for_symbol_ignored(tmp_config):
    _setup_position(tmp_config, "ETH", "long", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    signals = monitor.check_exits({"BTC": 50.0})  # ETH price not provided
    assert signals == []


def test_multiple_positions_multiple_exits(tmp_config):
    _setup_position(tmp_config, "BTC", "long", qty=1.0, avg_entry=100.0)
    _setup_position(tmp_config, "ETH", "short", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    # BTC hits TP, ETH hits SL
    signals = monitor.check_exits({"BTC": 120.0, "ETH": 110.0})
    assert len(signals) == 2
    actions = {s.token.symbol: s.action for s in signals}
    assert actions["BTC"] == "sell"
    assert actions["ETH"] == "short_exit"


def test_get_open_positions_returns_all(tmp_config):
    _setup_position(tmp_config, "BTC", "long", qty=1.0, avg_entry=100.0)
    _setup_position(tmp_config, "ETH", "short", qty=0.5, avg_entry=3500.0)
    monitor = PositionMonitor(tmp_config)
    positions = monitor.get_open_positions()
    assert len(positions) == 2


def test_sl_at_exact_boundary_triggers(tmp_config):
    _setup_position(tmp_config, "BTC", "long", qty=1.0, avg_entry=100.0)
    monitor = PositionMonitor(tmp_config)
    sl_exact = 100.0 * (1 - 8 / 100)  # = 92.0
    signals = monitor.check_exits({"BTC": sl_exact})
    assert len(signals) == 1  # price == SL → triggers
