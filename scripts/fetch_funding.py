#!/usr/bin/env python3
"""Fetch Binance USD-M futures funding history for research.

Official endpoint used:
- /fapi/v1/fundingRate

This script writes CSV and never sends orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request

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


def fetch_funding(symbol: str, start: datetime, end: datetime, sleep_s: float = 0.15) -> list[dict]:
    out: list[dict] = []
    cursor = ms(start)
    end_ms = ms(end)
    while cursor < end_ms:
        rows = get_json("/fapi/v1/fundingRate", {"symbol": symbol.upper(), "startTime": cursor, "endTime": end_ms, "limit": 1000})
        if not rows:
            break
        out.extend(rows)
        last_time = int(rows[-1]["fundingTime"])
        cursor = last_time + 1
        time.sleep(sleep_s)
    dedup = {int(r["fundingTime"]): r for r in out}
    return [dedup[k] for k in sorted(dedup)]


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["funding_time", "symbol", "funding_rate", "mark_price"])
        for r in rows:
            writer.writerow([
                datetime.fromtimestamp(int(r["fundingTime"]) / 1000, tz=timezone.utc).isoformat(),
                r.get("symbol", ""),
                r.get("fundingRate", ""),
                r.get("markPrice", ""),
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Binance USD-M futures funding history to CSV")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--days", type=int, default=200)
    parser.add_argument("--start", help="UTC ISO start")
    parser.add_argument("--end", help="UTC ISO end, default now")
    parser.add_argument("--out", help="Output CSV path")
    args = parser.parse_args()

    end = parse_utc(args.end) if args.end else datetime.now(timezone.utc)
    start = parse_utc(args.start) if args.start else end - timedelta(days=args.days)
    out = Path(args.out or f"data/funding/{args.symbol.upper()}_{args.days}d.csv")
    rows = fetch_funding(args.symbol, start, end)
    write_csv(rows, out)
    print(f"saved {len(rows)} funding rows -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
