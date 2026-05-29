"""Exchange executor - varsayilan paper trading, live mod fail-closed.

Faz 5 ilkesi: mainnet varsayilan olarak kapali kalir. Live path sadece testnet
veya acikca izin verilmis mainnet kosullarinda ilerler.
"""

import json
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

    def execute_batch(self, decisions: list[TradeDecision]) -> list[TradeExecution]:
        return [self.execute(decision) for decision in decisions if decision.side != "hold"]

    def execute(self, decision: TradeDecision) -> TradeExecution:
        if decision.side == "hold":
            return TradeExecution(decision=decision, status="skipped", mode=self.mode, exchange=self.exchange, message=decision.reason)

        if self.mode != "live":
            return self._paper_execute(decision)

        guard = self._live_safety_guard(decision)
        if guard is not None:
            return guard

        return self._live_execute(decision)

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

    def _reject(self, decision: TradeDecision, message: str) -> TradeExecution:
        return TradeExecution(decision=decision, status="rejected", mode="live", exchange=self.exchange, message=message)

    def _live_execute(self, decision: TradeDecision) -> TradeExecution:
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        if not api_key or not api_secret:
            return self._reject(decision, "BINANCE_API_KEY/BINANCE_API_SECRET yok")

        try:
            import ccxt  # type: ignore
        except ImportError:
            return TradeExecution(
                decision=decision,
                status="failed",
                mode="live",
                exchange=self.exchange,
                message="ccxt kurulu degil; live emir gonderilmedi",
            )

        quote = os.getenv("TRADING_QUOTE_SYMBOL", "USDT")
        market = f"{decision.token.symbol}/{quote}"
        try:
            exchange = ccxt.binance({"apiKey": api_key, "secret": api_secret, "enableRateLimit": True})
            if self.execution_env == "testnet":
                exchange.set_sandbox_mode(True)
            amount = decision.amount_usd / decision.token.price_usd
            params = {}
            if bool(getattr(decision, "reduce_only", False)):
                params["reduceOnly"] = True
            position_side = getattr(decision, "position_side", "")
            if position_side in {"long", "short"}:
                params["positionSide"] = position_side.upper()
            order = exchange.create_market_order(market, decision.side, amount, params=params)
            execution = TradeExecution(
                decision=decision,
                status="executed",
                mode="live",
                exchange="binance-testnet" if self.execution_env == "testnet" else "binance-mainnet",
                order_id=str(order.get("id", "")),
                message="Live market order gonderildi",
                executed_price=decision.token.price_usd,
                executed_amount_usd=decision.amount_usd,
            )
            self.position_store.apply_execution(decision, mode="live")
            return execution
        except Exception as exc:
            return TradeExecution(
                decision=decision,
                status="failed",
                mode="live",
                exchange="binance",
                message=f"Live emir hatasi: {exc}",
            )

    def _serialize_execution(self, execution: TradeExecution) -> dict:
        data = asdict(execution)
        data["executed_at"] = execution.executed_at.isoformat()
        data["decision"]["created_at"] = execution.decision.created_at.isoformat()
        data["decision"].pop("source_signal", None)
        return data
