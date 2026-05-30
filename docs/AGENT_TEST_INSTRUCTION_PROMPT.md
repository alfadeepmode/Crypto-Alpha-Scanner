# Agent Test Instruction Prompt

Aşağıdaki prompt Codex / yerel ajan / terminal ajanı için hazırlanmıştır. Amaç: Crypto-Alpha-Scanner reposunda canlı işlem açmadan lokal backtest, smoke test, dashboard doğrulama ve bilimsel kabul kapısını çalıştırmak.

---

## Kopyala-yapıştır agent promptu

```text
Görev: Crypto-Alpha-Scanner reposunda güvenli lokal araştırma testini çalıştır.

Repo yolu:
- Mevcut klasörde çalışıyorsan bulunduğun dizini kullan.
- Değilsen repo klasörüne gir: Crypto-Alpha-Scanner

Ana güvenlik kuralları:
1. Canlı işlem açma.
2. Mainnet kullanma.
3. API key isteme veya yazma.
4. .env dosyasını değiştirme.
5. TRADING_MODE=live çalıştırma.
6. Sadece paper/research/backtest komutları çalıştır.
7. Hata alırsan komutu tekrar tekrar kör şekilde çalıştırma; önce hatayı raporla.
8. data/ ve reports/ çıktıları lokal kalmalı; bunları commit etme.

Aşama 0 — Repo durumunu kontrol et:
- pwd
- git status
- python --version
- python -m pip --version

Aşama 1 — Bağımlılıkları kur:
- python -m pip install --upgrade pip
- pip install -r requirements.txt

Aşama 2 — Kod bütünlüğü testi:
- python -m compileall -q .
- python tests/smoke_test.py

Başarı kriteri:
- compileall hata vermemeli.
- smoke_test.py başarıyla bitmeli.
- Hata varsa çıktıyı aynen raporla ve dur.

Aşama 3 — BTCUSDT 5m 200 günlük veriyi indir:
- python scripts/fetch_binance_um.py --symbol BTCUSDT --interval 5m --days 200

Başarı kriteri:
- data/klines/BTCUSDT_5m_200d.csv oluşmalı.
- Satır sayısını raporla.

Aşama 4 — Backtest çalıştır:
- python scripts/run_backtest.py --csv data/klines/BTCUSDT_5m_200d.csv --symbol BTCUSDT --interval 5m --days 200

Başarı kriteri:
- reports/BTCUSDT_5m_200d_backtest.json oluşmalı.
- Konsoldaki şu metrikleri raporla:
  - net_profit_usd
  - net_profit_pct
  - max_drawdown_pct
  - win_rate_pct
  - profit_factor
  - expectancy_usd
  - trade_count

Aşama 5 — Bilimsel kabul kapısını çalıştır:
- python scripts/validate_backtest_report.py --report reports/BTCUSDT_5m_200d_backtest.json

Başarı kriteri:
- PASS veya FAIL sonucunu raporla.
- FAIL ise her failure maddesini aynen yaz.

Aşama 6 — Dashboard kontrolü:
- python dashboard.py

Not:
- Dashboard komutu terminali meşgul ederse bu normaldir.
- Tarayıcıda kontrol adresi: http://127.0.0.1:8788
- Dashboard açıldıktan sonra terminali durdurmak için Ctrl+C kullanılabilir.

Final rapor formatı:
1. Smoke test sonucu: PASS/FAIL
2. Veri dosyası: var/yok, satır sayısı
3. Backtest raporu: var/yok
4. Net profit
5. Max drawdown
6. Win rate
7. Profit factor
8. Expectancy
9. Trade count
10. Acceptance gate: PASS/FAIL
11. Hata varsa tam hata çıktısı
12. Sonraki önerilen mikro adım

Kesin yasaklar:
- TRADING_MODE=live çalıştırma.
- LIVE_TRADING=true ayarlama.
- ALLOW_MAINNET=true ayarlama.
- Binance API key isteme.
- Gerçek emir gönderme.
- data/ veya reports/ klasörünü commit etme.

BİTTİ sinyali:
- Tüm aşamalar tamamlanınca son satıra sadece şunu yaz:
BİTTİ
```
