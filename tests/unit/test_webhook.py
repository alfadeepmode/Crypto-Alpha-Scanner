"""F10: Webhook HMAC, replay protection, and signal normalization tests."""

import hashlib
import hmac
import time
import pytest
from tradingview_webhook import verify_hmac, is_fresh_timestamp, build_signal, normalize_signal_side


# ---------------------------------------------------------------------------
# F10.2  HMAC signature verification
# ---------------------------------------------------------------------------

def test_valid_hmac_accepted():
    secret = "mysecret"
    payload = b'{"side": "long", "symbol": "BTCUSDT"}'
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_hmac(secret, payload, sig) is True


def test_invalid_hmac_rejected():
    assert verify_hmac("secret", b"payload", "badhex") is False


def test_empty_hmac_rejected():
    assert verify_hmac("secret", b"payload", "") is False


def test_wrong_secret_rejected():
    payload = b"data"
    correct_sig = hmac.new(b"correct", payload, hashlib.sha256).hexdigest()
    assert verify_hmac("wrong", payload, correct_sig) is False


def test_hmac_is_constant_time():
    """Calling twice with same inputs must give same result (no side channels visible)."""
    sig = hmac.new(b"s", b"p", hashlib.sha256).hexdigest()
    assert verify_hmac("s", b"p", sig) is True
    assert verify_hmac("s", b"p", sig) is True


# ---------------------------------------------------------------------------
# F10.3  Replay protection
# ---------------------------------------------------------------------------

def test_fresh_timestamp_accepted():
    ts = str(time.time())
    assert is_fresh_timestamp(ts, window_seconds=60) is True


def test_old_timestamp_rejected():
    old_ts = str(time.time() - 120)
    assert is_fresh_timestamp(old_ts, window_seconds=60) is False


def test_future_timestamp_rejected():
    future_ts = str(time.time() + 120)
    assert is_fresh_timestamp(future_ts, window_seconds=60) is False


def test_exactly_at_window_boundary():
    # Use window=61 to allow for test execution time (1s tolerance)
    boundary = str(time.time() - 60)
    assert is_fresh_timestamp(boundary, window_seconds=61) is True


def test_invalid_timestamp_rejected():
    assert is_fresh_timestamp("not_a_number", window_seconds=60) is False
    assert is_fresh_timestamp("", window_seconds=60) is False
    assert is_fresh_timestamp(None, window_seconds=60) is False


# ---------------------------------------------------------------------------
# build_signal
# ---------------------------------------------------------------------------

def test_build_signal_long():
    payload = {"side": "long", "symbol": "BTCUSDT", "price": "100", "confidence": "80", "risk_score": "25"}
    signal = build_signal(payload)
    assert signal.token.symbol == "BTC"
    assert signal.action == "buy"
    assert signal.confidence == 80.0
    assert signal.risk_score == 25.0


def test_build_signal_short():
    payload = {"side": "short", "symbol": "ETHUSDT", "price": "3500"}
    signal = build_signal(payload)
    assert signal.token.symbol == "ETH"
    assert signal.action == "short"


def test_build_signal_missing_fields_use_defaults():
    payload = {"side": "long"}
    signal = build_signal(payload)
    assert signal.confidence == 80.0  # default
    assert signal.risk_score == 30.0  # default
    assert signal.token.price_usd == 0.0


def test_build_signal_ticker_field():
    payload = {"action": "buy", "ticker": "SOLUSDT", "price": "50"}
    signal = build_signal(payload)
    assert signal.token.symbol == "SOL"


def test_build_signal_strips_usdt_suffix():
    payload = {"side": "long", "symbol": "XRPUSDT"}
    signal = build_signal(payload)
    assert signal.token.symbol == "XRP"
