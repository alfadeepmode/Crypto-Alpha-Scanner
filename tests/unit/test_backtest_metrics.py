"""F4.6/F4.7: Backtest metrics correctness and acceptance gate."""

import json
import math
import pytest
from backtesting.metrics import calculate_metrics, max_drawdown, BacktestMetrics
from scripts.validate_backtest_report import evaluate


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

def test_max_drawdown_no_loss():
    curve = [1000.0, 1100.0, 1200.0, 1300.0]
    dd, dd_pct = max_drawdown(curve)
    assert dd == pytest.approx(0.0)
    assert dd_pct == pytest.approx(0.0)


def test_max_drawdown_single_drop():
    curve = [1000.0, 900.0]
    dd, dd_pct = max_drawdown(curve)
    assert dd == pytest.approx(100.0)
    assert dd_pct == pytest.approx(10.0)


def test_max_drawdown_recovery():
    # Peak=1200, drops to 900 (-300, -25%), then recovers and falls to 1100 (-100)
    curve = [1000.0, 1200.0, 900.0, 1300.0, 1100.0]
    dd, dd_pct = max_drawdown(curve)
    assert dd == pytest.approx(300.0)
    assert dd_pct == pytest.approx(25.0)


def test_max_drawdown_empty():
    dd, dd_pct = max_drawdown([])
    assert dd == 0.0
    assert dd_pct == 0.0


# ---------------------------------------------------------------------------
# calculate_metrics
# ---------------------------------------------------------------------------

def test_perfect_record():
    """All wins → PF=999 sentinel, win_rate=100."""
    pnls = [10.0, 20.0, 5.0]
    curve = [1000.0, 1010.0, 1030.0, 1035.0]
    m = calculate_metrics(pnls, curve, 1000.0)
    assert m.win_rate_pct == pytest.approx(100.0)
    assert m.profit_factor == pytest.approx(999.0)
    assert m.expectancy_usd == pytest.approx(35.0 / 3, rel=1e-6)
    assert m.trade_count == 3
    assert m.losing_trades == 0


def test_all_losses():
    """All losses → PF=0, win_rate=0."""
    pnls = [-5.0, -3.0, -7.0]
    curve = [1000.0, 995.0, 992.0, 985.0]
    m = calculate_metrics(pnls, curve, 1000.0)
    assert m.win_rate_pct == pytest.approx(0.0)
    assert m.profit_factor == pytest.approx(0.0)
    assert m.expectancy_usd < 0
    assert m.winning_trades == 0


def test_mixed_trades():
    pnls = [20.0, -5.0, 10.0, -2.0]
    curve = [1000.0, 1020.0, 1015.0, 1025.0, 1023.0]
    m = calculate_metrics(pnls, curve, 1000.0)
    assert m.trade_count == 4
    assert m.winning_trades == 2
    assert m.losing_trades == 2
    assert m.win_rate_pct == pytest.approx(50.0)
    assert m.profit_factor == pytest.approx(30.0 / 7.0, rel=1e-4)
    assert m.net_profit_usd == pytest.approx(23.0, rel=1e-4)


def test_empty_trades():
    m = calculate_metrics([], [1000.0], 1000.0)
    assert m.trade_count == 0
    assert m.net_profit_usd == pytest.approx(0.0)
    assert m.profit_factor == pytest.approx(0.0)
    assert m.win_rate_pct == pytest.approx(0.0)


def test_expectancy_formula():
    """expectancy = sum(pnls) / count."""
    pnls = [10.0, -5.0, 15.0, -3.0]
    curve = [1000.0] * 5
    m = calculate_metrics(pnls, curve, 1000.0)
    assert m.expectancy_usd == pytest.approx(sum(pnls) / len(pnls), rel=1e-6)


def test_net_profit_pct():
    pnls = [100.0]
    curve = [1000.0, 1100.0]
    m = calculate_metrics(pnls, curve, 1000.0)
    assert m.net_profit_usd == pytest.approx(100.0)
    assert m.net_profit_pct == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# F4.7  Validate backtest report acceptance gate
# ---------------------------------------------------------------------------

def _make_report(profit_factor=1.5, drawdown_pct=10.0, trades=150, expectancy=5.0):
    return {
        "metrics": {
            "profit_factor": profit_factor,
            "max_drawdown_pct": drawdown_pct,
            "trade_count": trades,
            "expectancy_usd": expectancy,
        }
    }


def test_gate_passes_good_report():
    report = _make_report(profit_factor=1.5, drawdown_pct=10.0, trades=150, expectancy=5.0)
    ok, failures = evaluate(report, 1.15, 20.0, 100, True)
    assert ok
    assert failures == []


def test_gate_fails_low_profit_factor():
    report = _make_report(profit_factor=1.0)
    ok, failures = evaluate(report, 1.15, 20.0, 100, True)
    assert not ok
    assert any("profit_factor" in f for f in failures)


def test_gate_fails_high_drawdown():
    report = _make_report(drawdown_pct=25.0)
    ok, failures = evaluate(report, 1.15, 20.0, 100, True)
    assert not ok
    assert any("drawdown" in f for f in failures)


def test_gate_fails_low_trade_count():
    report = _make_report(trades=50)
    ok, failures = evaluate(report, 1.15, 20.0, 100, True)
    assert not ok
    assert any("trade_count" in f for f in failures)


def test_gate_fails_negative_expectancy():
    report = _make_report(expectancy=-1.0)
    ok, failures = evaluate(report, 1.15, 20.0, 100, True)
    assert not ok
    assert any("expectancy" in f for f in failures)


def test_gate_allows_negative_expectancy_when_flag_set():
    report = _make_report(expectancy=-0.1)
    ok, failures = evaluate(report, 1.15, 20.0, 100, False)  # allow_negative=True
    # only fails if other criteria fail; expectancy is allowed
    expectancy_failures = [f for f in failures if "expectancy" in f]
    assert expectancy_failures == []
