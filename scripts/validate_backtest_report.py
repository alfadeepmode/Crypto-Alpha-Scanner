#!/usr/bin/env python3
"""Validate a backtest report against scientific acceptance gates.

This script never sends orders. It only reads a JSON report produced by
scripts/run_backtest.py and exits non-zero when the report fails the minimum
research gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_report(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate(report: dict, min_profit_factor: float, max_drawdown_pct: float, min_trades: int, require_positive_expectancy: bool) -> tuple[bool, list[str]]:
    metrics = report.get("metrics", {})
    failures: list[str] = []

    profit_factor = float(metrics.get("profit_factor", 0.0) or 0.0)
    drawdown = float(metrics.get("max_drawdown_pct", 999.0) or 999.0)
    trades = int(metrics.get("trade_count", 0) or 0)
    expectancy = float(metrics.get("expectancy_usd", 0.0) or 0.0)

    if profit_factor < min_profit_factor:
        failures.append(f"profit_factor {profit_factor:.4f} < required {min_profit_factor:.4f}")
    if drawdown > max_drawdown_pct:
        failures.append(f"max_drawdown_pct {drawdown:.4f} > allowed {max_drawdown_pct:.4f}")
    if trades < min_trades:
        failures.append(f"trade_count {trades} < required {min_trades}")
    if require_positive_expectancy and expectancy <= 0:
        failures.append(f"expectancy_usd {expectancy:.6f} <= 0")

    return len(failures) == 0, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate backtest report acceptance gate")
    parser.add_argument("--report", required=True, help="Backtest JSON report path")
    parser.add_argument("--min-profit-factor", type=float, default=1.15)
    parser.add_argument("--max-drawdown-pct", type=float, default=20.0)
    parser.add_argument("--min-trades", type=int, default=100)
    parser.add_argument("--allow-negative-expectancy", action="store_true")
    args = parser.parse_args()

    report = load_report(args.report)
    ok, failures = evaluate(
        report,
        min_profit_factor=args.min_profit_factor,
        max_drawdown_pct=args.max_drawdown_pct,
        min_trades=args.min_trades,
        require_positive_expectancy=not args.allow_negative_expectancy,
    )

    print(f"report: {args.report}")
    print(f"symbol: {report.get('symbol', '-')}")
    print(f"interval: {report.get('interval', '-')}")
    print(f"days: {report.get('days', '-')}")
    print("gate: PASS" if ok else "gate: FAIL")
    if failures:
        print("failures:")
        for failure in failures:
            print(f"- {failure}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
