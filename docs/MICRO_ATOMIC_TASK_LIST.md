# Micro Atomic Task List — Crypto Alpha Scanner

Bu belge, repoyu güvenli bir paper-trading prototipinden bilimsel olarak doğrulanabilir Binance USD-M futures araştırma ve yürütme sistemine dönüştürmek için görev listesidir.

> Ana kural: Gerçek para ile canlı emir, backtest + forward paper + testnet doğrulaması tamamlanmadan açılmayacak.

## Mevcut doğrulanmış durum

- Repo varsayılan olarak paper trading mantığıyla çalışıyor.
- `FutureSimulator` mevcut ve kararları canlı yürütmeden önce SL/TP reward-risk kapısından geçiriyor.
- `tradingview/crypto_alpha_alert.pine` şu an `indicator()` tabanlı sinyal üreticisi; Strategy Tester performans metrikleri üretmiyor.
- Webhook tarafında `long`, `long_exit`, `short`, `short_exit` sinyalleri henüz futures semantiğine tam karşılık vermiyor.
- Live executor fail-closed davranıyor; `LIVE_TRADING=true` olmadan emir göndermiyor.

## Faz 0 — Güvenlik kilidi ve bilimsel çalışma standardı

- [ ] Mainnet canlı emirleri varsayılan olarak kapalı tut.
- [ ] `TRADING_MODE=paper` ve `LIVE_TRADING=false` varsayılanlarını koru.
- [ ] Her değişiklik sonrası `python -m compileall -q .` ve `python -m pytest -q` kalite kapısı çalıştır.
- [ ] Backtest sonucu olmadan kârlılık iddiası üretme.
- [ ] Her raporda şu metrikleri zorunlu kıl: net profit, max drawdown, win rate, profit factor, expectancy, trade count.

## Faz 1 — Sinyal semantiği refaktörü

Amaç: TradingView ve backend arasında LONG / SHORT / LONG_EXIT / SHORT_EXIT anlam kaybını bitirmek.

- [ ] `models/schemas.py` içine futures uyumlu sinyal enumları ekle:
  - `LONG`
  - `SHORT`
  - `LONG_EXIT`
  - `SHORT_EXIT`
  - `HOLD`
- [ ] `TradeDecision` modeline şu alanları ekle:
  - `signal_side`
  - `order_side`
  - `position_side`
  - `reduce_only`
  - `qty`
  - `notional_usd`
  - `reject_reason`
  - `expected_fee_usd`
  - `expected_slippage_usd`
  - `expected_funding_usd`
- [ ] `tradingview_webhook.py` içinde sinyal normalizer yaz:
  - `long` → `LONG`
  - `long_exit` → `LONG_EXIT`
  - `short` → `SHORT`
  - `short_exit` → `SHORT_EXIT`
- [ ] Spot mode ve futures mode kararlarını ayır.
- [ ] Short açma ve short kapama lifecycle testleri ekle.

Kabul kriteri:

- [ ] `SHORT` artık basit `sell` olarak kaybolmayacak.
- [ ] `SHORT_EXIT` artık `watch` olarak kaybolmayacak.
- [ ] Her webhook payload deterministik olarak tek bir normalize edilmiş sinyal üretmeli.

## Faz 2 — FutureSimulator ana kalite kapısı

Amaç: Gelecek simülasyonu aracını sadece basit reward-risk filtresi olmaktan çıkarıp mikro risk motoruna dönüştürmek.

Mevcut durum:

- `FutureSimulator` buy kararında stop-loss / take-profit üzerinden projected loss, projected profit ve reward-risk hesaplıyor.
- `sell` kararlarını şu an otomatik pozisyon azaltma olarak kabul ediyor.

Yapılacaklar:

- [ ] Long ve short için simetrik PnL projeksiyonu ekle.
- [ ] Exit sinyallerini reduce-only pozisyon kapama olarak simüle et.
- [ ] Fee modelini ekle:
  - taker fee bps
  - maker fee bps
  - giriş fee
  - çıkış fee
- [ ] Slippage modelini ekle:
  - sabit bps
  - ATR yüzdesi tabanlı dinamik bps
  - hacim/likidite cezası
- [ ] Funding modelini ekle:
  - long funding maliyeti
  - short funding maliyeti
  - worst-case funding shock
- [ ] Liquidation buffer kontrolü ekle.
- [ ] Minimum reward-risk hesabını fee + slippage + funding sonrası yap.
- [ ] `SimulationResult` içine şunları ekle:
  - `net_projected_profit_usd`
  - `total_cost_usd`
  - `fee_cost_usd`
  - `slippage_cost_usd`
  - `funding_cost_usd`
  - `liquidation_buffer_pct`

Kabul kriteri:

- [ ] Simülasyon onayı almayan hiçbir emir execution katmanına geçmeyecek.
- [ ] Reward-risk brüt değil, maliyet sonrası net hesaplanacak.
- [ ] Long ve short aynı matematiksel disiplinle değerlendirilecek.

## Faz 3 — Pine indicator → strategy dönüşümü

Amaç: TradingView üzerinde ölçülebilir Strategy Tester sonucu üretmek.

- [ ] Mevcut indicator dosyasını koru.
- [ ] Ayrı dosya oluştur: `tradingview/crypto_alpha_strategy.pine`.
- [ ] `strategy()` kullan:
  - `pyramiding=0`
  - komisyon parametresi
  - slippage ticks parametresi
  - bar kapanışı veya sonraki bar fill kuralı açık tanımlı olsun.
- [ ] `strategy.entry()` ile LONG/SHORT aç.
- [ ] `strategy.exit()` ile SL/TP bracket çıkışları ekle.
- [ ] `strategy.close()` ile LONG_EXIT/SHORT_EXIT kapanışları ekle.
- [ ] Alert JSON formatı indicator ile uyumlu kalsın.

Kabul kriteri:

- [ ] TradingView Strategy Tester şu metrikleri gösterecek:
  - net profit
  - max drawdown
  - win rate
  - profit factor
  - trade count
- [ ] Repaint riskini azaltmak için `lookahead_off` korunacak.

## Faz 4 — Binance USD-M futures backtest altyapısı

Amaç: 200 günlük 5m futures backtestini Python içinde tekrar üretilebilir yapmak.

- [ ] `scripts/fetch_binance_um.py` oluştur:
  - `/fapi/v1/klines`
  - pagination
  - parquet/csv çıktı
- [ ] `scripts/fetch_funding.py` oluştur:
  - `/fapi/v1/fundingRate`
  - funding history saklama
- [ ] `scripts/fetch_exchange_info.py` oluştur:
  - tickSize
  - stepSize
  - minNotional
  - symbol rules
- [ ] `backtesting/engine.py` oluştur:
  - sonraki bar open fill varsayımı
  - fee
  - slippage
  - funding
  - stop-loss / take-profit
  - equity curve
  - drawdown
- [ ] `backtesting/metrics.py` oluştur:
  - net profit
  - max drawdown
  - win rate
  - profit factor
  - expectancy
  - Sharpe/Sortino opsiyonel
- [ ] `scripts/run_backtest.py` oluştur.
- [ ] Rapor çıktısı: `reports/{symbol}_{interval}_{days}d.json`.

Kabul kriteri:

- [ ] `BTCUSDT 5m 200d` backtest tek komutla çalışmalı.
- [ ] Sonuçlar JSON olarak kaydedilmeli.
- [ ] Komisyon, slippage ve funding devre dışı bırakıldığında/aktifken fark raporlanmalı.

## Faz 5 — Testnet-first live executor

Amaç: Canlı yürütmeyi önce güvenli Binance testnet motoruna taşımak.

- [ ] `EXECUTION_ENV=testnet` varsayılanını ekle.
- [ ] Mainnet için ikinci kilit ekle: `ALLOW_MAINNET=true` olmadan mainnet yasak.
- [ ] Binance futures one-way mode varsayılanını tanımla.
- [ ] Precision rounding:
  - tickSize
  - stepSize
  - minNotional
- [ ] `reduceOnly=true` exit emirlerini destekle.
- [ ] Bracket order mantığı ekle:
  - entry
  - stop market
  - take profit market/limit
- [ ] Testnet smoke script ekle.

Kabul kriteri:

- [ ] Eksik API key → rejected.
- [ ] Mainnet kilidi kapalı → rejected.
- [ ] Precision hatası → rejected, emir gönderilmez.
- [ ] Testnet dışında live emir varsayılan olarak yok.

## Faz 6 — AIAnalyst bilimsel modernizasyonu

Amaç: AIAnalyst adını ölçülebilir ve kalibre edilebilir karar motoruna çevirmek.

- [ ] Mevcut heuristic analizi `HeuristicAlphaModel` olarak yeniden adlandır.
- [ ] İstatistiksel feature üretici ekle:
  - EMA gap
  - RSI
  - MACD histogram slope
  - ATR pct
  - volume ratio
  - ADX
  - macro score
  - funding rate
  - spread bps
- [ ] Model çıktısını olasılık olarak üret:
  - `prob_up`
  - `prob_down`
  - `prob_no_trade`
- [ ] LLM kullanılırsa sadece açıklama katmanı olsun; trade yönünü LLM belirlemesin.
- [ ] Model versiyonu ve feature hash logla.

Kabul kriteri:

- [ ] Karar motoru ölçülebilir probability üretmeli.
- [ ] Backtest ve paper test aynı karar fonksiyonunu kullanmalı.
- [ ] LLM çıktısı JSON schema ile sınırlanmalı.

## Faz 7 — Dashboard ve gözlemlenebilirlik

Amaç: Sistem neden trade aldı/almadı sorusunu tam cevaplayacak hale gelsin.

- [ ] Dashboard’a açık pozisyonlar paneli ekle.
- [ ] Son sinyaller paneli ekle.
- [ ] Reddedilen kararlar paneli ekle.
- [ ] Rejection reason göster.
- [ ] PnL ayrıştırması ekle:
  - gross pnl
  - fee
  - slippage
  - funding
  - net pnl
- [ ] Equity curve ve max drawdown alanı ekle.
- [ ] FutureSimulator sonucu dashboard’da görünür olsun.

Kabul kriteri:

- [ ] Her kararın trace’i görülebilmeli.
- [ ] Her reddin sebebi görülebilmeli.
- [ ] Backtest/paper/live sonuçları aynı panelde ayrılmış görünmeli.

## Faz 8 — Bilimsel kabul kapısı

Bir strateji ancak şu koşullarda “ileri aşamaya geçebilir”:

- [ ] 200 günlük 5m backtestte maliyet sonrası pozitif expectancy.
- [ ] Profit factor > 1.15.
- [ ] Max drawdown kabul edilen risk sınırının altında.
- [ ] En az 100 trade veya istatistiksel olarak yeterli örneklem.
- [ ] Paper forward testte backtest davranışına yakın sonuç.
- [ ] Testnet emirleri precision/reduce-only/SL/TP açısından hatasız.
- [ ] Mainnet sadece manuel açık izinle.

## Öncelik sırası

1. Sinyal semantiği refaktörü.
2. FutureSimulator maliyet ve long/short simülasyonu.
3. Pine strategy dosyası.
4. Binance 200g 5m backtester.
5. Testnet executor.
6. AIAnalyst probability modeli.
7. Dashboard observability.
8. Bilimsel kabul raporu.

## Güncel sistem puanı

- Mimari iskelet: 75/100
- Güvenlik kilidi: 78/100
- Futures semantiği: 35/100
- Backtest kanıtı: 20/100
- FutureSimulator mevcut hali: 45/100
- Canlı futures hazırlığı: 30/100
- Genel üretim hazırlığı: 42/100

Hedef: İlk dönüşüm sonunda 70+/100, backtest + testnet sonrası 85+/100.
