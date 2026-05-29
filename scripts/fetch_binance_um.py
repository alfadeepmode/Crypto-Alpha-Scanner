#!/usr/bin/env python3
"""Fetch Binance USD-M futures klines for research backtests.

Official endpoints used:
- /fapi/v1/klines

This script writes CSV and never sends orders.
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
import json

BASE_URL = "https://fapi.binance.com"


def ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_json(path: str, params: dict) -> list | dict:
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "Crypto-Alpha-Scanner research fetcher"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_klines(symbol: str, interval: str, start: datetime, end: datetime, sleep_s: float = 0.15) -> list[list]:
    out: list[list] = []
    cursor = ms(start)
    end_ms = ms(end)
    while cursor < end_ms:
        rows = get_json("/fapi/v1/klines", {"symbol": symbol.upper(), "interval": interval, "startTime": cursor, "endTime": end_ms, "limit": 1500})
        if not rows:
            break
        out.extend(rows)
        last_open = int(rows[-1][0])
        next_cursor = last_open + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(sleep_s)
    # Deduplicate by open time.
    dedup = {int(r[0]): r for r in out}
    return [dedup[k] for k in sorted(dedup)]


def write_csv(rows: list[list], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([
                datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc).isoformat(),
                r[1], r[2], r[3], r[4], r[5],
                datetime.fromtimestamp(int(r[6]) / 1000, tz=timezone.utc).isoformat(),
                r[7], r[8], r[9], r[10], r[11],
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Binance USD-M futures klines to CSV")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--days", type=int, default=200)
    parser.add_argument("--start", help="UTC ISO start, e.g. 2025-01-01T00:00:00Z")
    parser.add_argument("--end", help="UTC ISO end, default now")
    parser.add_argument("--out", help="Output CSV path")
    args = parser.parse_args()

    end = parse_utc(args.end) if args.end else datetime.now(timezone.utc)
    start = parse_utc(args.start) if args.start else end - timedelta(days=args.days)
    out = Path(args.out or f"data/klines/{args.symbol.upper()}_{args.interval}_{args.days}d.csv")

    rows = fetch_klines(args.symbol, args.interval, start, end)
    write_csv(rows, out)
    print(f"saved {len(rows)} klines -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
