"""Exchange executor - varsayilan paper trading, live mod fail-closed.

Faz 5/6 ilkeleri:
- mainnet varsayilan olarak kapali kalir
- live path yalnizca testnet veya acikca izin verilmis mainnet kosullarinda ilerler
- TRADING_KILL_SWITCH=true → tum yeni emirler aninda durdurulur
- clientOrderId ile idempotency (tekrar gonderimde cift emir yok)
- qty/price precision: yapilandirilebilir ondalik yuvarla (gercek tickSize/stepSize Faz 2)
- bracket order: entry sonrasi SL stop-market + TP take-profit-market (reduceOnly)
"""

import hashlib
import json
import math
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from models.schemas import TradeDecision, TradeExecution
from tools.portfolio import PositionStore


class ExchangeExecutor:
    """Trade kararlarini paper dosyasina yazar veya fail-closed live adapter'a iletir."""

    def __init__(self, config: dict):
        trading = config.get("trading", {})
        self.mode = os.getenv("TRADING_MODE", trading.get("mode", "paper")).lower()
        self.exchange = os.getenv("TRADING_EXCHANGE", trading.get("exchange", "paper")).lower()
        self.execution_env = os.getenv("EXECUTION_ENV", trading.get("execution_env", "testnet")).lower()
        self.allow_mainnet = os.getenv("ALLOW_MAINNET", str(trading.get("allow_mainnet", False))).lower() == "true"
        self.paper_path = Path(os.getenv("PAPER_TRADES_PATH", trading.get("paper_trades_path", "data/paper_trades.jsonl")))
        self.allowed_symbols = {s.upper() for s in trading.get("allowed_symbols", ["BTC", "ETH", "SOL", "XRP"])}
        self.binance_testnet = os.getenv("BINANCE_TESTNET", str(trading.get("binance_testnet", True))).lower() == "true"
        self.position_store = PositionStore(config)
        # Precision defaults (Faz 2: override with exchangeInfo tickSize/stepSize)
        self.qty_precision = int(trading.get("qty_precision", 3))
        self.price_precision = int(trading.get("price_precision", 2))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_batch(self, decisions: list[TradeDecision]) -> list[TradeExecution]:
        return [self.execute(decision) for decision in decisions if decision.side != "hold"]

    def execute(self, decision: TradeDecision) -> TradeExecution:
        if decision.side == "hold":
            return TradeExecution(decision=decision, status="skipped", mode=self.mode, exchange=self.exchange, message=decision.reason)

        # F12.2 — global kill switch
        if os.getenv("TRADING_KILL_SWITCH", "").lower() == "true":
            return self._reject(decision, "TRADING_KILL_SWITCH aktif: tum emirler durduruldu")

        if self.mode != "live":
            return self._paper_execute(decision)

        guard = self._live_safety_guard(decision)
        if guard is not None:
            return guard

        return self._live_execute(decision)

    # ------------------------------------------------------------------
    # Paper
    # ------------------------------------------------------------------

    def _paper_execute(self, decision: TradeDecision) -> TradeExecution:
        self.paper_path.parent.mkdir(parents=True, exist_ok=True)
        execution = TradeExecution(
            decision=decision,
            status="executed",
            mode="paper",
            exchange="paper",
            order_id=f"paper_{uuid.uuid4().hex[:12]}",
            message="Paper trade kaydedildi",
            executed_price=decision.token.price_usd,
            executed_amount_usd=decision.amount_usd,
        )
        with self.paper_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(self._serialize_execution(execution), ensure_ascii=False) + "\n")
        self.position_store.apply_execution(decision, mode="paper")
        return execution

    # ------------------------------------------------------------------
    # Live safety guards
    # ------------------------------------------------------------------

    def _live_safety_guard(self, decision: TradeDecision) -> TradeExecution | None:
        if os.getenv("LIVE_TRADING") != "true":
            return self._reject(decision, "LIVE_TRADING=true olmadan live emir kapali")

        if decision.token.symbol.upper() not in self.allowed_symbols:
            return self._reject(decision, "Sembol live trading allowlist disinda")

        if self.exchange != "binance":
            return self._reject(decision, "Sadece binance adapter taslagi var; baska exchange kapali")

        if self.execution_env not in {"testnet", "mainnet"}:
            return self._reject(decision, "EXECUTION_ENV testnet veya mainnet olmali")

        if self.execution_env == "mainnet" and not self.allow_mainnet:
            return self._reject(decision, "ALLOW_MAINNET=true olmadan mainnet emir kapali")

        if self.execution_env == "testnet" and not self.binance_testnet:
            return self._reject(decision, "testnet ortaminda BINANCE_TESTNET=true olmali")

        if decision.amount_usd <= 0 or decision.token.price_usd <= 0:
            return self._reject(decision, "Gecersiz emir tutari veya fiyat")

        return None

    # ------------------------------------------------------------------
    # Live execution
    # ------------------------------------------------------------------

    def _live_execute(self, decision: TradeDecision) -> TradeExecution:
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        if not api_key or not api_secret:
            return self._reject(decision, "BINANCE_API_KEY/BINANCE_API_SECRET yok")

        try:
            import ccxt  # type: ignore
        except ImportError:
            return TradeExecution(
                decision=decision, status="failed", mode="live", exchange=self.exchange,
                message="ccxt kurulu degil; live emir gonderilmedi",
            )

        quote = os.getenv("TRADING_QUOTE_SYMBOL", "USDT")
        market = f"{decision.token.symbol}/{quote}"
        qty = self._quantize_qty(decision.amount_usd / decision.token.price_usd)
        if qty <= 0:
            return self._reject(decision, f"Precision sonrasi gecersiz miktar: qty={qty}")

        try:
            exchange = ccxt.binance({"apiKey": api_key, "secret": api_secret, "enableRateLimit": True})
            if self.execution_env == "testnet":
                exchange.set_sandbox_mode(True)

            position_side = getattr(decision, "position_side", "")
            params: dict = {"newClientOrderId": self._client_order_id(decision)}
            if bool(getattr(decision, "reduce_only", False)):
                params["reduceOnly"] = True
            if position_side in {"long", "short"}:
                params["positionSide"] = position_side.upper()

            order = exchange.create_market_order(market, decision.side, qty, params=params)
            exec_mode = "binance-testnet" if self.execution_env == "testnet" else "binance-mainnet"
            execution = TradeExecution(
                decision=decision, status="executed", mode="live",
                exchange=exec_mode,
                order_id=str(order.get("id", "")),
                message="Live market order gonderildi",
                executed_price=decision.token.price_usd,
                executed_amount_usd=decision.amount_usd,
            )
            self.position_store.apply_execution(decision, mode="live")

            # F6.5 — bracket: SL + TP orders (reduceOnly)
            if not bool(getattr(decision, "reduce_only", False)):
                self._place_bracket(exchange, market, decision.side, qty, decision, position_side)

            return execution
        except Exception as exc:
            return TradeExecution(
                decision=decision, status="failed", mode="live", exchange="binance",
                message=f"Live emir hatasi: {exc}",
            )

    def _place_bracket(self, exchange, market: str, entry_side: str, qty: float,
                       decision: TradeDecision, position_side: str) -> None:
        """Send SL stop-market and TP take-profit-market after entry (best-effort)."""
        exit_side = "sell" if entry_side == "buy" else "buy"
        common: dict = {"reduceOnly": True}
        if position_side in {"long", "short"}:
            common["positionSide"] = position_side.upper()

        if decision.stop_loss_price > 0:
            try:
                sl_price = self._quantize_price(decision.stop_loss_price)
                exchange.create_order(
                    market, "STOP_MARKET", exit_side, qty,
                    params={"stopPrice": sl_price, **common},
                )
            except Exception:
                pass  # bracket failure must not cancel main execution

        if decision.take_profit_price > 0:
            try:
                tp_price = self._quantize_price(decision.take_profit_price)
                exchange.create_order(
                    market, "TAKE_PROFIT_MARKET", exit_side, qty,
                    params={"stopPrice": tp_price, **common},
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _client_order_id(self, decision: TradeDecision) -> str:
        """Stable, deterministic order ID. Prevents duplicate orders on retry."""
        key = (
            f"{decision.token.symbol}:{decision.side}"
            f":{round(decision.amount_usd, 2)}"
            f":{decision.created_at.strftime('%Y%m%d%H%M')}"
        )
        digest = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()
        return f"cas_{digest[:16]}"

    def _quantize_qty(self, qty: float) -> float:
        """Floor quantity to configured precision (conservative — never over-order)."""
        if qty <= 0:
            return 0.0
        factor = 10 ** self.qty_precision
        return math.floor(qty * factor) / factor

    def _quantize_price(self, price: float) -> float:
        """Round price to configured precision."""
        if price <= 0:
            return 0.0
        factor = 10 ** self.price_precision
        return round(price * factor) / factor

    def _reject(self, decision: TradeDecision, message: str) -> TradeExecution:
        return TradeExecution(decision=decision, status="rejected", mode="live", exchange=self.exchange, message=message)

    def _serialize_execution(self, execution: TradeExecution) -> dict:
        data = asdict(execution)
        data["executed_at"] = execution.executed_at.isoformat()
        data["decision"]["created_at"] = execution.decision.created_at.isoformat()
        data["decision"].pop("source_signal", None)
        return data
