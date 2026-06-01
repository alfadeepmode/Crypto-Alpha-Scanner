#!/usr/bin/env python3
"""TradingView webhook receiver for Crypto Alpha Scanner.

Default behavior is paper trading. Live Binance orders require:
TRADING_MODE=live, LIVE_TRADING=true, TRADING_EXCHANGE=binance, Binance API keys.

Security (F10):
- HMAC-SHA256 signature: set X-Webhook-HMAC header with hex digest of body.
- Replay protection: set X-Webhook-Timestamp (Unix float); requests older than
  WEBHOOK_REPLAY_WINDOW_SEC (default 60) are rejected.
- Backward compat: plain X-Webhook-Secret header still supported when no HMAC header.
"""

import hashlib
import hmac
import json
import os
import time
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
    """Return (backend_action, normalized_futures_side) for any input.

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


# ---------------------------------------------------------------------------
# F10.2  HMAC signature verification
# ---------------------------------------------------------------------------

def verify_hmac(secret: str, payload: bytes, signature: str) -> bool:
    """Return True when HMAC-SHA256(secret, payload) matches signature."""
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# F10.3  Replay protection
# ---------------------------------------------------------------------------

def is_fresh_timestamp(timestamp_str: str, window_seconds: float = 60.0) -> bool:
    """Return True if timestamp is within window_seconds of now."""
    try:
        ts = float(timestamp_str)
        return abs(time.time() - ts) <= window_seconds
    except (ValueError, TypeError):
        return False


def build_signal(payload: dict) -> AlphaSignal:
    symbol = (
        str(payload.get("symbol") or payload.get("ticker") or "")
        .replace("USDT", "").replace("USD", "").upper()
    )
    action, normalized_side = normalize_signal_side(
        payload.get("side") or payload.get("action") or "watch"
    )

    price = float(payload.get("price") or payload.get("close") or 0)
    confidence = float(payload.get("confidence") or 80)
    risk = float(payload.get("risk_score") or payload.get("risk") or 30)

    token = TokenData(
        address=symbol, symbol=symbol, name=symbol, network="binance",
        price_usd=price,
        liquidity_usd=float(payload.get("liquidity_usd") or 1_000_000),
        volume_24h=float(payload.get("volume_24h") or 1_000_000),
    )
    return AlphaSignal(
        token=token, signal_type="tradingview",
        confidence=confidence, risk_score=risk,
        action=action,
        reasoning=str(payload.get("reason") or f"TradingView alert {normalized_side}"),
        detected_at=datetime.now(),
    )


class TradingViewHandler(BaseHTTPRequestHandler):
    replay_window_seconds: float = float(os.getenv("WEBHOOK_REPLAY_WINDOW_SEC", "60"))

    def do_POST(self):
        if urlparse(self.path).path != "/webhook/tradingview":
            self.send_error(404, "not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_bytes = self.rfile.read(length)

        # F10.2/F10.3: Authentication
        expected_secret = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
        if expected_secret:
            hmac_signature = self.headers.get("X-Webhook-HMAC", "")
            timestamp = self.headers.get("X-Webhook-Timestamp", "")
            plain_secret = self.headers.get("X-Webhook-Secret", "")

            if hmac_signature:
                if not verify_hmac(expected_secret, raw_bytes, hmac_signature):
                    self.send_error(403, "invalid hmac")
                    return
                if timestamp and not is_fresh_timestamp(timestamp, self.replay_window_seconds):
                    self.send_error(403, "replay detected: timestamp out of window")
                    return
            elif plain_secret != expected_secret:
                self.send_error(403, "bad secret")
                return

        raw = raw_bytes.decode("utf-8")
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
