#!/usr/bin/env python3
"""Run an offline research backtest from a local kline CSV.

Example:
  python scripts/run_backtest.py --csv data/klines/BTCUSDT_5m_200d.csv --symbol BTCUSDT --interval 5m --days 200
"""

from __future__ import annotations

import argparse
from pathlib import Path

from backtesting.engine import BacktestConfig, load_klines_csv, run_backtest, save_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Micro Atomic research backtest")
    parser.add_argument("--csv", required=True, help="Kline CSV from scripts/fetch_binance_um.py")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--days", type=int, default=200)
    parser.add_argument("--initial-capital", type=float, default=1000.0)
    parser.add_argument("--position-pct", type=float, default=20.0)
    parser.add_argument("--min-score", type=float, default=80.0)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--funding-bps", type=float, default=1.0)
    parser.add_argument("--out", help="Report JSON path")
    args = parser.parse_args()

    cfg = BacktestConfig(
        initial_capital=args.initial_capital,
        position_pct=args.position_pct,
        min_score_pct=args.min_score,
        taker_fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        funding_bps_per_trade=args.funding_bps,
    )
    rows = load_klines_csv(args.csv)
    report = run_backtest(rows, cfg)
    report["symbol"] = args.symbol.upper()
    report["interval"] = args.interval
    report["days"] = args.days
    report["source_csv"] = str(Path(args.csv))

    out = Path(args.out or f"reports/{args.symbol.upper()}_{args.interval}_{args.days}d_backtest.json")
    save_report(report, out)

    metrics = report["metrics"]
    print("Backtest complete")
    print(f"report: {out}")
    print(f"net_profit_usd: {metrics['net_profit_usd']}")
    print(f"net_profit_pct: {metrics['net_profit_pct']}")
    print(f"max_drawdown_pct: {metrics['max_drawdown_pct']}")
    print(f"win_rate_pct: {metrics['win_rate_pct']}")
    print(f"profit_factor: {metrics['profit_factor']}")
    print(f"expectancy_usd: {metrics['expectancy_usd']}")
    print(f"trade_count: {metrics['trade_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
