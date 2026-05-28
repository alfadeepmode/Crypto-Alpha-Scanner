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
from datetime import datetime
from dotenv import load_dotenv

# AutoGen imports
import autogen
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager

# Proje modülleri
from models.schemas import TokenData, WhaleMove, SocialSignal, AlphaSignal, ScanReport
from agents.data_collector import DataCollectorAgent
from agents.filter_agent import FilterAgent
from agents.ai_analyst import AIAnalystAgent
from agents.publisher import PublisherAgent

load_dotenv()


def load_config():
    """Konfigürasyon yükle"""
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def create_autogen_agents(config: dict):
    """AutoGen agent'larını oluştur"""
    llm_config = {
        "config_list": [
            {
                "model": config.get("analysis", {}).get("ai_model", "gpt-4o"),
                "api_key": os.getenv("OPENAI_API_KEY"),
            }
        ],
        "temperature": config.get("agents", {}).get("temperature", 0.3),
    }

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


def run_scan():
    """Ana tarama döngüsü"""
    config = load_config()
    run_id = uuid.uuid4().hex[:8]
    print(f"\n{'='*50}")
    print(f"📡 Crypto Alpha Scanner — Çalışma #{run_id}")
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    # ===== 1. VERİ TOPLAMA =====
    print("▶️ AŞAMA 1: Veri Toplama")
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
    print("\n▶️ AŞAMA 4: Telegrama Yayınla")
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
        llm_config={
            "config_list": [
                {
                    "model": config.get("analysis", {}).get("ai_model", "gpt-4o"),
                    "api_key": os.getenv("OPENAI_API_KEY"),
                }
            ],
        },
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

    if "--autogen" in sys.argv:
        print("🧠 AutoGen GroupChat modu başlatılıyor...\n")
        run_autogen_groupchat()
    else:
        print("⚡ Hızlı tarama modu\n")
        run_scan()
