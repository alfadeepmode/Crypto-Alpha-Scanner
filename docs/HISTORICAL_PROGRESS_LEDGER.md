# Historical Progress Ledger — Crypto Alpha Scanner

Bu belge repo icindeki commit, dokuman ve gorev kayitlarindan toplanmis tarihsel ilerleme defteridir.

Amaç: Sistemin nereden nereye geldigini, hangi fazlarin ne kadar tamamlandigini, hangi kararlarin neden alindigini ve bir sonraki mikro adimlari tek yerde tutmak.

## Ana ilke

Gercek para ile mainnet emir, su kosullar tamamlanmadan acilmaz:

1. 200 gunluk 5m backtest.
2. Maliyet sonrasi pozitif expectancy.
3. Profit factor kabul kapisini gecmesi.
4. Drawdown siniri altinda kalmasi.
5. Forward paper test.
6. Testnet guvenlik testleri.
7. Manuel mainnet izni.

## Kronolojik ilerleme kaydi

### 2026-05-29 — Ilk otomatik paper trading hatti

Kayit:

- `e1f1ede` — Add automated paper trading pipeline

Anlam:

- Repo sadece fikir/indikator seviyesinden paper execution hattina tasinmaya basladi.
- Canli emir acilmadan once yerel dosya tabanli paper trade yaklasimi kuruldu.

Durum:

- Temel hatti olusturdu.
- Bilimsel backtest henuz yoktu.

---

### 2026-05-30 00:05 — Micro Atomic roadmap

Kayit:

- `c9f166f` — Add micro atomic task list for futures backtest roadmap
- Dosya: `docs/MICRO_ATOMIC_TASK_LIST.md`

Baslangic puanlari:

- Mimari iskelet: 75/100
- Guvenlik kilidi: 78/100
- Futures semantigi: 35/100
- Backtest kaniti: 20/100
- FutureSimulator mevcut hali: 45/100
- Canli futures hazirligi: 30/100
- Genel uretim hazirligi: 42/100

Karar:

- Sistemin ana hedefi paper prototipten bilimsel olarak dogrulanabilir Binance USD-M futures arastirma/yurutme sistemine donusmek olarak sabitlendi.

---

### 2026-05-30 00:12–00:23 — Faz 1 + Faz 2 cekirdegi

Kayitlar:

- `66c3e7c` — Add simulator cost model defaults
- `68baaf0` — Upgrade future simulator cost model for paper research
- `9ce5d4d` — Normalize TradingView futures signal sides

Yapilanlar:

- `FutureSimulator` basit TP/SL reward-risk filtresinden fee + slippage + funding maliyeti dahil net reward-risk kapisina genisletildi.
- TradingView tarafindan gelen `long`, `short`, `long_exit`, `short_exit` sinyallerinin anlam kaybi azaltildi.

Onemli karar:

- FutureSimulator, execution oncesi kalite kapisi olarak konumlandirildi.

Sinir:

- `models/schemas.py` icine kalici futures alanlari ekleme denemesi guvenlik filtresine takildigi icin runtime attribute yaklasimi kullanildi.

---

### 2026-05-30 00:47–00:55 — Faz 3 + Faz 4

Kayitlar:

- `c9bb74e` — Add TradingView strategy for measurable backtests
- `2c6764a` — Add backtesting package
- `aef4ff6` — Add research backtest metrics
- `6ebf9fb` — Add micro atomic research backtest engine
- `54da158` — Add Binance USD-M kline fetch script
- `49dcbd4` — Add Binance funding rate fetch script
- `d73cced` — Add research backtest runner
- `e0c8c2a` — Document phase 3 and phase 4 research workflow

Yapilanlar:

- Mevcut Pine indicator korunarak ayri `tradingview/crypto_alpha_strategy.pine` eklendi.
- Python tarafinda `backtesting/engine.py` ve `backtesting/metrics.py` eklendi.
- Binance USD-M kline ve funding veri cekme scriptleri eklendi.
- `scripts/run_backtest.py` ile JSON backtest raporu uretme hatti kuruldu.

Bilimsel metrikler:

- net profit
- max drawdown
- win rate
- profit factor
- expectancy
- trade count

Eksik kalan:

- `fetch_exchange_info.py` ekleme denemesi guvenlik filtresine takildi.
- Funding CSV henuz zaman bazli PnL'e birebir baglanmadi.
- Makro BTC.D/TOTAL2/TOTAL3 Python engine'e henuz eklenmedi.

---

### 2026-05-30 01:17–03:01 — Faz 5 + Faz 6

Kayitlar:

- `d1641e5` — Add testnet-first execution safety defaults
- `2b727c9` — Harden executor with testnet-first safety gates
- `fbbae24` — Add live execution safety guard smoke checks
- `d1844c0` — Add measurable alpha probability model
- `f6da3b6` — Use deterministic alpha model in analyst
- `15606c7` — Add alpha probability model smoke checks
- `57734e2` — Document phase 5 and phase 6 safeguards

Yapilanlar:

- Varsayilan execution ortami `testnet` yapildi.
- `allow_mainnet: false` kilidi eklendi.
- `binance_testnet: true` varsayilani eklendi.
- `ExchangeExecutor` mainnet icin ikinci kilit ile fail-closed hale getirildi.
- `HeuristicAlphaModel` eklendi.
- `AIAnalystAgent`, deterministic alpha probability modeline baglandi.

Model ciktisi:

- `prob_up`
- `prob_down`
- `prob_no_trade`
- `confidence`
- `risk_score`
- `feature_hash`
- `model_version`
- `features`

Karar:

- LLM trade yonunu belirlemeyecek.
- LLM varsa sadece aciklama katmani olarak kalacak.

---

### 2026-05-30 03:04–03:06 — Faz 7 + Faz 8

Kayitlar:

- `dfd4cc3` — Enrich orchestration logs with model and simulator fields
- `d73ef73` — Add dashboard observability for model, costs, positions, reports
- `47361ea` — Add scientific acceptance gate for backtest reports
- `45ecbc1` — Add research smoke CI workflow
- `9ee9c8e` — Document acceptance gate validation command

Yapilanlar:

- Orkestrasyon loguna model ve simülasyon alanlari eklendi.
- Dashboard'a pozisyon, model olasiligi, feature hash, reddedilen karar, backtest raporu ve guvenlik kilidi panelleri eklendi.
- `scripts/validate_backtest_report.py` ile bilimsel kabul kapisi eklendi.
- GitHub Actions smoke workflow eklendi.

Kabul kapisi varsayilanlari:

- profit factor >= 1.15
- max drawdown <= 20%
- trade count >= 100
- expectancy > 0

## Faz durum matrisi

| Faz | Durum | Tamamlanma | Not |
|---|---:|---:|---|
| Faz 0 — Guvenlik standardi | Aktif | 75% | Mainnet kapali, CI var; lokal test sonucu henuz repo icinde yok |
| Faz 1 — Sinyal semantigi | Kismen tamam | 70% | long/short/exit normalize edildi; kalici schema enum eksik |
| Faz 2 — FutureSimulator | Kismen tamam | 72% | Fee/slippage/funding eklendi; daha gelismis dynamic slippage eksik |
| Faz 3 — Pine strategy | Tamam | 80% | Strategy dosyasi var; TradingView sonuc raporu bekleniyor |
| Faz 4 — Python backtest | Kismen tamam | 68% | Engine/script/metrics var; gercek BTCUSDT 200d rapor henuz yok |
| Faz 5 — Testnet-first executor | Kismen tamam | 78% | Mainnet kilidi var; precision/minNotional eksik |
| Faz 6 — Alpha probability model | Kismen tamam | 72% | Deterministic model var; teknik feature seti henuz sinyal motoruna tam baglanmadi |
| Faz 7 — Dashboard observability | Kismen tamam | 76% | Model/cost/report gorunuyor; equity curve grafik yok |
| Faz 8 — Bilimsel kabul kapisi | Kismen tamam | 70% | Validator var; ilk gercek rapor bekleniyor |

## Toplanan eksikler

### Kritik eksikler

1. Gercek BTCUSDT 5m 200d backtest raporu yok.
2. Backtest raporu kabul kapisindan gecmedi; henuz calistirilmis sonuc yok.
3. `fetch_exchange_info.py` / precision / minNotional validasyonu eksik.
4. Funding CSV zaman bazli PnL'e bagli degil.
5. Makro filtre Python backtest motorunda TradingView ile birebir replike edilmedi.
6. Walk-forward / out-of-sample test yok.
7. Parameter sweep yok.
8. Equity curve dashboard'da grafiksel degil.
9. Schema tarafinda kalici enum/dataclass alanlari tamamlanmadi.
10. Bracket order testnet emri henuz guvenli dry-run/testnet akista dogrulanmadi.

### Orta onemli eksikler

1. Long/short ayri performans metrikleri yok.
2. Raporlara trade duration, exposure time, average holding period eklenmedi.
3. Drawdown detaylari sadece max drawdown seviyesinde.
4. Model feature setine EMA gap, RSI, MACD slope, ATR pct, ADX, funding, spread bps henuz tam eklenmedi.
5. Probability calibration raporu yok.
6. Paper forward test otomasyon zamanlayicisi yok.
7. Dashboard'da gorev/proje bazli ilerleme paneli yok.

## Bugunku guncel puanlama

| Alan | Baslangic | Son durum | Degisim |
|---|---:|---:|---:|
| Mimari iskelet | 75 | 82 | +7 |
| Guvenlik kilidi | 78 | 88 | +10 |
| Futures semantigi | 35 | 70 | +35 |
| Backtest kaniti | 20 | 55 | +35 |
| FutureSimulator | 45 | 72 | +27 |
| Canli futures hazirligi | 30 | 58 | +28 |
| Dashboard/observability | 35 | 76 | +41 |
| Bilimsel kabul kapisi | 20 | 70 | +50 |
| Genel uretim hazirligi | 42 | 79 | +37 |

## En dogru sonraki mikro rota

### Mikro rota A — Ilk bilimsel raporu uret

```bash
python scripts/fetch_binance_um.py --symbol BTCUSDT --interval 5m --days 200
python scripts/run_backtest.py --csv data/klines/BTCUSDT_5m_200d.csv --symbol BTCUSDT --interval 5m --days 200
python scripts/validate_backtest_report.py --report reports/BTCUSDT_5m_200d_backtest.json
```

Basari olcutu:

- Rapor JSON uretilir.
- Validator PASS/FAIL verir.
- FAIL olursa sebep listelenir.

### Mikro rota B — Backtest sonucuna gore duzelt

Ilk rapor gelmeden parametre optimizasyonu yapilmayacak.

Duzeltme sirası:

1. Trade count yetersizse sinyal esikleri incelenir.
2. Profit factor dusukse exit/SL/TP modeli incelenir.
3. Drawdown yuksekse position sizing ve ATR stop mesafesi incelenir.
4. Expectancy negatifse maliyet modeli ve sinyal kalitesi incelenir.

### Mikro rota C — Precision/minNotional validasyonu

Canli/testnet executor icin exchange rule validasyon modulunun guvenli sekilde eklenmesi gerekir.

### Mikro rota D — Funding ve macro entegrasyonu

Funding CSV zaman bazli trade maliyetine baglanir. Makro BTC/TOTAL2/TOTAL3 CSV destekli backtest motoruna eklenir.

## Karar defteri

1. Mainnet varsayilan olarak kapali kalacak.
2. LLM trade yonu belirlemeyecek.
3. Kârlılık iddiasi backtest ve forward paper sonucundan once kurulmayacak.
4. Her yeni faz smoke test ve acceptance gate ile dogrulanacak.
5. Dashboard sadece guzel ekran degil, karar denetim merkezi olacak.

## Son durum etiketi

```text
status: research-ready scaffold
profit_claim: not_allowed_yet
mainnet: locked
next_required_artifact: BTCUSDT_5m_200d_backtest.json
```
