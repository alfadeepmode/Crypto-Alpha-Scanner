"""Measurable alpha probability model.

Faz 6 ilkesi: LLM trade yonunu belirlemez. Bu modul deterministic feature
ve probability uretir; AI/LLM sadece aciklama katmani olarak kalabilir.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import exp

from models.schemas import TokenData, WhaleMove, SocialSignal


@dataclass
class AlphaFeatures:
    liquidity_score: float
    volume_score: float
    whale_score: float
    social_score: float
    verification_score: float
    risk_penalty: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AlphaProbability:
    prob_up: float
    prob_down: float
    prob_no_trade: float
    confidence: float
    risk_score: float
    action: str
    feature_hash: str
    reasoning: str
    features: AlphaFeatures

    def to_dict(self) -> dict:
        data = asdict(self)
        data["features"] = self.features.to_dict()
        return data


class HeuristicAlphaModel:
    """Deterministic, auditable alpha model for research/paper mode."""

    version = "heuristic-alpha-v1"

    def score(self, token: TokenData, whale: WhaleMove | None = None, social: SocialSignal | None = None) -> AlphaProbability:
        liquidity_score = self._bounded_log_score(token.liquidity_usd, floor=50_000, ceiling=1_000_000)
        volume_score = self._bounded_log_score(token.volume_24h, floor=25_000, ceiling=500_000)
        whale_score = 0.0
        if whale:
            whale_size_score = self._bounded_log_score(whale.value_usd, floor=10_000, ceiling=1_000_000)
            whale_score = whale_size_score if whale.is_buy else -0.60 * whale_size_score

        social_score = 0.0
        if social:
            social_score += max(-1.0, min(1.0, social.sentiment)) * 0.45
            social_score += min(social.engagement / 500, 1.0) * 0.25

        verification_score = 0.25 if token.is_verified else 0.0
        risk_penalty = 0.0
        if token.is_honeypot:
            risk_penalty += 1.25
        if token.liquidity_usd < 50_000:
            risk_penalty += 0.45
        if token.volume_24h < 10_000:
            risk_penalty += 0.35

        features = AlphaFeatures(
            liquidity_score=round(liquidity_score, 6),
            volume_score=round(volume_score, 6),
            whale_score=round(whale_score, 6),
            social_score=round(social_score, 6),
            verification_score=round(verification_score, 6),
            risk_penalty=round(risk_penalty, 6),
        )

        edge = (
            0.85 * liquidity_score
            + 0.70 * volume_score
            + 0.65 * whale_score
            + 0.35 * social_score
            + verification_score
            - risk_penalty
        )
        risk_raw = max(0.0, 0.35 + risk_penalty - 0.20 * liquidity_score - 0.15 * volume_score)

        prob_up = self._sigmoid(edge - 0.85)
        prob_down = self._sigmoid(risk_raw - 0.75)
        prob_no_trade = max(0.0, 1.0 - max(prob_up, prob_down))

        confidence = max(prob_up, prob_down) * 100
        risk_score = min(99.0, max(1.0, prob_down * 100 + risk_penalty * 18))

        if prob_up >= 0.62 and risk_score <= 35:
            action = "buy"
        elif prob_down >= 0.62 or risk_score >= 70:
            action = "sell"
        elif max(prob_up, prob_down) >= 0.50:
            action = "watch"
        else:
            action = "ignore"

        reasoning = self._reasoning(features, prob_up, prob_down, risk_score)
        feature_hash = self._feature_hash(features)
        return AlphaProbability(
            prob_up=round(prob_up, 6),
            prob_down=round(prob_down, 6),
            prob_no_trade=round(prob_no_trade, 6),
            confidence=round(confidence, 3),
            risk_score=round(risk_score, 3),
            action=action,
            feature_hash=feature_hash,
            reasoning=reasoning,
            features=features,
        )

    @staticmethod
    def _bounded_log_score(value: float, floor: float, ceiling: float) -> float:
        if value <= floor:
            return 0.0
        if value >= ceiling:
            return 1.0
        span = ceiling - floor
        return max(0.0, min(1.0, (value - floor) / span))

    @staticmethod
    def _sigmoid(x: float) -> float:
        return 1 / (1 + exp(-x))

    @staticmethod
    def _feature_hash(features: AlphaFeatures) -> str:
        raw = "|".join(f"{k}:{v}" for k, v in sorted(features.to_dict().items()))
        # Stable small non-cryptographic hash for logs.
        acc = 0
        for ch in raw:
            acc = (acc * 131 + ord(ch)) % 1_000_000_007
        return f"haf1:{acc:09d}"

    @staticmethod
    def _reasoning(features: AlphaFeatures, prob_up: float, prob_down: float, risk_score: float) -> str:
        parts = [
            f"prob_up={prob_up:.2f}",
            f"prob_down={prob_down:.2f}",
            f"risk={risk_score:.1f}",
            f"liq={features.liquidity_score:.2f}",
            f"vol={features.volume_score:.2f}",
        ]
        if abs(features.whale_score) > 0:
            parts.append(f"whale={features.whale_score:.2f}")
        if features.risk_penalty > 0:
            parts.append(f"penalty={features.risk_penalty:.2f}")
        return " | ".join(parts)
