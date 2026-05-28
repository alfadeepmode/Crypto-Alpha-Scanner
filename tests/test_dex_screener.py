import httpx

from agents.data_collector import DataCollectorAgent
from tools.dex_screener import DexScreenerTool


class FakeResponse:
    def __init__(self, payload=None, status_code=200, json_error=None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(self.status_code)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

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
            raise AssertionError("unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def pair(**overrides):
    data = {
        "chainId": "ethereum",
        "pairAddress": "0xpair",
        "baseToken": {"address": "0xtoken", "symbol": "AAA", "name": "Alpha"},
        "priceUsd": "1.23",
        "liquidity": {"usd": "4567.8"},
        "volume": {"h24": "999"},
    }
    data.update(overrides)
    return data


def test_search_token_successful_response():
    tool = DexScreenerTool(client=FakeClient([FakeResponse({"pairs": [pair()]})]))

    token = tool.search_token("AAA")

    assert token is not None
    assert token.address == "0xtoken"
    assert token.symbol == "AAA"
    assert token.network == "ethereum"
    assert token.price_usd == 1.23
    assert token.liquidity_usd == 4567.8
    assert token.volume_24h == 999.0


def test_search_token_empty_pairs_returns_none():
    tool = DexScreenerTool(client=FakeClient([FakeResponse({"pairs": []})]))

    assert tool.search_token("missing") is None


def test_bad_numeric_fields_fall_back_to_zero():
    bad_pair = pair(priceUsd="bad", liquidity={"usd": None}, volume={"h24": ""})
    tool = DexScreenerTool(client=FakeClient([FakeResponse({"pairs": [bad_pair]})]))

    token = tool.search_token("AAA")

    assert token is not None
    assert token.price_usd == 0.0
    assert token.liquidity_usd == 0.0
    assert token.volume_24h == 0.0


def test_api_error_returns_none_or_empty_list():
    tool = DexScreenerTool(client=FakeClient([FakeResponse(status_code=500)] * 6))

    assert tool.search_token("AAA") is None
    assert tool.get_trending() == []


def test_json_parse_error_returns_none():
    tool = DexScreenerTool(client=FakeClient([FakeResponse(json_error=ValueError("invalid json"))]))

    assert tool.search_token("AAA") is None


def test_data_collector_handles_empty_or_failed_sources():
    collector = DataCollectorAgent()
    collector.dex.get_trending = lambda: []
    collector.dex.get_new_pairs = lambda chain="ethereum": []
    collector.etherscan.get_whale_transfers = lambda: []
    collector.reddit.search_crypto = lambda query: []

    data = collector.collect_all()

    assert data["trending"] == []
    assert data["new_tokens"] == []
    assert data["whale_moves"] == []
    assert data["reddit_signals"] == []
    assert data["total_tokens"] == 0


def test_data_collector_converts_source_exception_to_empty_list():
    collector = DataCollectorAgent()
    collector.dex.get_trending = lambda: (_ for _ in ()).throw(RuntimeError("dex down"))
    collector.dex.get_new_pairs = lambda chain="ethereum": []
    collector.etherscan.get_whale_transfers = lambda: []
    collector.reddit.search_crypto = lambda query: []

    data = collector.collect_all()

    assert data["trending"] == []
    assert data["total_tokens"] == 0


def test_search_pairs_returns_multiple_tokens():
    first = pair(baseToken={"address": "0x1", "symbol": "A", "name": "A"})
    second = pair(baseToken={"address": "0x2", "symbol": "B", "name": "B"})
    tool = DexScreenerTool(client=FakeClient([FakeResponse({"pairs": [first, second]})]))

    tokens = tool.search_pairs("A", limit=10)

    assert [token.address for token in tokens] == ["0x1", "0x2"]


def test_latest_profiles_and_token_pairs_helpers():
    client = FakeClient([
        FakeResponse([
            {"chainId": "ethereum", "tokenAddress": "0xaaa"},
            "bad",
            {"chainId": "bsc", "tokenAddress": "0xbbb"},
        ]),
        FakeResponse([pair(baseToken={"address": "0xaaa", "symbol": "AAA", "name": "AAA"})]),
    ])
    tool = DexScreenerTool(client=client)

    profiles = tool.get_latest_profiles(limit=3)
    tokens = tool.get_token_pairs("ethereum", "0xaaa", limit=1)

    assert profiles == [
        {"chainId": "ethereum", "tokenAddress": "0xaaa"},
        {"chainId": "bsc", "tokenAddress": "0xbbb"},
    ]
    assert len(tokens) == 1
    assert tokens[0].symbol == "AAA"
