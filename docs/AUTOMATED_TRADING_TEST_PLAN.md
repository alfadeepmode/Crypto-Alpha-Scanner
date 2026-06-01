# Otomatik Al-Sat Dönüşümü — Mikro Atomik Test Odaklı Plan

> Bu belge **yalnızca analiz ve planlamadır**. Kod yazmaz, silmez, değiştirmez.
> Amaç: Crypto Alpha Scanner'ı bilimsel olarak doğrulanabilir, **tamamen otomatik al-sat**
> yapan bir sisteme dönüştürecek **test-öncelikli (TDD)** mikro atomik görev listesini,
> en güncel teknolojik altyapı önerileriyle birlikte ortaya koymaktır.
>
> Çalışma kuralı: Her görev **önce kırmızı (failing) test → minimal değişiklik → yeşil test**
> döngüsüyle ilerletilir. Hiçbir canlı mainnet emri backtest + forward paper + testnet
> kapıları geçilmeden açılmaz.

---

## 0. Yönetici Özeti — Mevcut Durum Fotoğrafı (kanıta dayalı)

Bu çalışmada repo mikro atomik seviyede incelendi ve kalite kapıları gerçek ortamda çalıştırıldı.

| Alan | Durum | Kanıt |
|---|---|---|
| `python -m compileall -q .` | ✅ Geçiyor | exit=0 |
| `pytest` (9 test, dex_screener) | ✅ Geçiyor | `9 passed in 0.15s` |
| `tests/smoke_test.py` | ❌ **KIRIK** | `AssertionError: expected at least one approved buy decision` |
| CI workflow (`Research Smoke`) | ⚠️ Sadece `smoke_test.py` çalıştırıyor; `pytest` çalıştırmıyor | `.github/workflows/*.yml` |
| Bağımlılıklar | ⚠️ Ortamda `httpx`/`pytest` kurulu değildi; elle kuruldu | `ModuleNotFoundError: httpx` |
| Backtest fixture verisi | ❌ Repo'da kline CSV yok (`data/klines/` yok) | `find *.csv` boş |

### 0.1 Tespit edilen kök-neden hata (BLOCKER)

`HeuristicAlphaModel` örnek BTC/ETH için **confidence = 72.11**, **risk = 32.08** üretiyor
(çünkü `confidence = max(prob_up, prob_down) * 100` ve `prob_up = sigmoid(edge - 0.85) ≈ 0.721`).
Ancak `DecisionAgent.min_buy_confidence = 75`. Yani:

- Alpha modeli `action="buy"` diyor (`prob_up >= 0.62 and risk <= 35`),
- DecisionAgent ise `confidence >= 75` istediği için **buy'ı hold'a çeviriyor**,
- `smoke_test.py` "en az bir onaylı buy" beklediği için **çöküyor**.

> Bu, "alpha modeli eşiği" ile "karar motoru eşiği" arasındaki **kontrat uyumsuzluğudur**.
> Tamamen otomatik al-sat hedefinde bu zincirin her halkasının eşik sözleşmesi tek bir
> kaynaktan türetilmeli ve testle kilitlenmelidir (Faz 1).

---

## 1. Mimari Haritası (test sınırlarını belirlemek için)

```
                         ┌─────────────────────────────────────────────┐
  main.py (run_scan)     │              VERİ KATMANI                    │
  main.py (run_watch) ──▶│ DataCollectorAgent                          │
  tradingview_webhook ─┐ │   ├─ DexScreenerTool (REST, httpx)          │
                       │ │   ├─ EtherscanTool                          │
                       │ │   └─ RedditScraper / WhaleAlert             │
                       │ └─────────────────────────────────────────────┘
                       │            │ raw_data
                       │            ▼
                       │   FilterAgent (likidite/hacim eşikleri)
                       │            │ filtered
                       │            ▼
                       │   AIAnalystAgent ─▶ HeuristicAlphaModel
                       │            │  (prob_up/prob_down/confidence/risk/action)
                       │            ▼  signals
                       │   OrchestrationAgent.process_signals
                       │      1) DecisionAgent   → side/signal_side/SL/TP
                       │      2) RiskManager     → allowlist/limit/likidite/pozisyon
                       │      3) FutureSimulator → fee+slippage+funding net RR kapısı
                       │      4) ExchangeExecutor→ paper | fail-closed live (ccxt)
                       │            │
                       │            ▼  PositionStore (data/positions.json)
                       └──────▶ PublisherAgent (Telegram)  +  orchestration_log.jsonl

  backtesting/engine.py  ── offline araştırma (next-bar open fill, intrabar SL/TP)
  backtesting/metrics.py ── net profit/DD/PF/expectancy/sharpe-like
  scripts/fetch_*        ── Binance USD-M klines + funding (ağ gerektirir)
  scripts/validate_backtest_report.py ── bilimsel kabul kapısı
  dashboard.py           ── yerel gözlem paneli
  tradingview/*.pine     ── indicator + strategy (Strategy Tester)
```

### 1.1 `side` semantiği (kritik sözleşme)
`TradeDecision.side` exchange yönü (`buy`/`sell`/`hold`); futures niyeti `signal_side`
runtime attribute'unda taşınıyor:

| Niyet | signal_side | side | position_side | reduce_only |
|---|---|---|---|---|
| Long giriş | `LONG` | buy | long | false |
| Long çıkış | `LONG_EXIT` | sell | long | true |
| Short giriş | `SHORT` | sell | short | false |
| Short çıkış | `SHORT_EXIT` | buy | short | true |

Bu eşleme `decision_agent.py`, `tradingview_webhook.normalize_signal_side`,
`portfolio.apply_execution` ve `exchange_executor` arasında **dört yerde** tekrarlanıyor →
regression testiyle kilitlenmesi gereken kırılgan nokta.

---

## 2. Risk / Boşluk Sicili (otomasyon önündeki engeller)

| # | Boşluk | Etki | Faz |
|---|---|---|---|
| G1 | Alpha confidence (72) vs buy eşiği (75) uyumsuzluğu | Hiç buy üretilmez, smoke kırık | F1 |
| G2 | CI `pytest`'i çalıştırmıyor; 9 unit test gate değil | Regresyon kaçar | F0 |
| G3 | Açık pozisyon için **SL/TP enforcement yok** (paper/live) | Korumasız pozisyon, otomatik çıkış yok | F7 |
| G4 | Live executor'da **precision yok** (tickSize/stepSize/minNotional) | Borsa emir reddi / hatalı miktar | F6 |
| G5 | Live'da **bracket order gönderilmiyor** (SL/TP borsada yok) | Stop'suz canlı pozisyon | F6/F7 |
| G6 | Borsa ↔ `PositionStore` **mutabakatı (reconciliation) yok** | Hayalet/şişmiş pozisyon | F7 |
| G7 | **Idempotency / clientOrderId yok**, retry yok | Çift emir riski | F6 |
| G8 | Gerçek zamanlı fiyat akışı yok (sadece REST snapshot) | Geç/yanlış fiyatla emir | F8 |
| G9 | `run_watch` = `time.sleep` döngüsü; crash recovery yok | Daemon kırılgan | F9 |
| G10 | Webhook: statik secret, **HMAC/replay koruması yok**, tek-thread `HTTPServer` | Sahte sinyal/yük | F10 |
| G11 | Backtest fixture'ı repo'da yok | CI'da backtest doğrulanamaz | F4 |
| G12 | FutureSimulator funding modeli tutma süresinden bağımsız; exit maliyetsiz onaylanıyor | Net RR yanlış | F3 |
| G13 | Şemalar dataclass; doğrulama/serileştirme zayıf (pydantic yok) | Geçersiz veri sızar | F0/F5 |
| G14 | Backtest motoru saf-Python döngü (vektörize değil) | 200g 5m yavaş | F13 |
| G15 | Kill-switch / global devre kesici yok | Acil durdurma yok | F12 |
| G16 | Yapısal log/metrics (Prometheus) yok | Gözlemlenebilirlik düşük | F11 |

---

## 3. Önerilen Modern Teknoloji Altyapısı (en güncel, hızlı)

> Bunlar **plan içi öneridir**; bu seansta uygulanmaz. Her geçiş bir test fazına bağlanmıştır.

| Katman | Mevcut | Önerilen (güncel/hızlı) | Neden |
|---|---|---|---|
| Çalışma zamanı | Python 3.11 | **Python 3.12/3.13 + uvloop** | async hız, son sürüm |
| Şema/doğrulama | dataclass | **Pydantic v2** (rust-core) | hızlı doğrulama/serileştirme |
| HTTP | httpx (sync) | **httpx.AsyncClient** + retry (tenacity) | paralel veri toplama |
| Borsa I/O | ccxt (sync) | **ccxt.pro / websockets** | gerçek zamanlı fiyat+emir |
| Webhook/API | `http.server` | **FastAPI + uvicorn** | async, doğrulama, OpenAPI |
| Zamanlama | `time.sleep` | **APScheduler / asyncio task** | crash recovery, jitter |
| Backtest hesap | saf Python | **Polars / NumPy** vektörize | 200g 5m'i saniyelere indirir |
| Paket/venv | pip | **uv** (Astral, çok hızlı) | hızlı kurulum, lock |
| Lint/format | yok | **Ruff** (lint+format) | tek araç, çok hızlı |
| Tip | yok | **mypy / pyright** | sözleşme güvenliği |
| Test | pytest | **pytest + pytest-asyncio + cov + hypothesis** | property + async |
| HTTP mock | elle FakeClient | **respx / vcrpy** | gerçekçi httpx mock/replay |
| Zaman mock | yok | **freezegun** | deterministik zaman |
| Entegrasyon | yok | **testcontainers** (opsiyonel) | izole bağımlılık |
| Paketleme | yok | **Docker + compose** | tekrarlanabilir runtime |
| Gözlem | print | **structlog + Prometheus + Grafana** | trace/metric |
| Gizli tarama | GH | **gitleaks / detect-secrets** (pre-commit) | sızıntı önleme |

---

## 4. Test Piramidi ve Dosya Düzeni (hedef)

```
tests/
  unit/            # saf, ağsız, <1ms — modeller, eşik sözleşmeleri, indikatörler
  contract/        # ajanlar arası sözleşmeler (decision↔risk↔sim↔executor)
  property/        # hypothesis — long/short simetrisi, invariantlar
  integration/     # respx ile mock borsa/REST; FastAPI TestClient
  e2e/             # paper uçtan uca; (opsiyonel) testnet nightly
  fixtures/        # küçük kline CSV, webhook payload, exchangeInfo JSON
conftest.py        # freeze time, tmp paths, config factory, env izolasyonu
```

Hedef kapsama (coverage) kapıları: çekirdek modüller (`agents/`, `tools/`, `backtesting/`)
için **≥ %85 satır**, kritik para yolu (`exchange_executor`, `future_simulator`,
`risk_manager`, `portfolio`) için **≥ %95**.

---

## 5. MİKRO ATOMİK GÖREV LİSTESİ

Format: `ID — Görev | Yazılacak/çalıştırılacak test | Kabul kriteri`.
Her görev tek bir davranışı izole eder (mikro atomik). Sıra, bağımlılığa göredir.

### FAZ 0 — Test altyapısı & tekrarlanabilir ortam (temel)

- [ ] **F0.1** Baseline'ı dondur: `compileall`, `pytest`, `smoke_test` çıktısını bir
  `docs/BASELINE.md`'ye kaydet. | *Test:* komutların exit kodlarını raporla. |
  *Kabul:* smoke'un şu an kırık olduğu belgelenir (regresyon referansı).
- [ ] **F0.2** `requirements-dev.txt` ekle (pytest, pytest-cov, pytest-asyncio, hypothesis,
  freezegun, respx, ruff, mypy). | *Test:* `uv pip install -r requirements-dev.txt` temiz. |
  *Kabul:* tüm dev araçları import edilebilir.
- [ ] **F0.3** SessionStart hook + `Makefile`/`tasks` ekle: `make test`, `make lint`,
  `make smoke`, `make backtest`. | *Test:* her hedef sıfır-yapılandırmayla koşar. |
  *Kabul:* tek komutla yeşil kapı.
- [ ] **F0.4** CI'yı genişlet: `compileall` + **`pytest -q --cov`** + `ruff` + `mypy` +
  `smoke_test`. | *Test:* CI matrix (3.11/3.12). | *Kabul:* `pytest` artık gate (G2 kapanır).
- [ ] **F0.5** `conftest.py`: `frozen_time`, `tmp_config` factory, `isolated_env`
  (TRADING_MODE/LIVE_TRADING/POSITION_STATE_PATH/PAPER_TRADES_PATH temizler). |
  *Test:* iki test paralelde dosya çakışması yaratmaz. | *Kabul:* deterministik, izole.
- [ ] **F0.6** `data/`, `reports/` yazımlarını `tmp_path`'e yönlendiren test policy. |
  *Test:* test sonrası repo'da artık dosya yok. | *Kabul:* temiz çalışma ağacı.

### FAZ 1 — Eşik sözleşmesi & mevcut hata regresyonu (G1)

- [ ] **F1.1** *Kırmızı test:* `HeuristicAlphaModel` örnek BTC için `action=="buy"` üretirken
  `confidence` değerinin `DecisionAgent.min_buy_confidence`'ı geçtiğini doğrula. |
  *Test:* `tests/contract/test_alpha_decision_contract.py`. | *Kabul:* test **şu an kırmızı**
  (72.11 < 75) — hatayı kanıtlar.
- [ ] **F1.2** Tek kaynak eşiği: alpha "buy" sınırı ile decision "min_buy_confidence"in
  config'ten türetilme tasarımını belgele. | *Test:* config-driven parametrik test. |
  *Kabul:* eşikler tek yerden, dokümante.
- [ ] **F1.3** *Yeşile alma görevi (sonraki seans):* alpha skor ölçeği ↔ decision eşiği
  uyumlandığında F1.1 yeşile döner ve `smoke_test` yeniden geçer. | *Test:* `smoke_test` +
  F1.1. | *Kabul:* smoke yeşil, en az bir onaylı buy.
- [ ] **F1.4** Sınır değer testleri: confidence = {eşik-1, eşik, eşik+1}, risk = {max, max+1}. |
  *Test:* parametrik unit. | *Kabul:* karar sınırları kesin tanımlı.

### FAZ 2 — Sinyal semantiği & futures yaşam döngüsü sözleşmesi (1.1 tablosu)

- [ ] **F2.1** `normalize_signal_side` tüm girdiler için tablo testi (long/buy/short/sell/
  long_exit/short_exit/exit/bilinmeyen). | *Test:* parametrik. | *Kabul:* her girdi tek
  deterministik (action, signal_side).
- [ ] **F2.2** `DecisionAgent.decide` her signal_side için doğru `side/position_side/
  reduce_only/SL/TP` üretir. | *Test:* 4 yaşam-döngüsü senaryosu. | *Kabul:* SHORT artık
  düz "sell" olarak kaybolmaz; SHORT_EXIT "watch" olmaz.
- [ ] **F2.3** Long lifecycle: giriş→çıkış `PositionStore` qty/cost/realized doğru. |
  *Test:* `test_position_lifecycle_long`. | *Kabul:* realized PnL = (exit-avg)*qty.
- [ ] **F2.4** Short lifecycle: giriş→çıkış realized = (avg-exit)*qty. |
  *Test:* `test_position_lifecycle_short`. | *Kabul:* short matematiği simetrik doğru.
- [ ] **F2.5** Spot vs futures mod ayrımı: reduce_only emir spot modda anlamlı reddedilir. |
  *Test:* mod parametreli. | *Kabul:* mod sözleşmesi net.

### FAZ 3 — FutureSimulator maliyet motoru (G12)

- [ ] **F3.1** Long & short PnL projeksiyonu simetrisi. | *Test:* aynı SL/TP mesafesinde
  long ve short net_reward_risk eşit (işaret hariç). | *Kabul:* simetri korunur.
- [ ] **F3.2** Fee modeli: round-trip taker fee = `notional*2*bps/1e4`. |
  *Test:* bilinen sayılarla eşitlik. | *Kabul:* fee birebir.
- [ ] **F3.3** Slippage: sabit bps + (öneri) ATR/likidite cezası. | *Test:* dinamik bps
  artışı doğrulanır. | *Kabul:* düşük likiditede maliyet artar.
- [ ] **F3.4** Funding: tutma süresi/funding interval'a bağlı maliyet (mevcut: sabit). |
  *Test:* uzun tutmada funding artar. | *Kabul:* funding süreye duyarlı.
- [ ] **F3.5** Exit/reduce-only emirde maliyet **eksik onay** hatasını yakala. |
  *Test:* exit kararı maliyetsiz onaylanmamalı. | *Kabul:* exit de net hesaba girer.
- [ ] **F3.6** Liquidation buffer reddi: stop mesafesi < min_buffer → reddet. |
  *Test:* sınır değer. | *Kabul:* tampon ihlali emri durdurur.
- [ ] **F3.7** Kapı sözleşmesi: onaysız hiçbir karar executor'a geçmez. |
  *Test:* `approve_batch` reddinde `side=="hold"`. | *Kabul:* fail-closed.

### FAZ 4 — Backtest motoru & bilimsel kanıt (G11)

- [ ] **F4.1** Küçük deterministik kline fixture'ı (`tests/fixtures/klines_*.csv`) ekle. |
  *Test:* `load_klines_csv` doğru parse. | *Kabul:* CI ağsız backtest koşar.
- [ ] **F4.2** İndikatör doğruluğu: EMA/RSI/ATR/ADX/MACD referans değerlere karşı. |
  *Test:* bilinen seride tolerans içinde. | *Kabul:* indikatörler doğrulanmış.
- [ ] **F4.3** **No-lookahead** testi: sinyal bar i, fill bar i+1 open. |
  *Test:* gelecek bar kullanılmadığını assert et. | *Kabul:* repaint/lookahead yok.
- [ ] **F4.4** Intrabar SL/TP önceliği: aynı barda hem stop hem take varsa kural deterministik. |
  *Test:* çakışma senaryosu. | *Kabul:* tutarlı çıkış.
- [ ] **F4.5** Maliyet on/off farkı raporlanır (fee/slippage/funding=0 vs aktif). |
  *Test:* iki koşu karşılaştırması. | *Kabul:* maliyet etkisi ölçülür.
- [ ] **F4.6** Metrics doğruluğu: PF, expectancy, win_rate, max_drawdown bilinen trade
  setiyle. | *Test:* `test_metrics.py`. | *Kabul:* metrikler birebir.
- [ ] **F4.7** Kabul kapısı entegrasyonu: `validate_backtest_report.py` PASS/FAIL doğru. |
  *Test:* iyi/kötü rapor fixture'ı. | *Kabul:* PF<1.15 veya trade<100 → FAIL (exit 2).
- [ ] **F4.8** (Öneri) `engine`'i Polars/NumPy ile vektörize et; sonuç eşitliği testi. |
  *Test:* saf-Python ile vektörize çıktı aynı. | *Kabul:* hız ↑, sonuç değişmez (G14).

### FAZ 5 — Veri katmanı güvenilirliği (G13)

- [ ] **F5.1** DexScreener: başarı/boş/HTTP500/JSON-hata yolları (respx ile). |
  *Test:* `test_dex_screener` genişlet. | *Kabul:* her hata → güvenli boş dönüş.
- [ ] **F5.2** Retry + timeout + rate-limit (tenacity) sözleşmesi. | *Test:* 429 sonrası
  yeniden dene. | *Kabul:* geçici hatada toparlanır.
- [ ] **F5.3** Pydantic v2 ile gelen veri doğrulama (negatif fiyat/NaN reddi). |
  *Test:* bozuk payload → reddedilir. | *Kabul:* geçersiz veri pipeline'a sızmaz.
- [ ] **F5.4** Etherscan/Reddit/WhaleAlert hata→boş dönüş ve `collect_all` dayanıklılığı. |
  *Test:* kaynak exception fırlatınca boş liste. | *Kabul:* tek kaynak çökmesi taramayı durdurmaz.

### FAZ 6 — Live executor güvenliği & precision (G4, G5, G7)

- [ ] **F6.1** Fail-closed matris (mevcut smoke davranışını unit'e taşı): LIVE_TRADING≠true,
  allowlist dışı, exchange≠binance, env geçersiz, mainnet kilidi, testnet sandbox, eksik key. |
  *Test:* her durum `rejected`. | *Kabul:* yedi kilit de testle sabit.
- [ ] **F6.2** `exchangeInfo` fixture ile precision: tickSize/stepSize/minNotional yuvarlama. |
  *Test:* miktar/fiyat borsa kurallarına yuvarlanır. | *Kabul:* precision hatası → reddet (emir gitmez).
- [ ] **F6.3** Idempotency: `clientOrderId` üretimi ve tekrar gönderimde çift emir yok. |
  *Test:* aynı karar iki kez → tek emir. | *Kabul:* idempotent.
- [ ] **F6.4** ccxt mock ile market emir parametreleri (`reduceOnly`, `positionSide`). |
  *Test:* doğru params iletildi. | *Kabul:* futures niyeti borsaya doğru yansır.
- [ ] **F6.5** Bracket order: entry + stop-market + take-profit emirlerinin (reduceOnly)
  birlikte kurulması. | *Test:* üç emir mock'ta oluşur. | *Kabul:* canlı pozisyon stop'suz açılmaz (G5).
- [ ] **F6.6** Hata/timeout'ta `failed` durumu ve pozisyon state'inin bozulmaması. |
  *Test:* exchange exception. | *Kabul:* kısmi-emir tutarsızlığı yok.

### FAZ 7 — Pozisyon izleme, SL/TP enforcement & mutabakat (G3, G6) — *otomasyonun kalbi*

- [ ] **F7.1** PositionMonitor sözleşmesi (yeni bileşen tasarımı): açık pozisyonları periyodik
  değerlendirir; fiyat SL/TP'yi geçtiğinde reduce-only çıkış üretir. |
  *Test:* fiyat stop'u geçince çıkış kararı. | *Kabul:* korumasız pozisyon kalmaz.
- [ ] **F7.2** Paper modda SL/TP enforcement: simüle fiyat akışında otomatik kapama. |
  *Test:* enjekte fiyat serisi. | *Kabul:* paper pozisyon SL/TP'de kapanır.
- [ ] **F7.3** Trailing stop / breakeven (öneri) opsiyonel kural. | *Test:* trailing tetikler. |
  *Kabul:* kâr koruma çalışır.
- [ ] **F7.4** Reconciliation: borsa pozisyonu ↔ `PositionStore` farkı tespit & uzlaştırma. |
  *Test:* mock borsa farkı → drift uyarısı/düzeltme. | *Kabul:* hayalet pozisyon yakalanır.
- [ ] **F7.5** Çıkış emri başarısızsa yeniden dene + alarm. | *Test:* exit fail → retry. |
  *Kabul:* çıkış garantili kuyrukta.

### FAZ 8 — Gerçek zamanlı veri & async modernizasyon (G8)

- [ ] **F8.1** Async veri toplama (httpx.AsyncClient) — eşzamanlı kaynak çağrısı. |
  *Test:* `pytest-asyncio` + respx. | *Kabul:* paralel toplama, daha düşük gecikme.
- [ ] **F8.2** Binance websocket fiyat akışı adaptörü (mock ws). | *Test:* tick → fiyat
  güncellenir. | *Kabul:* karar anlık fiyatla.
- [ ] **F8.3** Veri tazeliği kapısı: snapshot yaşı > eşik → emir bloklanır. |
  *Test:* bayat fiyat → reddet. | *Kabul:* bayat veriyle emir yok.

### FAZ 9 — Zamanlayıcı / daemon dayanıklılığı (G9)

- [ ] **F9.1** APScheduler/asyncio tabanlı tarama döngüsü; jitter + interval. |
  *Test:* sahte saat ile tetikleme. | *Kabul:* `time.sleep` döngüsü yerine sağlam zamanlama.
- [ ] **F9.2** Crash recovery: çalışma ortasında kesinti → tutarlı yeniden başlama. |
  *Test:* yarıda kesilen run state. | *Kabul:* çift işlem yok.
- [ ] **F9.3** Tek-örnek kilidi (lockfile) — paralel daemon çakışmasını önle. |
  *Test:* ikinci örnek reddedilir. | *Kabul:* tek aktif trader.

### FAZ 10 — Webhook sertleştirme (G10)

- [ ] **F10.1** FastAPI + TestClient'e taşıma tasarımı; mevcut payload sözleşmesi korunur. |
  *Test:* aynı payload → aynı karar. | *Kabul:* davranış denkliği.
- [ ] **F10.2** **HMAC imza** doğrulaması (statik secret yerine). | *Test:* yanlış imza → 403. |
  *Kabul:* sahte sinyal reddi.
- [ ] **F10.3** Replay koruması (timestamp + nonce). | *Test:* tekrarlanan istek reddedilir. |
  *Kabul:* replay engellenir.
- [ ] **F10.4** Rate-limit & gövde boyutu sınırı. | *Test:* flood → 429. | *Kabul:* DoS yüzeyi daralır.

### FAZ 11 — Gözlemlenebilirlik & dashboard (G16)

- [ ] **F11.1** Yapısal log (structlog) — her kararın trace'i JSON. | *Test:* log şeması. |
  *Kabul:* her karar izlenebilir.
- [ ] **F11.2** Dashboard panelleri: açık pozisyonlar, son sinyaller, reddedilen kararlar +
  reject_reason, PnL ayrışımı (gross/fee/slippage/funding/net), equity curve. |
  *Test:* dashboard render testleri. | *Kabul:* "neden trade aldı/almadı" görünür.
- [ ] **F11.3** Prometheus metrikleri (emir sayısı, red oranı, gecikme, PnL). |
  *Test:* `/metrics` endpoint. | *Kabul:* metrik export.

### FAZ 12 — Uçtan uca otomasyon & canlıya geçiş kapısı (G15)

- [ ] **F12.1** Paper E2E: webhook/scan → karar → risk → sim → paper exec → pozisyon →
  SL/TP kapanış → log. | *Test:* tek senaryo tüm zinciri kapsar. | *Kabul:* paper'da
  tam otomatik al-sat döngüsü yeşil.
- [ ] **F12.2** **Kill-switch / global devre kesici**: tek bayrak tüm yeni emirleri durdurur. |
  *Test:* kill aktifken emir yok, açık pozisyonlar güvenli kapatılır. | *Kabul:* acil durdurma var.
- [ ] **F12.3** Günlük zarar limiti / max açık pozisyon / max kaldıraç guard. |
  *Test:* limit aşımında yeni emir reddi. | *Kabul:* sermaye koruması.
- [ ] **F12.4** Testnet E2E (nightly, opsiyonel, gerçek testnet key ile): precision +
  reduce-only + bracket hatasız. | *Test:* nightly job. | *Kabul:* testnet'te emir döngüsü temiz.
- [ ] **F12.5** Bilimsel kabul kapısı: 200g 5m backtest → maliyet sonrası pozitif expectancy,
  PF>1.15, DD<sınır, ≥100 trade → forward paper benzerliği. | *Test:* gate script + rapor. |
  *Kabul:* mainnet ancak **manuel açık izinle** (`ALLOW_MAINNET=true`).

### FAZ 13 — Performans & dağıtım altyapısı (G14)

- [ ] **F13.1** Gecikme bütçesi testi: sinyal→emir kararı < hedef ms. | *Test:* benchmark. |
  *Kabul:* SLA içinde.
- [ ] **F13.2** Vektörize backtest hız ölçümü (Polars/NumPy). | *Test:* süre regresyonu. |
  *Kabul:* 200g 5m hedef süre altında.
- [ ] **F13.3** Docker + compose; uv ile reproducible build. | *Test:* image içinde `make test`. |
  *Kabul:* taşınabilir, tekrarlanabilir.
- [ ] **F13.4** Yük testi (webhook + scheduler eşzamanlı). | *Test:* concurrency. |
  *Kabul:* darboğaz yok.

---

## 6. Yürütme Sırası (öncelik)

1. **F0** test altyapısı + CI'da pytest gate (en acil — G2).
2. **F1** eşik sözleşmesi & smoke'u yeşile alacak kontrat testi (G1, mevcut kırık).
3. **F2–F3** sinyal semantiği + maliyet motoru sözleşmeleri.
4. **F4** backtest fixture + bilimsel kanıt (ağsız CI).
5. **F5–F6** veri güvenilirliği + live precision/idempotency/bracket.
6. **F7** pozisyon izleme + SL/TP enforcement + reconciliation (**otomasyonun kalbi**).
7. **F8–F10** gerçek zamanlı veri, daemon, webhook sertleştirme.
8. **F11–F12** gözlem + uçtan uca + kill-switch + kabul kapısı.
9. **F13** performans + dağıtım.

---

## 7. "Tamamen Otomatik Al-Sat" Tanımı (Definition of Done)

Sistem ancak şu maddelerin **tamamı testle yeşil** olunca tam-otomatik sayılır:

- [ ] Sinyal → karar → risk → simülasyon → emir → pozisyon → **otomatik SL/TP çıkışı** zinciri
      paper'da uçtan uca yeşil (F12.1).
- [ ] Long **ve** short, giriş **ve** çıkış aynı matematiksel disiplinle doğrulanmış (F2–F3).
- [ ] Live yol: precision + reduceOnly + bracket + idempotency + fail-closed kilitleri testli (F6).
- [ ] Açık pozisyon **asla** stop'suz kalmaz; reconciliation drift'i yakalar (F7).
- [ ] Gerçek zamanlı/taze fiyat kapısı + bayat-veri reddi (F8).
- [ ] Dayanıklı zamanlayıcı + tek-örnek kilidi + crash recovery (F9).
- [ ] Webhook HMAC + replay + rate-limit (F10).
- [ ] Kill-switch + günlük zarar limiti + max pozisyon/kaldıraç guard (F12.2–F12.3).
- [ ] Bilimsel kabul kapısı geçildi; mainnet yalnız manuel açık izinle (F12.5).
- [ ] CI: `compileall + pytest(cov) + ruff + mypy + smoke + backtest-gate` hepsi yeşil.

---

## 8. Bu Seansta Yapılmayanlar (kapsam sınırı)

- Hiçbir `.py`, `.pine`, `.yaml` dosyası yazılmadı/değiştirilmedi/silinmedi.
- Hiçbir canlı/testnet emri gönderilmedi.
- Yalnızca okuma, kalite kapılarının çalıştırılması ve bu plan dokümanı üretildi.

> Sonraki adım: F0.1'den başlayıp her görevi **önce kırmızı test** ile açmak.
> İlk somut kazanç: F1.1 testiyle mevcut "buy onaylanmıyor" hatasını kanıtlamak ve
> F1.3 ile `smoke_test`'i yeniden yeşile almaktır.
