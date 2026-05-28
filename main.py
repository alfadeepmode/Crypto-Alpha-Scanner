#!/usr/bin/env python3
"""
Crypto Alpha Scanner - AutoGen Multi-Agent Sistemi
n8n workflow'un AutoGen dönüşümü
"""

import os
import sys
import json
import uuid
import yaml
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# AutoGen is optional. Fast scan mode must work without the classic autogen package.
try:
    from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
except ImportError:
    AssistantAgent = UserProxyAgent = GroupChat = GroupChatManager = None

# Proje modülleri
from models.schemas import TokenData, WhaleMove, SocialSignal, AlphaSignal, ScanReport
from agents.data_collector import DataCollectorAgent
from agents.filter_agent import FilterAgent
from agents.ai_analyst import AIAnalystAgent
from agents.publisher import PublisherAgent
from agents.decision_agent import DecisionAgent
from agents.risk_manager import RiskManager
from agents.future_simulator import FutureSimulator
from agents.orchestration_agent import OrchestrationAgent
from tools.exchange_executor import ExchangeExecutor
from setup_keys import main as run_setup

load_dotenv()



def needs_setup() -> bool:
    """Return True when .env is missing or first-run setup is requested."""
    env_path = Path(".env")
    if not env_path.exists():
        return True
    content = env_path.read_text(encoding="utf-8", errors="ignore")
    required_defaults = ["TRADING_MODE", "TRADING_EXCHANGE", "LIVE_TRADING", "PAPER_TRADES_PATH"]
    return any(key not in content for key in required_defaults)


def maybe_run_startup_setup() -> None:
    """Run interactive setup at startup when explicitly requested or .env is incomplete."""
    if "--no-setup" in sys.argv:
        return
    if "--setup" in sys.argv:
        run_setup()
        load_dotenv(override=True)
        return
    if needs_setup():
        if not sys.stdin.isatty():
            print("⚠️ .env eksik veya tamamlanmamış; non-interactive ortamda setup atlandı. `python main.py --setup` çalıştır.")
            return
        run_setup()
        load_dotenv(override=True)


def load_config():
    """Konfigürasyon yükle"""
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def build_llm_config(config: dict) -> dict | None:
    """Build an optional OpenAI-compatible LLM config for AutoGen."""
    provider = os.getenv("AI_PROVIDER", "openai").lower()
    model = os.getenv("AI_MODEL") or config.get("analysis", {}).get("ai_model", "gpt-4o")

    providers = {
        "openai": {"api_key": os.getenv("OPENAI_API_KEY")},
        "openrouter": {
            "api_key": os.getenv("OPENROUTER_API_KEY"),
            "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        },
        "groq": {
            "api_key": os.getenv("GROQ_API_KEY"),
            "base_url": os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        },
        "github": {
            "api_key": os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"),
            "base_url": os.getenv("GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference"),
        },
        "local": {
            "api_key": os.getenv("LOCAL_AI_API_KEY", "local"),
            "base_url": os.getenv("LOCAL_AI_BASE_URL"),
        },
    }

    selected = providers.get(provider, providers["openai"])
    if not selected.get("api_key") or (provider == "local" and not selected.get("base_url")):
        return None

    config_item = {"model": model, "api_key": selected["api_key"]}
    if selected.get("base_url"):
        config_item["base_url"] = selected["base_url"]

    return {
        "config_list": [config_item],
        "temperature": config.get("agents", {}).get("temperature", 0.3),
    }


def build_sample_raw_data() -> dict:
    """Return deterministic offline market data for smoke tests and demos."""
    tokens = [
        TokenData(
            address="BTC",
            symbol="BTC",
            name="Bitcoin",
            network="binance",
            price_usd=100000.0,
            liquidity_usd=10_000_000.0,
            volume_24h=500_000_000.0,
            is_verified=True,
        ),
        TokenData(
            address="ETH",
            symbol="ETH",
            name="Ethereum",
            network="binance",
            price_usd=3500.0,
            liquidity_usd=8_000_000.0,
            volume_24h=250_000_000.0,
            is_verified=True,
        ),
        TokenData(
            address="LOW",
            symbol="LOW",
            name="Low Liquidity Demo",
            network="ethereum",
            price_usd=0.01,
            liquidity_usd=1_000.0,
            volume_24h=500.0,
        ),
    ]
    return {
        "trending": tokens[:2],
        "new_tokens": tokens[2:],
        "whale_moves": [],
        "reddit_signals": [],
        "total_tokens": len(tokens),
    }


def create_autogen_agents(config: dict):
    """AutoGen agent'larını oluştur"""
    if AssistantAgent is None:
        raise RuntimeError("Classic autogen package is not importable. Fast mode still works; use python main.py.")

    llm_config = build_llm_config(config)
    if llm_config is None:
        raise RuntimeError("No AI provider configured. Set AI_PROVIDER and the matching API key to use --autogen.")

    # ===== UserProxy (sistemi başlatan) =====
    user_proxy = UserProxyAgent(
        name="Orchestrator",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=5,
        code_execution_config=False,
        llm_config=llm_config,
        system_message="Sen orchestratorsun. Veri toplama, filtreleme, analiz ve yayınlama sürecini yönetirsin.",
    )

    # ===== Data Collector =====
    data_collector = AssistantAgent(
        name="DataCollector",
        system_message="""Sen bir kripto veri toplayıcısın. 
DexScreener'dan trend ve yeni tokenları, Etherscan'den balina hareketlerini,
Reddit'ten sosyal sinyalleri toplarsın. Topladığın veriyi özet olarak raporla.""",
        llm_config=llm_config,
    )

    # ===== Filter =====
    filter_agent = AssistantAgent(
        name="FilterAgent",
        system_message="""Sen bir veri filtresisin. 
Gelen verileri düşük likidite, düşük hacim gibi kriterlere göre eleyip 
sadece kaliteli sinyalleri bir sonraki aşamaya gönderirsin.""",
        llm_config=llm_config,
    )

    # ===== AI Analyst =====
    ai_analyst = AssistantAgent(
        name="AIAnalyst",
        system_message="""Sen bir kripto alpha analistsin. Token verilerini, balina hareketlerini 
ve sosyal sinyalleri değerlendirip AL/SAT/İZLE/GEÇ kararı verirsin.
Yüksek güven (>%75) ve düşük risk (<%30) = AL.
Orta güven (%50-75) = İZLE.
Yüksek risk (>%60) veya düşük güven (<%50) = GEÇ.
Her kararını gerekçelendir.""",
        llm_config=llm_config,
    )

    # ===== Publisher =====
    publisher = AssistantAgent(
        name="Publisher",
        system_message="""Sen bir yayıncısın. Analiz sonuçlarını Telegram üzerinden 
kullanıcıya iletirsin. Sinyalleri zengin formatlı mesajlara dönüştürürsün.""",
        llm_config=llm_config,
    )

    return {
        "user_proxy": user_proxy,
        "data_collector": data_collector,
        "filter_agent": filter_agent,
        "ai_analyst": ai_analyst,
        "publisher": publisher,
    }


def run_scan(auto_trade: bool = False, offline: bool = False):
    """Ana tarama döngüsü"""
    config = load_config()
    run_id = uuid.uuid4().hex[:8]
    print(f"\n{'='*50}")
    print(f"📡 Crypto Alpha Scanner — Çalışma #{run_id}")
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # ===== 1. VERİ TOPLAMA =====
    print("▶️ AŞAMA 1: Veri Toplama")
    if offline:
        raw_data = build_sample_raw_data()
        print("[DataCollector] Offline örnek veri kullanılıyor")
        print(DataCollectorAgent().summary(raw_data))
    else:
        collector = DataCollectorAgent()
        raw_data = collector.collect_all()
        print(collector.summary(raw_data))

    # ===== 2. FİLTRELEME =====
    print("\n▶️ AŞAMA 2: Filtreleme")
    filter_agent = FilterAgent()
    filtered_data = filter_agent.run(raw_data)
    print(f"[Filter] İşlem tamam")

    # ===== 3. AI ANALİZ =====
    print("\n▶️ AŞAMA 3: AI Analizi")
    analyst = AIAnalystAgent()
    
    # Tüm tokenları birleştir
    all_tokens = filtered_data["trending"] + filtered_data["new_tokens"]
    all_whales = filtered_data["whale_moves"]
    
    if all_tokens:
        signals = analyst.analyze_batch(all_tokens, all_whales)
        # En iyi sinyalleri göster
        for s in signals[:5]:
            icon = {"buy": "🟢", "watch": "🟡", "ignore": "⚪", "sell": "🔴"}.get(s.action, "⚪")
            print(f"  {icon} {s.token.symbol} → {s.action.upper()} (%{s.confidence:.0f} güven, %{s.risk_score:.0f} risk)")
            print(f"     {s.reasoning}")
    else:
        signals = []
        print("  ⚠️ Filtreleme sonrası analiz edilecek token kalmadı")

    trade_decisions = []
    trade_executions = []
    if auto_trade:
        print("\n▶️ AŞAMA 4: Otomatik Trade Kararı")
        orchestrator = OrchestrationAgent(config)
        trade_decisions, trade_executions = orchestrator.process_signals(signals)

        for decision in trade_decisions[:10]:
            if decision.side == "hold":
                print(f"  HOLD {decision.token.symbol}: {decision.reason}")
            else:
                print(f"  {decision.side.upper()} {decision.token.symbol}: ${decision.amount_usd:.2f} | {decision.reason}")
        for execution in trade_executions:
            print(f"  EXEC {execution.status.upper()} {execution.decision.token.symbol}: {execution.message}")

    # ===== 4. RAPOR OLUŞTUR =====
    report = ScanReport(
        run_id=run_id,
        tokens_scanned=len(all_tokens),
        whales_detected=len(all_whales),
        social_signals=len(filtered_data["reddit_signals"]),
        alpha_signals=signals,
        summary=f"{len(signals)} sinyal üretildi, {sum(1 for s in signals if s.action=='buy')} AL önerisi",
    )

    # ===== 5. YAYINLA =====
    print("\n▶️ AŞAMA 5: Telegrama Yayınla")
    publisher = PublisherAgent()
    
    # Raporu gönder
    publisher.publish_report(report)
    
    # Sinyalleri gönder
    result = publisher.publish_signals(signals)
    print(f"  {result}")

    # ===== 6. ÖZET =====
    print(f"\n{'='*50}")
    print(f"✅ Tarama tamamlandı")
    print(f"📊 {report.tokens_scanned} token tarandı")
    print(f"🐋 {report.whales_detected} balina hareketi")
    print(f"📱 {report.social_signals} sosyal sinyal")
    print(f"💡 {len(signals)} alpha sinyali üretildi")
    print(f"🟢 AL: {sum(1 for s in signals if s.action=='buy')}")
    print(f"🟡 İZLE: {sum(1 for s in signals if s.action=='watch')}")
    print(f"{'='*50}\n")

    return report


def run_watch(auto_trade: bool = True, offline: bool = False) -> None:
    """Continuously run the scanner on the configured interval."""
    config = load_config()
    interval_minutes = float(os.getenv("SCAN_INTERVAL_MINUTES", config.get("schedule", {}).get("interval_minutes", 15)))
    interval_seconds = max(10.0, interval_minutes * 60)
    print(f"🔁 Otomatik tarama başladı: interval={interval_minutes:g} dk, trade={'açık' if auto_trade else 'kapalı'}, offline={offline}")
    print("Durdurmak için Ctrl+C")
    while True:
        started = datetime.now()
        try:
            run_scan(auto_trade=auto_trade, offline=offline)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[watch] Tarama hatası: {exc}")
        elapsed = (datetime.now() - started).total_seconds()
        sleep_for = max(1.0, interval_seconds - elapsed)
        print(f"[watch] Sonraki tarama {sleep_for:.0f} saniye sonra")
        time.sleep(sleep_for)


def run_autogen_groupchat():
    """AutoGen GroupChat modu ile çalıştır (opsiyonel AI sohbetli versiyon)"""
    config = load_config()
    agents = create_autogen_agents(config)

    groupchat = GroupChat(
        agents=list(agents.values()),
        messages=[],
        max_round=12,
    )

    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=build_llm_config(config),
    )

    # Sohbeti başlat
    agents["user_proxy"].initiate_chat(
        manager,
        message="""
Merhaba ekip! Yeni bir alpha taraması başlatıyoruz.
Lütfen sırayla:
1. DataCollector: Verileri topla
2. FilterAgent: Gereksizleri ele
3. AIAnalyst: Analiz et
4. Publisher: Sonuçları yayınla

Başlayalım!
""",
    )


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════╗
║   Crypto Alpha Scanner — AutoGen    ║
║   n8n → Multi-Agent Dönüşümü        ║
╚══════════════════════════════════════╝
    """)

    maybe_run_startup_setup()

    if "--setup" in sys.argv:
        raise SystemExit(0)
    elif "--autogen" in sys.argv:
        print("🧠 AutoGen GroupChat modu başlatılıyor...\n")
        run_autogen_groupchat()
    else:
        auto_trade = "--trade" in sys.argv or os.getenv("AUTO_TRADE") == "true"
        offline = "--offline" in sys.argv or "--smoke" in sys.argv or os.getenv("OFFLINE_MODE") == "true"
        if "--smoke" in sys.argv:
            auto_trade = True
        if "--watch" in sys.argv or "--daemon" in sys.argv or os.getenv("WATCH_MODE") == "true":
            run_watch(auto_trade=True if "--trade" in sys.argv or os.getenv("AUTO_TRADE") == "true" else auto_trade, offline=offline)
        else:
            print("⚡ Hızlı tarama modu" + (" + paper/live trade" if auto_trade else "") + (" + offline" if offline else "") + "\n")
            run_scan(auto_trade=auto_trade, offline=offline)
