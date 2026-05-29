"""Micro Atomic research backtest engine.

This engine is for offline scientific validation only. It never sends orders.
It uses next-bar open fills, ATR-based SL/TP, fee, slippage, and optional
funding-cost approximation.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from backtesting.metrics import calculate_metrics


@dataclass
class BacktestConfig:
    initial_capital: float = 1000.0
    position_pct: float = 20.0
    ema_fast: int = 50
    ema_slow: int = 200
    rsi_len: int = 7
    rsi_long_min: float = 52.0
    rsi_long_max: float = 78.0
    rsi_short_min: float = 22.0
    rsi_short_max: float = 48.0
    atr_len: int = 14
    min_atr_pct: float = 0.20
    vol_len: int = 20
    min_vol_ratio: float = 1.20
    adx_len: int = 14
    adx_threshold: float = 20.0
    min_score_pct: float = 80.0
    sl_atr_mult: float = 1.2
    tp_atr_mult: float = 1.8
    taker_fee_bps: float = 5.0
    slippage_bps: float = 3.0
    funding_bps_per_trade: float = 1.0


@dataclass
class Trade:
    side: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    qty: float
    gross_pnl_usd: float
    fee_usd: float
    slippage_usd: float
    funding_usd: float
    net_pnl_usd: float
    exit_reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def load_klines_csv(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "open_time": row.get("open_time") or row.get("timestamp") or row.get("time"),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
    return rows


def sma(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if length <= 0:
        return out
    rolling = 0.0
    for i, value in enumerate(values):
        rolling += value
        if i >= length:
            rolling -= values[i - length]
        if i >= length - 1:
            out[i] = rolling / length
    return out


def ema(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if not values or length <= 0:
        return out
    alpha = 2 / (length + 1)
    seed = values[0]
    for i, value in enumerate(values):
        seed = value if i == 0 else alpha * value + (1 - alpha) * seed
        if i >= length - 1:
            out[i] = seed
    return out


def rsi(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= length:
        return out
    gains = [0.0] * len(values)
    losses = [0.0] * len(values)
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains[i] = max(diff, 0.0)
        losses[i] = max(-diff, 0.0)
    avg_gain = sum(gains[1:length + 1]) / length
    avg_loss = sum(losses[1:length + 1]) / length
    out[length] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(length + 1, len(values)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], length: int) -> list[float | None]:
    tr: list[float] = []
    for i in range(len(closes)):
        prev_close = closes[i - 1] if i > 0 else closes[i]
        tr.append(max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close)))
    return ema(tr, length)


def dmi_adx(highs: list[float], lows: list[float], closes: list[float], length: int) -> list[float | None]:
    plus_dm = [0.0] * len(closes)
    minus_dm = [0.0] * len(closes)
    tr = [0.0] * len(closes)
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr_vals = ema(tr, length)
    plus_s = ema(plus_dm, length)
    minus_s = ema(minus_dm, length)
    dx = [0.0] * len(closes)
    for i in range(len(closes)):
        if atr_vals[i] and atr_vals[i] > 0 and plus_s[i] is not None and minus_s[i] is not None:
            pdi = 100 * plus_s[i] / atr_vals[i]
            mdi = 100 * minus_s[i] / atr_vals[i]
            denom = pdi + mdi
            dx[i] = 100 * abs(pdi - mdi) / denom if denom > 0 else 0.0
    return ema(dx, length)


def macd_hist(values: list[float], fast: int = 5, slow: int = 13, signal: int = 5) -> list[float | None]:
    fast_e = ema(values, fast)
    slow_e = ema(values, slow)
    line = [None if fast_e[i] is None or slow_e[i] is None else fast_e[i] - slow_e[i] for i in range(len(values))]
    safe_line = [x if x is not None else 0.0 for x in line]
    sig = ema(safe_line, signal)
    return [None if line[i] is None or sig[i] is None else line[i] - sig[i] for i in range(len(values))]


def run_backtest(rows: list[dict[str, Any]], cfg: BacktestConfig) -> dict[str, Any]:
    closes = [r["close"] for r in rows]
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    opens = [r["open"] for r in rows]
    volumes = [r["volume"] for r in rows]

    ema_fast = ema(closes, cfg.ema_fast)
    ema_slow = ema(closes, cfg.ema_slow)
    rsi_vals = rsi(closes, cfg.rsi_len)
    atr_vals = atr(highs, lows, closes, cfg.atr_len)
    vol_avg = sma(volumes, cfg.vol_len)
    adx_vals = dmi_adx(highs, lows, closes, cfg.adx_len)
    hist = macd_hist(closes)

    equity = cfg.initial_capital
    equity_curve = [equity]
    trades: list[Trade] = []
    position: dict[str, Any] | None = None

    def friction(notional: float) -> tuple[float, float, float]:
        fee = notional * 2 * cfg.taker_fee_bps / 10000
        slip = notional * 2 * cfg.slippage_bps / 10000
        funding = notional * cfg.funding_bps_per_trade / 10000
        return fee, slip, funding

    start_i = max(cfg.ema_slow, cfg.atr_len, cfg.vol_len, cfg.adx_len) + 2
    for i in range(start_i, len(rows) - 1):
        if any(x is None for x in [ema_fast[i], ema_slow[i], rsi_vals[i], atr_vals[i], vol_avg[i], adx_vals[i], hist[i], hist[i - 1]]):
            equity_curve.append(equity)
            continue

        price = closes[i]
        atr_now = atr_vals[i] or 0.0
        atr_pct = atr_now / price * 100 if price > 0 else 0.0
        vol_ratio = volumes[i] / vol_avg[i] if vol_avg[i] and vol_avg[i] > 0 else 0.0
        trend_long = ema_fast[i] > ema_slow[i] and price > ema_fast[i]
        trend_short = ema_fast[i] < ema_slow[i] and price < ema_fast[i]
        rsi_long_ok = cfg.rsi_long_min <= rsi_vals[i] <= cfg.rsi_long_max
        rsi_short_ok = cfg.rsi_short_min <= rsi_vals[i] <= cfg.rsi_short_max
        macd_long = hist[i] > 0 and hist[i] > hist[i - 1]
        macd_short = hist[i] < 0 and hist[i] < hist[i - 1]
        atr_ok = atr_pct >= cfg.min_atr_pct
        vol_ok = vol_ratio >= cfg.min_vol_ratio
        adx_ok = adx_vals[i] >= cfg.adx_threshold

        long_score = sum([trend_long, rsi_long_ok, vol_ok, adx_ok, macd_long])
        short_score = sum([trend_short, rsi_short_ok, vol_ok, adx_ok, macd_short])
        long_pct = long_score / 5 * 100
        short_pct = short_score / 5 * 100
        long_signal = atr_ok and long_pct >= cfg.min_score_pct and long_score > short_score
        short_signal = atr_ok and short_pct >= cfg.min_score_pct and short_score > long_score

        # Exit first using intrabar SL/TP assumptions.
        if position:
            side = position["side"]
            exit_price = None
            exit_reason = ""
            if side == "long":
                if lows[i] <= position["stop"]:
                    exit_price = position["stop"]
                    exit_reason = "stop"
                elif highs[i] >= position["take"]:
                    exit_price = position["take"]
                    exit_reason = "take"
                elif short_signal:
                    exit_price = opens[i + 1]
                    exit_reason = "reverse"
            else:
                if highs[i] >= position["stop"]:
                    exit_price = position["stop"]
                    exit_reason = "stop"
                elif lows[i] <= position["take"]:
                    exit_price = position["take"]
                    exit_reason = "take"
                elif long_signal:
                    exit_price = opens[i + 1]
                    exit_reason = "reverse"

            if exit_price is not None:
                qty = position["qty"]
                entry = position["entry_price"]
                notional = position["notional"]
                gross = (exit_price - entry) * qty if side == "long" else (entry - exit_price) * qty
                fee, slip, funding = friction(notional)
                net = gross - fee - slip - funding
                equity += net
                trades.append(Trade(side, position["entry_time"], str(rows[i]["open_time"]), entry, exit_price, qty, gross, fee, slip, funding, net, exit_reason))
                position = None

        # Entry on next bar open after signal.
        if position is None and (long_signal or short_signal):
            entry_price = opens[i + 1]
            notional = equity * cfg.position_pct / 100
            qty = notional / entry_price if entry_price > 0 else 0.0
            if qty > 0:
                if long_signal:
                    position = {"side": "long", "entry_time": str(rows[i + 1]["open_time"]), "entry_price": entry_price, "qty": qty, "notional": notional, "stop": entry_price - atr_now * cfg.sl_atr_mult, "take": entry_price + atr_now * cfg.tp_atr_mult}
                elif short_signal:
                    position = {"side": "short", "entry_time": str(rows[i + 1]["open_time"]), "entry_price": entry_price, "qty": qty, "notional": notional, "stop": entry_price + atr_now * cfg.sl_atr_mult, "take": entry_price - atr_now * cfg.tp_atr_mult}

        equity_curve.append(equity)

    if position:
        exit_price = closes[-1]
        qty = position["qty"]
        entry = position["entry_price"]
        notional = position["notional"]
        gross = (exit_price - entry) * qty if position["side"] == "long" else (entry - exit_price) * qty
        fee, slip, funding = friction(notional)
        net = gross - fee - slip - funding
        equity += net
        trades.append(Trade(position["side"], position["entry_time"], str(rows[-1]["open_time"]), entry, exit_price, qty, gross, fee, slip, funding, net, "end_of_data"))
        equity_curve.append(equity)

    metrics = calculate_metrics([t.net_pnl_usd for t in trades], equity_curve, cfg.initial_capital)
    return {
        "config": asdict(cfg),
        "metrics": metrics.to_dict(),
        "trades": [t.to_dict() for t in trades],
        "equity_curve": equity_curve,
    }


def save_report(report: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
