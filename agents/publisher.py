"""Publisher Agent - Sinyalleri Telegram'a gönderir"""

from models.schemas import AlphaSignal, ScanReport
from tools.telegram import TelegramTool


class PublisherAgent:
    """Sinyalleri yayınlama ajanı"""

    def __init__(self):
        self.telegram = TelegramTool()

    def publish_signals(self, signals: list[AlphaSignal], max_alerts: int = 5) -> str:
        """Alpha sinyallerini Telegram'a gönder"""
        sent = 0
        for signal in signals[:max_alerts]:
            if signal.action in ("buy", "watch"):
                ok = self.telegram.send_alpha_signal(signal)
                if ok:
                    sent += 1

        result = f"📨 {sent}/{min(len(signals), max_alerts)} sinyal Telegram'a gönderildi"
        print(f"[Publisher] {result}")
        return result

    def publish_report(self, report: ScanReport) -> bool:
        """Tarama raporunu gönder"""
        return self.telegram.send_report(report)

    def format_summary(self, signals: list[AlphaSignal]) -> str:
        """Sinyallerin özet metni"""
        buys = sum(1 for s in signals if s.action == "buy")
        watches = sum(1 for s in signals if s.action == "watch")
        ignores = sum(1 for s in signals if s.action == "ignore")

        return f"""YAYIN RAPORU:
• Toplam Sinyal: {len(signals)}
• AL önerisi: {buys}
• İzle: {watches}
• Geç: {ignores}
"""
