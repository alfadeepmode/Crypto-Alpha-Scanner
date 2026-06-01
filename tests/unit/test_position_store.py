"""F7: PositionStore unit tests — lifecycle and realized PnL."""

import pytest
from tools.portfolio import PositionStore
from models.schemas import TradeDecision, TokenData


def _token(symbol: str = "BTC", price: float = 100.0) -> TokenData:
    return TokenData(address=symbol, symbol=symbol, name=symbol, network="b",
                     price_usd=price, liquidity_usd=1e6, volume_24h=1e6)


def _decision(symbol: str, side: str, amount_usd: float, signal_side: str,
              position_side: str, reduce_only: bool = False, price: float = 100.0) -> TradeDecision:
    d = TradeDecision(token=_token(symbol, price), side=side, amount_usd=amount_usd)
    d.signal_side = signal_side
    d.position_side = position_side
    d.reduce_only = reduce_only
    d.qty = amount_usd / price
    return d


# ---------------------------------------------------------------------------
# Basic state management
# ---------------------------------------------------------------------------

def test_empty_store_has_no_positions(tmp_config):
    store = PositionStore(tmp_config)
    assert not store.has_position("BTC", "long")
    assert store.get("BTC", "long") is None


def test_long_entry_creates_position(tmp_config):
    store = PositionStore(tmp_config)
    d = _decision("BTC", "buy", 100.0, "LONG", "long")
    store.apply_execution(d, "paper")
    assert store.has_position("BTC", "long")
    pos = store.get("BTC", "long")
    assert pos["qty"] == pytest.approx(1.0)
    assert pos["avg_entry_price"] == pytest.approx(100.0)


def test_short_entry_creates_position(tmp_config):
    store = PositionStore(tmp_config)
    d = _decision("ETH", "sell", 100.0, "SHORT", "short", price=200.0)
    store.apply_execution(d, "paper")
    assert store.has_position("ETH", "short")


def test_long_and_short_are_separate_keys(tmp_config):
    store = PositionStore(tmp_config)
    store.apply_execution(_decision("BTC", "buy", 100.0, "LONG", "long"), "paper")
    store.apply_execution(_decision("BTC", "sell", 100.0, "SHORT", "short"), "paper")
    assert store.has_position("BTC", "long")
    assert store.has_position("BTC", "short")


# ---------------------------------------------------------------------------
# Long PnL
# ---------------------------------------------------------------------------

def test_long_exit_realized_pnl_profit(tmp_config):
    store = PositionStore(tmp_config)
    # Entry: 1 BTC @ 100 → qty=1.0, cost=100
    store.apply_execution(_decision("BTC", "buy", 100.0, "LONG", "long", price=100.0), "paper")
    # Full exit: need amount_usd = qty * exit_price = 1.0 * 120 = 120 to exit full qty
    store.apply_execution(_decision("BTC", "sell", 120.0, "LONG_EXIT", "long", True, price=120.0), "paper")
    pos = store.get("BTC", "long")
    assert pos["realized_pnl_usd"] == pytest.approx(20.0, rel=0.01)


def test_long_exit_realized_pnl_loss(tmp_config):
    store = PositionStore(tmp_config)
    store.apply_execution(_decision("BTC", "buy", 100.0, "LONG", "long", price=100.0), "paper")
    # Full exit at 80: amount_usd = 1.0 * 80 = 80
    store.apply_execution(_decision("BTC", "sell", 80.0, "LONG_EXIT", "long", True, price=80.0), "paper")
    pos = store.get("BTC", "long")
    assert pos["realized_pnl_usd"] == pytest.approx(-20.0, rel=0.01)


# ---------------------------------------------------------------------------
# Short PnL
# ---------------------------------------------------------------------------

def test_short_exit_realized_pnl_profit(tmp_config):
    store = PositionStore(tmp_config)
    # Entry: 1 BTC short @ 100
    store.apply_execution(_decision("BTC", "sell", 100.0, "SHORT", "short", price=100.0), "paper")
    # Exit at 80: amount_usd = 1.0 * 80 = 80 to cover full qty
    store.apply_execution(_decision("BTC", "buy", 80.0, "SHORT_EXIT", "short", True, price=80.0), "paper")
    pos = store.get("BTC", "short")
    assert pos["realized_pnl_usd"] == pytest.approx(20.0, rel=0.01)


def test_short_exit_realized_pnl_loss(tmp_config):
    store = PositionStore(tmp_config)
    store.apply_execution(_decision("BTC", "sell", 100.0, "SHORT", "short", price=100.0), "paper")
    # Exit at 120: amount_usd = 1.0 * 120 = 120
    store.apply_execution(_decision("BTC", "buy", 120.0, "SHORT_EXIT", "short", True, price=120.0), "paper")
    pos = store.get("BTC", "short")
    assert pos["realized_pnl_usd"] == pytest.approx(-20.0, rel=0.01)


# ---------------------------------------------------------------------------
# Position closure
# ---------------------------------------------------------------------------

def test_full_exit_zeroes_qty(tmp_config):
    store = PositionStore(tmp_config)
    store.apply_execution(_decision("BTC", "buy", 100.0, "LONG", "long", price=100.0), "paper")
    store.apply_execution(_decision("BTC", "sell", 100.0, "LONG_EXIT", "long", True, price=100.0), "paper")
    pos = store.get("BTC", "long")
    assert pos["qty"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

def test_has_position_backward_compat(tmp_config):
    """Old state files keyed only by symbol (no side suffix) still work."""
    store = PositionStore(tmp_config)
    data = store.load()
    data["positions"]["BTC"] = {
        "symbol": "BTC", "position_side": "long",
        "qty": 1.0, "cost_usd": 100.0, "avg_entry_price": 100.0,
        "last_price": 100.0, "realized_pnl_usd": 0.0,
        "mode": "paper", "updated_at": "2024-01-01",
    }
    store.save(data)
    assert store.has_position("BTC", "long")
