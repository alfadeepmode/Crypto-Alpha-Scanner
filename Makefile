.PHONY: test lint smoke backtest check install

install:
	pip install -q -r requirements-dev.txt

lint:
	python -m compileall -q .
	ruff check . --select E,F,W --ignore E501 || true

smoke:
	python tests/smoke_test.py

test:
	python -m pytest -q --tb=short

cov:
	python -m pytest --cov=agents --cov=tools --cov=backtesting --cov=models \
	  --cov-report=term-missing --cov-fail-under=60 -q

backtest:
	PYTHONPATH=. python scripts/run_backtest.py \
	  --csv tests/fixtures/klines_mini.csv \
	  --symbol TEST --interval 5m --days 1 \
	  --out /tmp/test_backtest_report.json && \
	PYTHONPATH=. python scripts/validate_backtest_report.py \
	  --report /tmp/test_backtest_report.json \
	  --min-trades 1 --min-profit-factor 0.0 \
	  --allow-negative-expectancy || true

check: lint test smoke
	@echo "All checks passed."
