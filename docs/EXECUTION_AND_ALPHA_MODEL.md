# Faz 5 + Faz 6 — Execution Safety ve Alpha Probability Model

Bu belge, canlı emir riskini kapalı tutarak testnet-first yürütme güvenliğini ve ölçülebilir alpha modelini tanımlar.

## Faz 5 — Testnet-first execution safety

Varsayılanlar:

```yaml
trading:
  mode: "paper"
  execution_env: "testnet"
  allow_mainnet: false
  binance_testnet: true
```

Ana kurallar:

- `TRADING_MODE=live` olmadan live path çalışmaz.
- `LIVE_TRADING=true` olmadan live path çalışmaz.
- `EXECUTION_ENV=mainnet` olsa bile `ALLOW_MAINNET=true` yoksa mainnet reddedilir.
- `EXECUTION_ENV=testnet` iken `BINANCE_TESTNET=true` yoksa emir reddedilir.
- Eksik API key durumunda emir reddedilir.
- Allowlist dışı sembol reddedilir.

Smoke test tarafından yakalanan durumlar:

- Missing Binance key rejection.
- Mainnet lock rejection.
- Testnet sandbox guard rejection.

## Faz 6 — Measurable alpha model

Eklenen dosya:

```text
agents/alpha_model.py
```

İlke:

- LLM trade yönünü belirlemez.
- Trade sinyali deterministic feature/probability modelinden gelir.
- LLM kullanılırsa sadece açıklama katmanı olabilir.

Model çıktıları:

- `prob_up`
- `prob_down`
- `prob_no_trade`
- `confidence`
- `risk_score`
- `feature_hash`
- `model_version`
- `features`

Modelin kullandığı ilk feature seti:

- liquidity_score
- volume_score
- whale_score
- social_score
- verification_score
- risk_penalty

## Bilimsel kullanım standardı

Bir model veya strateji şu olmadan güvenilir sayılmaz:

- Backtest sonucu
- Forward paper test sonucu
- Maliyet sonrası expectancy
- Drawdown analizi
- En azından temel out-of-sample / walk-forward kontrolü

## Sonraki mikro görevler

1. Exchange precision/min-notional validasyonunu güvenli ayrı modüle ekle.
2. Testnet smoke scriptini API key olmadan dry-run validate modunda çalıştır.
3. Funding CSV'yi trade süresine göre backtest PnL'e bağla.
4. Alpha model feature setine teknik göstergeler ekle:
   - EMA gap
   - RSI
   - MACD histogram slope
   - ATR pct
   - ADX
   - funding rate
   - spread bps
5. Probability calibration raporu ekle.
6. Dashboard'a model probability ve feature hash görünümü ekle.

## Mevcut sınırlama

Bu fazlar güvenlik ve ölçülebilirlik altyapısıdır. Kârlılık ispatı değildir. Kârlılık iddiası için Faz 4 backtest ve forward paper sonuçları gerekir.
