# Crypto Alpha Scanner

n8n workflow mantigindan Python tabanli, ajanli, TradingView sinyali alabilen ve varsayilan olarak paper trading yapan kripto analiz/al-sat otomasyonu.

Bu repo gercek API anahtari, token, secret veya hesap bilgisi icermez. Tum ozel bilgiler `.env` dosyasina yazilir ve `.gitignore` ile repoya alinmaz.

## Ne Yapar

- DexScreener uzerinden public token verisi toplar.
- Opsiyonel Etherscan, Reddit ve Whale Alert kaynaklarini kullanir.
- Sinyalleri filtreler ve alpha skoru uretir.
- TradingView Pine indikatorden webhook sinyali alir.
- Her sinyali orkestrasyon hattindan gecirir.
- Canli emirden once risk ve gelecek simulasyonu yapar.
- Varsayilan olarak paper trade yazar.
- Dashboard ile durum, API var/yok, karar loglari ve paper emirleri goruntulenir.

## Mimari

```text
DataCollectorAgent
  -> FilterAgent
  -> AIAnalystAgent
  -> OrchestrationAgent
      -> SignalIntake
      -> DecisionAgent
      -> RiskManager
      -> FutureSimulator
      -> ExecutionTool
  -> PublisherAgent
```

TradingView akisi:

```text
TradingView Pine Indicator
  -> Webhook Server
  -> OrchestrationAgent
  -> Paper Trade veya Binance Live Executor
```

## Dizin Yapisi

```text
main.py                         # Ana CLI/orchestrator
setup_keys.py                   # Ilk kurulum ve .env sihirbazi
dashboard.py                    # Yerel web arayuzu
tradingview_webhook.py          # TradingView webhook server
config.yaml                     # Filtre, risk, trade ve orkestrasyon ayarlari
.env.example                    # Secret icermeyen env sablonu

agents/
  data_collector.py
  filter_agent.py
  ai_analyst.py
  publisher.py
  decision_agent.py
  risk_manager.py
  future_simulator.py
  orchestration_agent.py

tools/
  dex_screener.py
  etherscan.py
  reddit_scraper.py
  whale_alert.py
  telegram.py
  exchange_executor.py

models/
  schemas.py

tradingview/
  crypto_alpha_alert.pine       # Micro Atomic webhook indikatörü
```

## Kurulum

```bash
cd /home/alp/projects/Crypto-Alpha-Scanner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Ilk calistirmada veya `.env` eksikse kurulum sihirbazi otomatik acilir:

```bash
python main.py
```

Kurulumu elle yenilemek icin:

```bash
python main.py --setup
```

Sihirbaz su bilgileri sorar ama ekrana secret basmaz:

- AI provider ve model secimi
- OpenAI / OpenRouter / Groq / GitHub / local model bilgileri
- Telegram bot token ve chat id
- Binance API key / secret
- TradingView webhook secret
- Etherscan / Whale Alert gibi opsiyonel veri kaynaklari

## .env Guvenligi

`.env` repoya girmez. `.gitignore` icinde kapali tutulur.

Ornek degerler:

```bash
AI_PROVIDER=openrouter
AI_MODEL=qwen/qwen3-coder:free
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY

TRADING_MODE=paper
TRADING_EXCHANGE=paper
LIVE_TRADING=false

BINANCE_API_KEY=YOUR_BINANCE_KEY
BINANCE_API_SECRET=YOUR_BINANCE_SECRET

TRADINGVIEW_WEBHOOK_SECRET=CHANGE_ME
```

Gercek degerler README, commit, issue veya chat icine yazilmamalidir.

## Calistirma

Hizli tarama:

```bash
python main.py
```

Dış API kullanmadan deterministik demo/smoke taraması:

```bash
python main.py --offline --trade --no-setup
```

Tam offline smoke test:

```bash
python tests/smoke_test.py
```

Paper trade dahil otomatik karar:

```bash
python main.py --trade
```

Sürekli otomatik al-sat taraması (varsayılan paper mode):

```bash
python main.py --watch --trade
```

Tarama aralığı `config.yaml` içindeki `schedule.interval_minutes` veya env ile ayarlanır:

```bash
SCAN_INTERVAL_MINUTES=5 python main.py --watch --trade
```

Paper pozisyon defteri:

```text
data/positions.json
```

AutoGen GroupChat modu:

```bash
python main.py --autogen
```

TradingView webhook server:

```bash
python tradingview_webhook.py
```

Dashboard:

```bash
python dashboard.py
```

Dashboard adresi:

```text
http://127.0.0.1:8788/
```

Ham JSON status endpoint:

```text
http://127.0.0.1:8788/api/status
```

## Dashboard

Dashboard sunlari gosterir:

- trade modu: paper/live
- live trading kilidi
- API anahtarlari var/yok durumu
- TradingView webhook host/port
- orkestrasyon rolleri
- son karar loglari
- son paper emirler

Ana arayuz icin `/` adresi kullanilir. `/api/status` sadece JSON endpointidir.

## TradingView Indikatoru

Pine dosyasi:

```text
tradingview/crypto_alpha_alert.pine
```

TradingView Pine Editor'a bu dosya yapistirilir ve alert kurulur.

Webhook URL:

```text
http://127.0.0.1:8787/webhook/tradingview
```

TradingView alarminda header olarak kullanilacak secret:

```text
X-Webhook-Secret: TRADINGVIEW_WEBHOOK_SECRET_DEGERI
```

Indikator sinyal eslesmesi:

```text
LONG       -> buy
LONG EXIT  -> sell
SHORT      -> sell
SHORT EXIT -> watch
```

Spot Binance kullaniminda short acmak yerine sistem risk katmanindan gecirir. Varsayilan ayarda pozisyon dogrulamasi olmadan sell emirleri reddedilir.

## Otomatik Al-Sat

Varsayilan guvenli mod paper trading'dir:

```bash
TRADING_MODE=paper
TRADING_EXCHANGE=paper
LIVE_TRADING=false
```

Bu modda gercek emir gonderilmez. Emirler su dosyaya yazilir:

```text
data/paper_trades.jsonl
```

Canli Binance emri icin bilincli olarak uc kilit acilmalidir:

```bash
TRADING_MODE=live
TRADING_EXCHANGE=binance
LIVE_TRADING=true
```

Ek olarak Binance key/secret `.env` icinde bulunmalidir.

Canli kullanim icin guvenlik notlari:

- Binance API key icin withdrawal izni kapali olmalidir.
- Mumkunse IP restriction acilmalidir.
- Once paper modda yeterli test yapilmalidir.
- `config.yaml` icindeki `allowed_symbols` disinda emir verilmez.
- `FutureSimulator` onaylamadan emir executor'a gitmez.

## Risk ve Simulasyon Kapilari

`config.yaml` icindeki ana trade ayarlari:

```yaml
trading:
  mode: "paper"
  exchange: "paper"
  base_order_usd: 25
  max_order_usd: 100
  max_orders_per_run: 3
  min_buy_confidence: 75
  max_buy_risk: 35
  min_liquidity_usd: 100000
  stop_loss_pct: 8
  take_profit_pct: 18
  allowed_symbols: ["BTC", "ETH", "SOL", "XRP"]
  require_future_simulation: true
  max_projected_loss_usd: 15
  min_reward_risk: 1.4
```

FutureSimulator sunlari kontrol eder:

- fiyat gecerli mi
- stop-loss var mi
- take-profit var mi
- tahmini maksimum zarar limiti asiliyor mu
- odul/risk orani yeterli mi

Gecmeyen karar `hold` durumuna alinir.

Batch emir limiti `OrchestrationAgent.process_signals()` seviyesinde uygulanir. `max_orders_per_run: 3` ise tek taramada en fazla 3 emir executor'a gider; sonraki uygun sinyaller `hold` olur.

## Orkestrasyon Loglari

Her sinyal bu hatta islenir:

```text
SignalIntake -> DecisionAgent -> RiskManager -> FutureSimulator -> ExecutionTool
```

Log dosyasi:

```text
data/orchestration_log.jsonl
```

Bu log sistemin neden AL/SAT/HOLD verdigini ve hangi kapida durdugunu gosterir.

## Testler

Syntax/import kontrolu:

```bash
source .venv/bin/activate
python -m compileall -q .
```

Paper karar testi:

```bash
python main.py --trade
```

Webhook server testi:

```bash
python tradingview_webhook.py
```

Dashboard testi:

```bash
python dashboard.py
```

Son durumda test edilen kritik senaryolar:

```text
setup_detection                 PASS
paper_buy_executes              PASS
low_confidence_holds            PASS
high_risk_not_buy               PASS
low_liquidity_rejected          PASS
allowlist_rejected              PASS
future_sim_rejects_bad_rr       PASS
live_requires_explicit_flag     PASS
tradingview_payload_buy         PASS
critical_imports                PASS
```

TradingView otomasyon notu:

- Headless Chrome grafik sayfasini acti ve ekran goruntusu aldi.
- Mevcut otomasyon Pine Editor alanini otomatik bulamadi.
- Pine dosyasi hazir; TradingView Pine Editor'a manuel yapistirilarak alert kurulmalidir.

## GitHub

Remote repo:

```text
https://github.com/alfadeepmode/Crypto-Alpha-Scanner
```

Push oncesi kontrol:

```bash
git status
git diff
python -m compileall -q .
```

Commit ornegi:

```bash
git add -A
git commit -m "Add TradingView orchestration and paper trading dashboard"
git push origin master
```

## Onemli Uyari

Bu proje finansal tavsiye degildir. Canli emir modu gercek para riski tasir. Varsayilan paper trading modu ile test edilmeden live mod acilmamalidir.
