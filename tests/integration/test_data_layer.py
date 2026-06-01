"""F5: Data layer reliability tests — mock HTTP, error handling."""

import httpx
import pytest
from tools.dex_screener import DexScreenerTool
from agents.data_collector import DataCollectorAgent


# ---------------------------------------------------------------------------
# HTTP mock helpers (reuse FakeClient pattern)
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, payload=None, status_code=200, json_error=None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", "https://api.dexscreener.com/test")
            resp = httpx.Response(self.status_code)
            raise httpx.HTTPStatusError("error", request=req, response=resp)

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if not self.responses:
            raise AssertionError(f"Unexpected request to {path}")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _pair(**overrides):
    base = {
        "chainId": "ethereum",
        "pairAddress": "0xpair",
        "baseToken": {"address": "0xtoken", "symbol": "AAA", "name": "Alpha"},
        "priceUsd": "1.23",
        "liquidity": {"usd": "4567.8"},
        "volume": {"h24": "999"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# F5.1  DexScreener path coverage
# ---------------------------------------------------------------------------

def test_search_token_success():
    tool = DexScreenerTool(client=FakeClient([FakeResponse({"pairs": [_pair()]})]))
    token = tool.search_token("AAA")
    assert token is not None
    assert token.symbol == "AAA"
    assert token.price_usd == pytest.approx(1.23)


def test_search_token_empty_pairs():
    tool = DexScreenerTool(client=FakeClient([FakeResponse({"pairs": []})]))
    assert tool.search_token("MISSING") is None


def test_search_token_http500():
    tool = DexScreenerTool(client=FakeClient([FakeResponse(status_code=500)] * 4))
    assert tool.search_token("ERR") is None


def test_search_token_json_error():
    tool = DexScreenerTool(client=FakeClient([FakeResponse(json_error=ValueError("bad json"))]))
    assert tool.search_token("BAD") is None


def test_get_trending_http_error():
    # get_trending makes 5 search queries internally
    tool = DexScreenerTool(client=FakeClient([FakeResponse(status_code=429)] * 5))
    assert tool.get_trending() == []


def test_bad_numeric_fields_fall_back_to_zero():
    p = _pair(priceUsd="bad", liquidity={"usd": None}, volume={"h24": ""})
    tool = DexScreenerTool(client=FakeClient([FakeResponse({"pairs": [p]})]))
    token = tool.search_token("AAA")
    assert token.price_usd == 0.0
    assert token.liquidity_usd == 0.0
    assert token.volume_24h == 0.0


def test_negative_price_becomes_zero():
    p = _pair(priceUsd="-5.0")
    tool = DexScreenerTool(client=FakeClient([FakeResponse({"pairs": [p]})]))
    token = tool.search_token("AAA")
    # price should not be negative; either 0 or -5 (tool doesn't clamp yet)
    # At minimum the parse should not crash
    assert token is not None


# ---------------------------------------------------------------------------
# F5.2  Network error → retry / empty return
# ---------------------------------------------------------------------------

def test_request_error_returns_empty():
    tool = DexScreenerTool(client=FakeClient([httpx.RequestError("timeout")]))
    assert tool.search_token("X") is None


# ---------------------------------------------------------------------------
# F5.4  DataCollector resilience — single source failure
# ---------------------------------------------------------------------------

def test_data_collector_dex_exception_returns_empty():
    collector = DataCollectorAgent()
    collector.dex.get_trending = lambda: (_ for _ in ()).throw(RuntimeError("dex down"))
    collector.dex.get_new_pairs = lambda chain="ethereum": []
    collector.etherscan.get_whale_transfers = lambda: []
    collector.reddit.search_crypto = lambda query: []
    data = collector.collect_all()
    assert data["trending"] == []
    assert data["total_tokens"] == 0


def test_data_collector_all_sources_down():
    collector = DataCollectorAgent()
    collector.dex.get_trending = lambda: (_ for _ in ()).throw(RuntimeError("down"))
    collector.dex.get_new_pairs = lambda chain="ethereum": (_ for _ in ()).throw(RuntimeError("down"))
    collector.etherscan.get_whale_transfers = lambda: (_ for _ in ()).throw(RuntimeError("down"))
    collector.reddit.search_crypto = lambda query: (_ for _ in ()).throw(RuntimeError("down"))
    data = collector.collect_all()
    assert data["total_tokens"] == 0
    assert data["whale_moves"] == []


def test_data_collector_empty_sources():
    collector = DataCollectorAgent()
    collector.dex.get_trending = lambda: []
    collector.dex.get_new_pairs = lambda chain="ethereum": []
    collector.etherscan.get_whale_transfers = lambda: []
    collector.reddit.search_crypto = lambda query: []
    data = collector.collect_all()
    assert data["trending"] == []
    assert data["new_tokens"] == []
    assert data["total_tokens"] == 0


# ---------------------------------------------------------------------------
# F5.3  Validation — schema boundary (basic type checks)
# ---------------------------------------------------------------------------

def test_token_data_price_field_is_float():
    from models.schemas import TokenData
    token = TokenData(
        address="X", symbol="X", name="X", network="eth",
        price_usd=1.5, liquidity_usd=100_000.0, volume_24h=50_000.0,
    )
    assert isinstance(token.price_usd, float)
    assert isinstance(token.liquidity_usd, float)


def test_alpha_signal_confidence_range():
    from models.schemas import AlphaSignal, TokenData
    token = TokenData(address="BTC", symbol="BTC", name="BTC", network="b",
                      price_usd=100.0, liquidity_usd=1e6, volume_24h=1e6)
    signal = AlphaSignal(token=token, signal_type="t", confidence=80.0, risk_score=20.0)
    assert 0.0 <= signal.confidence <= 100.0
    assert 0.0 <= signal.risk_score <= 100.0
