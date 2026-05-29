# Backtest Research Workflow — Faz 3 + Faz 4

Bu belge, Micro Atomic sisteminin kârlılık iddiası üretmeden önce nasıl ölçüleceğini tanımlar.

## Bilimsel ilke

Backtest sonucu olmadan sistem için "kârlı" denmez. Her sonuç maliyet sonrası değerlendirilir:

```text
net_pnl = gross_pnl - fee - slippage - funding
expectancy = sum(net_pnl) / trade_count
```

Zorunlu metrikler:

- net profit
- max drawdown
- win rate
- profit factor
- expectancy
- trade count

## Faz 3 — TradingView Strategy

Eklenen dosya:

```text
tradingview/crypto_alpha_strategy.pine
```

Bu dosya mevcut indikatörü bozmaz. Ayrı bir `strategy()` sürümüdür.

Ölçtüğü yapı:

- LONG entry
- SHORT entry
- LONG TP/SL
- SHORT TP/SL
- momentum/reversal exit
- komisyon
- slippage

TradingView Strategy Tester içinde kontrol edilecek ana metrikler:

- Net Profit
- Max Drawdown
- Percent Profitable
- Profit Factor
- Total Closed Trades

## Faz 4 — Python research backtest

Eklenen paket:

```text
backtesting/
  __init__.py
  engine.py
  metrics.py
```

Eklenen scriptler:

```text
scripts/fetch_binance_um.py
scripts/fetch_funding.py
scripts/run_backtest.py
```

### 1) Binance USD-M kline indir

```bash
python scripts/fetch_binance_um.py --symbol BTCUSDT --interval 5m --days 200
```

Çıktı:

```text
data/klines/BTCUSDT_5m_200d.csv
```

### 2) Funding verisi indir

```bash
python scripts/fetch_funding.py --symbol BTCUSDT --days 200
```

Çıktı:

```text
data/funding/BTCUSDT_200d.csv
```

Not: İlk backtest motoru funding'i trade başına yaklaşık bps maliyeti olarak modele dahil eder. Sonraki adımda funding CSV, zaman bazlı maliyet hesabına bağlanacak.

### 3) Backtest çalıştır

```bash
python scripts/run_backtest.py --csv data/klines/BTCUSDT_5m_200d.csv --symbol BTCUSDT --interval 5m --days 200
```

Çıktı:

```text
reports/BTCUSDT_5m_200d_backtest.json
```

## Varsayımlar

- Entry fill: sinyalden sonraki bar open.
- Exit fill: SL/TP intrabar varsayımı.
- Maliyet: taker fee + slippage + funding yaklaşımı.
- Position sizing: equity yüzdesi.
- Bu sistem research-only çalışır; emir göndermez.

## Kabul kapısı

Bir strateji bir sonraki aşamaya ancak şunlarla geçer:

- Profit factor > 1.15
- Maliyet sonrası expectancy > 0
- Trade count istatistiksel olarak anlamlı seviyede
- Max drawdown kabul edilebilir sınırda
- TradingView ve Python backtest davranışı yön olarak tutarlı
- Forward paper test backtest davranışından kopmuyor

## Mevcut sınırlamalar

- Python engine makro BTC.D/TOTAL2/TOTAL3 filtresini henüz replikasyon olarak içermez.
- Funding CSV henüz zaman bazlı PnL'e birebir bağlanmadı; yaklaşık funding bps kullanılır.
- Exchange precision/min-notional validasyonu ayrı fazda eklenecek.
- Canlı emir sistemi bu fazda açılmadı.

## Sonraki mikro görevler

1. Funding CSV'yi trade süresine göre PnL'e bağla.
2. Makro veri CSV desteği ekle.
3. Walk-forward split ekle.
4. Parameter sweep ekle.
5. Raporlara long/short ayrı metrikleri ekle.
6. Dashboard'a backtest raporu okuma paneli ekle.
