#!/usr/bin/env python3
"""Local dashboard for Crypto Alpha Scanner."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def latest_report() -> dict:
    reports = sorted((ROOT / "reports").glob("*_backtest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        return {}
    data = load_json(reports[0])
    data["report_path"] = str(reports[0].relative_to(ROOT))
    return data


def tail_jsonl(path: Path, limit: int = 50) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]:
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return rows


HTML = """
<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Crypto Alpha Scanner</title>
<style>
:root{color-scheme:dark;--bg:#0f1115;--panel:#171a21;--panel2:#1f2430;--line:#303644;--text:#eceff4;--muted:#9aa4b2;--green:#2ec27e;--red:#ff6b6b;--yellow:#f6c85f;--blue:#7aa2ff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Inter,system-ui,sans-serif}header{border-bottom:1px solid var(--line);background:#11141a}.bar,main{max-width:1400px;margin:0 auto}.bar{padding:16px 20px;display:flex;justify-content:space-between;gap:16px;align-items:center}main{padding:20px}h1{margin:0;font-size:20px}h2{margin:0 0 12px;font-size:14px}.sub,.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;min-width:0}.s3{grid-column:span 3}.s4{grid-column:span 4}.s5{grid-column:span 5}.s6{grid-column:span 6}.s7{grid-column:span 7}.s8{grid-column:span 8}.s12{grid-column:span 12}.metric{font-size:24px;font-weight:750}.row{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid rgba(255,255,255,.07)}.row:first-child{border-top:0}.badge{border:1px solid var(--line);background:var(--panel2);border-radius:999px;padding:4px 8px;font-size:12px;font-weight:650;white-space:nowrap}.ok{color:var(--green)}.warn{color:var(--yellow)}.bad{color:var(--red)}.info{color:var(--blue)}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{text-align:left;padding:9px 8px;border-top:1px solid rgba(255,255,255,.07);overflow-wrap:anywhere;vertical-align:top}th{color:var(--muted);font-size:12px}button{border:1px solid var(--line);background:var(--panel2);color:var(--text);border-radius:7px;padding:8px 10px;cursor:pointer}pre{margin:0;white-space:pre-wrap;color:#d6dbe7}.tiny{font-size:12px}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}@media(max-width:900px){.s3,.s4,.s5,.s6,.s7,.s8{grid-column:span 12}.bar{align-items:flex-start;flex-direction:column}}
</style></head><body>
<header><div class="bar"><div><h1>Crypto Alpha Scanner</h1><div class="sub">Orkestrasyon, probability model, paper/testnet güvenlik ve backtest gözlemi</div></div><button onclick="refresh()">Yenile</button></div></header>
<main><section class="grid">
<div class="panel s3"><h2>Trade Modu</h2><div id="tradeMode" class="metric">-</div><div id="liveState" class="muted">-</div></div>
<div class="panel s3"><h2>Execution Env</h2><div id="execEnv" class="metric">-</div><div id="mainnetState" class="muted">-</div></div>
<div class="panel s3"><h2>Son Kararlar</h2><div id="decisionCount" class="metric">0</div><div class="muted">Orkestrasyon log satırı</div></div>
<div class="panel s3"><h2>Paper Emir</h2><div id="paperCount" class="metric">0</div><div class="muted">Simülasyon emri</div></div>
<div class="panel s4"><h2>API Durumu</h2><div id="apiRows"></div></div>
<div class="panel s4"><h2>Güvenlik Kilitleri</h2><div id="guardRows"></div></div>
<div class="panel s4"><h2>Son Backtest</h2><div id="backtestRows"></div></div>
<div class="panel s6"><h2>Açık Pozisyonlar</h2><table><thead><tr><th>Sembol</th><th>Taraf</th><th>Qty</th><th>Avg</th><th>PnL</th></tr></thead><tbody id="positionRows"></tbody></table></div>
<div class="panel s6"><h2>Son Model Sinyalleri</h2><table><thead><tr><th>Zaman</th><th>Sembol</th><th>p↑</th><th>p↓</th><th>Hash</th></tr></thead><tbody id="modelRows"></tbody></table></div>
<div class="panel s7"><h2>Son Orkestrasyon</h2><table><thead><tr><th>Zaman</th><th>Sembol</th><th>Sinyal</th><th>Karar</th><th>RR</th><th>Durum</th></tr></thead><tbody id="orchRows"></tbody></table></div>
<div class="panel s5"><h2>Reddedilen / Hold Kararlar</h2><table><thead><tr><th>Zaman</th><th>Sembol</th><th>Karar</th><th>Sebep</th></tr></thead><tbody id="rejectRows"></tbody></table></div>
<div class="panel s12"><h2>Komutlar</h2><pre>python main.py --setup
python main.py --trade
python dashboard.py
python scripts/fetch_binance_um.py --symbol BTCUSDT --interval 5m --days 200
python scripts/run_backtest.py --csv data/klines/BTCUSDT_5m_200d.csv --symbol BTCUSDT --interval 5m --days 200</pre></div>
</section></main>
<script>
function badge(text, cls){return `<span class="badge ${cls||''}">${text}</span>`}function fmt(v){return v===undefined||v===null||v===''?'-':v}function pct(v){return v===undefined||v===null?'-':Number(v).toFixed(2)}
async function refresh(){const d=await fetch('/api/status').then(r=>r.json());const t=d.config.trading||{};document.getElementById('tradeMode').textContent=d.env.TRADING_MODE||t.mode||'paper';document.getElementById('liveState').innerHTML=d.env.LIVE_TRADING==='true'?badge('LIVE açık','bad'):badge('Live kilitli','ok');document.getElementById('execEnv').textContent=d.env.EXECUTION_ENV||t.execution_env||'testnet';document.getElementById('mainnetState').innerHTML=(d.env.ALLOW_MAINNET==='true'||t.allow_mainnet===true)?badge('Mainnet izinli','bad'):badge('Mainnet kilitli','ok');document.getElementById('decisionCount').textContent=d.orchestration.length;document.getElementById('paperCount').textContent=d.paperTrades.length;const keys=['OPENROUTER_API_KEY','OPENAI_API_KEY','GROQ_API_KEY','GITHUB_TOKEN','TELEGRAM_BOT_TOKEN','BINANCE_API_KEY','BINANCE_API_SECRET'];document.getElementById('apiRows').innerHTML=keys.map(k=>`<div class="row"><span>${k}</span>${badge(d.api[k]?'var':'yok',d.api[k]?'ok':'warn')}</div>`).join('');document.getElementById('guardRows').innerHTML=[['mode',d.env.TRADING_MODE||t.mode],['live',d.env.LIVE_TRADING==='true'?'true':'false'],['execution_env',d.env.EXECUTION_ENV||t.execution_env],['allow_mainnet',String(d.env.ALLOW_MAINNET||t.allow_mainnet)],['binance_testnet',String(d.env.BINANCE_TESTNET||t.binance_testnet)]].map(r=>`<div class="row"><span>${r[0]}</span>${badge(r[1],r[1]==='true'&&r[0].includes('mainnet')?'bad':'info')}</div>`).join('');const bt=d.backtest?.metrics||{};document.getElementById('backtestRows').innerHTML=d.backtest?.report_path?[['report',d.backtest.report_path],['net',bt.net_profit_usd],['dd%',bt.max_drawdown_pct],['pf',bt.profit_factor],['exp',bt.expectancy_usd],['trades',bt.trade_count]].map(r=>`<div class="row"><span>${r[0]}</span><span class="mono">${fmt(r[1])}</span></div>`).join(''):'<div class="muted">Rapor yok</div>';const pos=Object.values(d.positions.positions||{});document.getElementById('positionRows').innerHTML=pos.slice(-20).map(p=>`<tr><td>${fmt(p.symbol)}</td><td>${fmt(p.position_side||'long')}</td><td>${pct(p.qty)}</td><td>${pct(p.avg_entry_price)}</td><td>${pct(p.realized_pnl_usd)}</td></tr>`).join('');document.getElementById('modelRows').innerHTML=d.orchestration.slice(-20).reverse().map(r=>`<tr><td>${fmt(r.at)}</td><td>${fmt(r.symbol)}</td><td>${pct(r.prob_up)}</td><td>${pct(r.prob_down)}</td><td class="mono tiny">${fmt(r.feature_hash)}</td></tr>`).join('');document.getElementById('orchRows').innerHTML=d.orchestration.slice(-20).reverse().map(r=>`<tr><td>${fmt(r.at)}</td><td>${fmt(r.symbol)}</td><td>${fmt(r.signal_side||r.signal_action)}</td><td>${fmt(r.decision)}</td><td>${pct(r.expected_reward_risk)}</td><td>${fmt(r.execution_status)}</td></tr>`).join('');document.getElementById('rejectRows').innerHTML=d.orchestration.filter(r=>r.decision==='hold'||r.reject_reason).slice(-20).reverse().map(r=>`<tr><td>${fmt(r.at)}</td><td>${fmt(r.symbol)}</td><td>${fmt(r.decision)}</td><td>${fmt(r.reject_reason||r.trace?.slice(-2)?.[0]?.detail)}</td></tr>`).join('')}
refresh();setInterval(refresh,5000);
</script></body></html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, HTML, "text/html; charset=utf-8")
        elif path == "/api/status":
            self._json(self.status_payload())
        else:
            self.send_error(404)

    def status_payload(self) -> dict:
        config = load_yaml(ROOT / "config.yaml")
        trading = config.get("trading", {})
        orch_path = ROOT / config.get("orchestration", {}).get("log_path", "data/orchestration_log.jsonl")
        paper_path = ROOT / os.getenv("PAPER_TRADES_PATH", trading.get("paper_trades_path", "data/paper_trades.jsonl"))
        pos_path = ROOT / os.getenv("POSITION_STATE_PATH", trading.get("position_state_path", "data/positions.json"))
        keys = ["OPENROUTER_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN", "BINANCE_API_KEY", "BINANCE_API_SECRET", "ETHERSCAN_API_KEY", "WHALE_ALERT_API_KEY"]
        env_keys = ["TRADING_MODE", "TRADING_EXCHANGE", "LIVE_TRADING", "EXECUTION_ENV", "ALLOW_MAINNET", "BINANCE_TESTNET", "TRADINGVIEW_WEBHOOK_HOST", "TRADINGVIEW_WEBHOOK_PORT"]
        return {"config": config, "api": {k: bool(os.getenv(k, "").strip()) for k in keys}, "env": {k: os.getenv(k, "") for k in env_keys}, "orchestration": tail_jsonl(orch_path), "paperTrades": tail_jsonl(paper_path), "positions": load_json(pos_path), "backtest": latest_report()}

    def _json(self, body: dict):
        self._send(200, json.dumps(body, ensure_ascii=False), "application/json; charset=utf-8")

    def _send(self, status: int, body: str, content_type: str):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"[Dashboard] {self.address_string()} - " + fmt % args)


def main():
    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "8788"))
    print(f"Dashboard listening on http://{host}:{port}")
    HTTPServer((host, port), DashboardHandler).serve_forever()


if __name__ == "__main__":
    main()
