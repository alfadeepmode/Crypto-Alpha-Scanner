#!/usr/bin/env python3
"""TradingView webhook receiver for Crypto Alpha Scanner.

Default behavior is paper trading. Live Binance orders require:
TRADING_MODE=live, LIVE_TRADING=true, TRADING_EXCHANGE=binance, Binance API keys.
"""

import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

from agents.orchestration_agent import OrchestrationAgent
from models.schemas import AlphaSignal, TokenData
from tools.exchange_executor import ExchangeExecutor

load_dotenv()


def load_config() -> dict:
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_signal_side(raw_side: str) -> tuple[str, str]:
    """Return backend action and normalized futures side.

    The action field stays backward-compatible with the existing DecisionAgent.
    normalized_side preserves the exact TradingView intent for logs/tests.
    """
    side = str(raw_side or "watch").strip().lower()
    if side in {"long", "buy"}:
        return "buy", "LONG"
    if side in {"short"}:
        return "short", "SHORT"
    if side in {"long_exit", "sell"}:
        return "sell", "LONG_EXIT"
    if side in {"short_exit", "exit"}:
        return "short_exit", "SHORT_EXIT"
    return "watch", "HOLD"


def build_signal(payload: dict) -> AlphaSignal:
    symbol = str(payload.get("symbol") or payload.get("ticker") or "").replace("USDT", "").replace("USD", "").upper()
    action, normalized_side = normalize_signal_side(payload.get("side") or payload.get("action") or "watch")

    price = float(payload.get("price") or payload.get("close") or 0)
    confidence = float(payload.get("confidence") or 80)
    risk = float(payload.get("risk_score") or payload.get("risk") or 30)

    token = TokenData(
        address=symbol,
        symbol=symbol,
        name=symbol,
        network="binance",
        price_usd=price,
        liquidity_usd=float(payload.get("liquidity_usd") or 1_000_000),
        volume_24h=float(payload.get("volume_24h") or 1_000_000),
    )
    return AlphaSignal(
        token=token,
        signal_type="tradingview",
        confidence=confidence,
        risk_score=risk,
        action=action,
        reasoning=str(payload.get("reason") or f"TradingView alert {normalized_side}"),
        detected_at=datetime.now(),
    )


class TradingViewHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if urlparse(self.path).path != "/webhook/tradingview":
            self.send_error(404, "not found")
            return

        expected_secret = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
        got_secret = self.headers.get("X-Webhook-Secret", "")
        if expected_secret and got_secret != expected_secret:
            self.send_error(403, "bad secret")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
            config = load_config()
            signal = build_signal(payload)
            decision, execution = OrchestrationAgent(config).process_signal(signal)
            if execution is None:
                execution = ExchangeExecutor(config).execute(decision)
            body = {
                "ok": True,
                "symbol": signal.token.symbol,
                "decision": decision.side,
                "status": execution.status,
                "mode": execution.mode,
                "message": execution.message,
            }
            self._json(200, body)
        except Exception as exc:
            self._json(500, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"[TradingViewWebhook] {self.address_string()} - " + fmt % args)

    def _json(self, status: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    host = os.getenv("TRADINGVIEW_WEBHOOK_HOST", "127.0.0.1")
    port = int(os.getenv("TRADINGVIEW_WEBHOOK_PORT", "8787"))
    print(f"TradingView webhook listening on http://{host}:{port}/webhook/tradingview")
    HTTPServer((host, port), TradingViewHandler).serve_forever()


if __name__ == "__main__":
    main()
