# Crypto Alpha Scanner — AutoGen Multi-Agent

> **n8n workflow'dan AutoGen multi-agent sistemine dönüştürüldü**

## 🏗️ Mimari

```
DataCollectorAgent → FilterAgent → AIAnalystAgent → PublisherAgent
     (API'ler)      (filtreleme)    (GPT-4o analiz)   (Telegram)
```

## 🚀 Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env dosyasını API anahtarlarınla doldur
```

## ▶️ Çalıştırma

```bash
# Hızlı tarama (doğrudan fonksiyon çağrıları)
python main.py

# AutoGen GroupChat modu (AI ajan sohbeti ile)
python main.py --autogen
```

## 🔑 Gereken API'ler

| API | Zorunlu | Açıklama |
|-----|---------|----------|
| OpenAI | ✅ | GPT-4o analiz |
| Telegram | ✅ | Bildirim |
| Etherscan | ⬜ | On-chain veri |
| Reddit | ⬜ | Sosyal sinyal |
| Whale Alert | ⬜ | Balina takibi |

## 📦 Yapı

```
├── main.py              # Orchestrator
├── agents/
│   ├── data_collector.py
│   ├── filter_agent.py
│   ├── ai_analyst.py
│   └── publisher.py
├── tools/
│   ├── dex_screener.py
│   ├── etherscan.py
│   ├── reddit_scraper.py
│   ├── whale_alert.py
│   └── telegram.py
├── models/
│   └── schemas.py
├── config.yaml
└── .env
```
