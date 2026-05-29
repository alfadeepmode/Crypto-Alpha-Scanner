"""Backtest metrics for research mode.

No live trading. These functions evaluate closed trades and equity curves.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable


@dataclass
class BacktestMetrics:
    net_profit_usd: float
    net_profit_pct: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    expectancy_usd: float
    trade_count: int
    winning_trades: int
    losing_trades: int
    avg_win_usd: float
    avg_loss_usd: float
    sharpe_like: float

    def to_dict(self) -> dict:
        return asdict(self)


def max_drawdown(equity_curve: list[float]) -> tuple[float, float]:
    if not equity_curve:
        return 0.0, 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        dd = peak - equity
        dd_pct = dd / peak * 100 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct
    return max_dd, max_dd_pct


def calculate_metrics(trade_pnls: Iterable[float], equity_curve: list[float], initial_capital: float) -> BacktestMetrics:
    pnls = [float(x) for x in trade_pnls]
    final_equity = equity_curve[-1] if equity_curve else initial_capital
    net_profit = final_equity - initial_capital
    net_profit_pct = net_profit / initial_capital * 100 if initial_capital > 0 else 0.0

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    trade_count = len(pnls)
    win_rate = len(wins) / trade_count * 100 if trade_count else 0.0
    expectancy = sum(pnls) / trade_count if trade_count else 0.0
    avg_win = mean(wins) if wins else 0.0
    avg_loss = mean(losses) if losses else 0.0
    dd_usd, dd_pct = max_drawdown(equity_curve)

    returns = []
    for prev, cur in zip(equity_curve, equity_curve[1:]):
        if prev > 0:
            returns.append((cur - prev) / prev)
    sharpe_like = 0.0
    if len(returns) > 2:
        sigma = pstdev(returns)
        if sigma > 0:
            sharpe_like = mean(returns) / sigma * sqrt(len(returns))

    return BacktestMetrics(
        net_profit_usd=round(net_profit, 6),
        net_profit_pct=round(net_profit_pct, 6),
        max_drawdown_usd=round(dd_usd, 6),
        max_drawdown_pct=round(dd_pct, 6),
        win_rate_pct=round(win_rate, 6),
        profit_factor=round(profit_factor, 6),
        expectancy_usd=round(expectancy, 6),
        trade_count=trade_count,
        winning_trades=len(wins),
        losing_trades=len(losses),
        avg_win_usd=round(avg_win, 6),
        avg_loss_usd=round(avg_loss, 6),
        sharpe_like=round(sharpe_like, 6),
    )
