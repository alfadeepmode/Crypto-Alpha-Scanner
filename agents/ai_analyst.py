"""AI Analyst Agent - deterministic alpha scoring layer."""

from models.schemas import TokenData, WhaleMove, SocialSignal, AlphaSignal
from agents.alpha_model import HeuristicAlphaModel
import os


class AIAnalystAgent:
    """Token verisini olculebilir alpha modelinden gecirir."""

    SYSTEM_PROMPT = """LLM aciklama katmanidir; skor ve aksiyon yerel alpha modelinden gelir."""

    def __init__(self):
        self.model = os.getenv("AI_MODEL", "gpt-4o")
        self.alpha_model = HeuristicAlphaModel()

    def analyze_token(self, token: TokenData, whale: WhaleMove = None, social: SocialSignal = None) -> AlphaSignal:
        """Bir token'i feature/probability modeliyle analiz et."""
        result = self.alpha_model.score(token, whale, social)
        signal_type = "trending"
        if whale:
            signal_type = "whale"
        elif social:
            signal_type = "social"

        signal = AlphaSignal(
            token=token,
            signal_type=signal_type,
            confidence=result.confidence,
            risk_score=result.risk_score,
            action=result.action,
            reasoning=f"{result.reasoning} | model={self.alpha_model.version} | hash={result.feature_hash}",
            related_whale=whale,
            related_social=social,
        )
        signal.prob_up = result.prob_up
        signal.prob_down = result.prob_down
        signal.prob_no_trade = result.prob_no_trade
        signal.feature_hash = result.feature_hash
        signal.model_version = self.alpha_model.version
        signal.features = result.features.to_dict()
        return signal

    def analyze_batch(self, tokens: list[TokenData], whales: list[WhaleMove] = None) -> list[AlphaSignal]:
        """Token listesini analiz et."""
        signals = []
        whale_map = {}
        if whales:
            for w in whales:
                whale_map[w.token_address] = w

        for token in tokens:
            whale = whale_map.get(token.address)
            signal = self.analyze_token(token, whale)
            signals.append(signal)

        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals
