from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class TokenData:
    """Token bilgileri"""
    address: str
    symbol: str
    name: str
    network: str
    price_usd: float = 0.0
    liquidity_usd: float = 0.0
    volume_24h: float = 0.0
    holders: int = 0
    is_honeypot: bool = False
    is_verified: bool = False


@dataclass
class WhaleMove:
    """Balina hareketi"""
    tx_hash: str
    token_address: str
    token_symbol: str
    from_address: str
    to_address: str
    value_usd: float
    network: str
    timestamp: datetime
    is_buy: bool = True  # True: exchange'e giriş (alım sinyali)


@dataclass
class SocialSignal:
    """Sosyal medya sinyali"""
    source: str  # reddit, twitter
    content: str
    sentiment: float = 0.0  # -1.0 to 1.0
    engagement: int = 0
    url: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AlphaSignal:
    """Nihai alpha sinyali"""
    token: TokenData
    signal_type: str  # "whale", "new_token", "trending", "social"
    confidence: float  # 0-100
    reasoning: str = ""
    risk_score: float = 0.0  # 0 (safe) - 100 (risky)
    action: str = "watch"  # "buy", "sell", "watch", "ignore"
    related_whale: Optional[WhaleMove] = None
    related_social: Optional[SocialSignal] = None
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class ScanReport:
    """Tarama raporu"""
    run_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    tokens_scanned: int = 0
    whales_detected: int = 0
    social_signals: int = 0
    alpha_signals: list[AlphaSignal] = field(default_factory=list)
    summary: str = ""
