"""F6: ExchangeExecutor unit tests — kill switch, precision, idempotency, guards."""

import os
import pytest
from models.schemas import AlphaSignal, TokenData, TradeDecision
from tools.exchange_executor import ExchangeExecutor


def _token(symbol: str = "BTC", price: float = 100.0) -> TokenData:
    return TokenData(address=symbol, symbol=symbol, name=symbol, network="b",
                     price_usd=price, liquidity_usd=1e6, volume_24h=1e6)


def _buy_decision(tmp_config, symbol: str = "BTC", price: float = 100.0) -> TradeDecision:
    from agents.decision_agent import DecisionAgent
    signal = AlphaSignal(
        token=_token(symbol, price), signal_type="t",
        confidence=72.0, risk_score=30.0, action="buy", reasoning="",
    )
    return DecisionAgent(tmp_config).decide(signal)


# ---------------------------------------------------------------------------
# F12.2  Kill switch
# ---------------------------------------------------------------------------

def test_kill_switch_rejects_any_order(tmp_config, monkeypatch):
    monkeypatch.setenv("TRADING_KILL_SWITCH", "true")
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    result = executor.execute(dec)
    assert result.status == "rejected"
    assert "KILL_SWITCH" in result.message


def test_kill_switch_false_allows_paper(tmp_config, monkeypatch):
    monkeypatch.setenv("TRADING_KILL_SWITCH", "false")
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    result = executor.execute(dec)
    assert result.status == "executed"
    assert result.mode == "paper"


# ---------------------------------------------------------------------------
# Paper execution
# ---------------------------------------------------------------------------

def test_paper_execute_creates_file(tmp_config, tmp_path):
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    result = executor.execute(dec)
    assert result.status == "executed"
    assert result.mode == "paper"
    paper_path = tmp_path / "paper_trades.jsonl"
    assert paper_path.exists()
    lines = paper_path.read_text().strip().split("\n")
    assert len(lines) == 1


def test_paper_execute_updates_position(tmp_config):
    from tools.portfolio import PositionStore
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    executor.execute(dec)
    store = PositionStore(tmp_config)
    assert store.has_position("BTC", "long")


def test_hold_decision_skipped(tmp_config):
    executor = ExchangeExecutor(tmp_config)
    dec = TradeDecision(token=_token(), side="hold", amount_usd=0.0)
    result = executor.execute(dec)
    assert result.status == "skipped"


# ---------------------------------------------------------------------------
# F6.1  Fail-closed guards (live mode)
# ---------------------------------------------------------------------------

def test_live_trading_false_rejects(tmp_config, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("TRADING_EXCHANGE", "binance")
    # LIVE_TRADING not set
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    result = executor.execute(dec)
    assert result.status == "rejected"
    assert "LIVE_TRADING" in result.message


def test_symbol_not_in_allowlist_rejected(tmp_config, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("TRADING_EXCHANGE", "binance")
    monkeypatch.setenv("LIVE_TRADING", "true")
    monkeypatch.setenv("EXECUTION_ENV", "testnet")
    monkeypatch.setenv("BINANCE_TESTNET", "true")
    dec = _buy_decision(tmp_config, symbol="DOGE")  # not in allowlist
    executor = ExchangeExecutor(tmp_config)
    result = executor.execute(dec)
    assert result.status == "rejected"
    assert "allowlist" in result.message


def test_mainnet_lock_rejects_without_flag(tmp_config, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("TRADING_EXCHANGE", "binance")
    monkeypatch.setenv("LIVE_TRADING", "true")
    monkeypatch.setenv("EXECUTION_ENV", "mainnet")
    monkeypatch.setenv("ALLOW_MAINNET", "false")
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    result = executor.execute(dec)
    assert result.status == "rejected"
    assert "ALLOW_MAINNET" in result.message


def test_testnet_sandbox_flag_required(tmp_config, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("TRADING_EXCHANGE", "binance")
    monkeypatch.setenv("LIVE_TRADING", "true")
    monkeypatch.setenv("EXECUTION_ENV", "testnet")
    monkeypatch.setenv("BINANCE_TESTNET", "false")
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    result = executor.execute(dec)
    assert result.status == "rejected"
    assert "BINANCE_TESTNET" in result.message


def test_missing_api_key_rejects(tmp_config, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("TRADING_EXCHANGE", "binance")
    monkeypatch.setenv("LIVE_TRADING", "true")
    monkeypatch.setenv("EXECUTION_ENV", "testnet")
    monkeypatch.setenv("BINANCE_TESTNET", "true")
    # No BINANCE_API_KEY
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    result = executor.execute(dec)
    assert result.status == "rejected"
    assert "BINANCE_API_KEY" in result.message


# ---------------------------------------------------------------------------
# F6.2  Precision
# ---------------------------------------------------------------------------

def test_quantize_qty_floors(tmp_config):
    executor = ExchangeExecutor(tmp_config)  # default qty_precision=3
    assert executor._quantize_qty(1.23456789) == pytest.approx(1.234)
    assert executor._quantize_qty(0.9999) == pytest.approx(0.999)


def test_quantize_qty_zero_input(tmp_config):
    executor = ExchangeExecutor(tmp_config)
    assert executor._quantize_qty(0.0) == 0.0
    assert executor._quantize_qty(-1.0) == 0.0


def test_quantize_price_rounds(tmp_config):
    executor = ExchangeExecutor(tmp_config)  # default price_precision=2
    assert executor._quantize_price(100.556) == pytest.approx(100.56)
    assert executor._quantize_price(99.994) == pytest.approx(99.99)


def test_custom_qty_precision(tmp_config):
    tmp_config["trading"]["qty_precision"] = 5
    executor = ExchangeExecutor(tmp_config)
    assert executor._quantize_qty(1.123456789) == pytest.approx(1.12345)


# ---------------------------------------------------------------------------
# F6.3  Idempotency — clientOrderId
# ---------------------------------------------------------------------------

def test_client_order_id_deterministic(tmp_config):
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    id1 = executor._client_order_id(dec)
    id2 = executor._client_order_id(dec)
    assert id1 == id2


def test_client_order_id_format(tmp_config):
    executor = ExchangeExecutor(tmp_config)
    dec = _buy_decision(tmp_config)
    cid = executor._client_order_id(dec)
    assert cid.startswith("cas_")
    assert len(cid) == 20  # "cas_" + 16 hex chars


def test_different_symbols_different_ids(tmp_config):
    executor = ExchangeExecutor(tmp_config)
    dec_btc = _buy_decision(tmp_config, "BTC")
    dec_eth = _buy_decision(tmp_config, "ETH")
    assert executor._client_order_id(dec_btc) != executor._client_order_id(dec_eth)
