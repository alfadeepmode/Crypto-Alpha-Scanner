"""AI Analyst Agent - GPT-4o ile token analizi yapar"""

from models.schemas import TokenData, WhaleMove, SocialSignal, AlphaSignal
import os
import json


class AIAnalystAgent:
    """Yapay zeka ile alpha sinyali analizi"""

    SYSTEM_PROMPT = """Sen bir kripto alpha analistsin. Görevin:
1. Token verilerini analiz etmek
2. Balina hareketlerini yorumlamak
3. Sosyal medya sinyallerini değerlendirmek
4. Al/sat/izle/geç kararı vermek

Kriterlerin:
- Likidite > $50K ise güvenli kabul et
- Balina girişi (exchange) = bullish sinyal
- Yeni token + yüksek hacim = dikkat et
- Reddit'te aşırı hype = rug-pull riski
- Düşük hacim + yeni token = yüksek risk

Her sinyal için şu JSON formatında çıktı ver:
{
  "confidence": 0-100,
  "risk_score": 0-100,
  "action": "buy/sell/watch/ignore",
  "reasoning": "kısa analiz"
}"""

    def __init__(self):
        self.model = os.getenv("AI_MODEL", "gpt-4o")

    def analyze_token(self, token: TokenData, whale: WhaleMove = None, social: SocialSignal = None) -> AlphaSignal:
        """Bir token'ı tüm verilerle analiz et"""
        # Basit kural bazlı analiz (AutoGen agent asıl analizi yapacak)
        confidence = 50.0
        risk_score = 30.0
        action = "watch"
        reasoning_parts = []

        # Likidite kontrolü
        if token.liquidity_usd > 500000:
            confidence += 15
            reasoning_parts.append("✅ Yüksek likidite")
        elif token.liquidity_usd < 50000:
            risk_score += 20
            reasoning_parts.append("⚠️ Düşük likidite")

        # Hacim kontrolü
        if token.volume_24h > 100000:
            confidence += 10
            reasoning_parts.append("📈 Yüksek hacim")
        elif token.volume_24h < 10000 and token.liquidity_usd > 0:
            risk_score += 15
            reasoning_parts.append("⚠️ Düşük hacim/likidite oranı")

        # Balina kontrolü
        if whale:
            if whale.is_buy:
                confidence += 20
                reasoning_parts.append(f"🐋 Balina alımı ${whale.value_usd:,.0f}")
            else:
                risk_score += 10
                reasoning_parts.append(f"🐋 Balina satışı ${whale.value_usd:,.0f}")
            confidence += 5

        # Sosyal sinyal
        if social:
            if social.engagement > 100:
                confidence += 5
                reasoning_parts.append(f"📱 Sosyal ilgi: {social.engagement}")
            if social.sentiment < -0.5:
                risk_score += 15
                reasoning_parts.append("⚠️ Negatif sosyal duygu")

        # Karar
        if confidence >= 75 and risk_score <= 30:
            action = "buy"
        elif risk_score > 60:
            action = "ignore"
        elif confidence >= 50:
            action = "watch"
        else:
            action = "ignore"

        signal_type = "trending"
        if whale:
            signal_type = "whale"
        elif social:
            signal_type = "social"

        return AlphaSignal(
            token=token,
            signal_type=signal_type,
            confidence=min(confidence, 99),
            risk_score=min(risk_score, 99),
            action=action,
            reasoning=" | ".join(reasoning_parts) if reasoning_parts else "Yeterli veri yok",
            related_whale=whale,
            related_social=social,
        )

    def analyze_batch(self, tokens: list[TokenData], whales: list[WhaleMove] = None) -> list[AlphaSignal]:
        """Token listesini analiz et"""
        signals = []
        whale_map = {}
        if whales:
            for w in whales:
                whale_map[w.token_address] = w

        for token in tokens:
            whale = whale_map.get(token.address)
            signal = self.analyze_token(token, whale)
            signals.append(signal)

        # Güvene göre sırala
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals
