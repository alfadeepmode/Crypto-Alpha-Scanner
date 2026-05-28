import httpx
import os
from models.schemas import AlphaSignal, ScanReport


class TelegramTool:
    """Telegram bot ile bildirim gönderir"""

    BASE_URL = "https://api.telegram.org/bot"

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Telegram'a mesaj gönder"""
        if not self.token or not self.chat_id:
            print("[Telegram] Bot token veya chat ID yok")
            return False

        try:
            url = f"{self.BASE_URL}{self.token}/sendMessage"
            resp = httpx.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"[Telegram] Gönderme hatası: {e}")
            return False

    def format_alpha_signal(self, signal: AlphaSignal) -> str:
        """Alpha sinyalini Telegram mesajına çevir"""
        emoji_map = {
            "buy": "🟢", "sell": "🔴", "watch": "🟡", "ignore": "⚪"
        }
        emoji = emoji_map.get(signal.action, "⚪")

        msg = f"""
{emoji} <b>ALPHA SİNYALİ</b> {emoji}
━━━━━━━━━━━━━━━━
<b>Token:</b> {signal.token.symbol} ({signal.token.name})
<b>Ağ:</b> {signal.token.network}
<b>Fiyat:</b> ${signal.token.price_usd:.8f}
<b>Likitide:</b> ${signal.token.liquidity_usd:,.0f}
<b>Hacim 24s:</b> ${signal.token.volume_24h:,.0f}
<b>Tür:</b> {signal.signal_type}
<b>Güven:</b> %{signal.confidence:.0f} | <b>Risk:</b> %{signal.risk_score:.0f}
<b>Öneri:</b> {signal.action.upper()}
<b>Analiz:</b>
{signal.reasoning[:400]}
"""
        if signal.signal_type == "whale" and signal.related_whale:
            msg += f"\n<b>Balina:</b> `{signal.related_whale.from_address[:10]}...` → `{signal.related_whale.to_address[:10]}...`"
            msg += f"\n<b>Miktar:</b> ${signal.related_whale.value_usd:,.0f}"

        return msg.strip()

    def send_alpha_signal(self, signal: AlphaSignal) -> bool:
        """Alpha sinyalini Telegram'a gönder"""
        msg = self.format_alpha_signal(signal)
        return self.send_message(msg)

    def send_report(self, report: ScanReport) -> bool:
        """Tarama raporunu gönder"""
        msg = f"""
📊 <b>ALPHA TARAMA RAPORU</b> 📊
━━━━━━━━━━━━━━━━
<b>Çalışma:</b> #{report.run_id}
<b>Zaman:</b> {report.timestamp.strftime('%H:%M:%S')}
<b>Taranan Token:</b> {report.tokens_scanned}
<b>Balina Hareketi:</b> {report.whales_detected}
<b>Sosyal Sinyal:</b> {report.social_signals}
<b>Alpha Sinyali:</b> {len(report.alpha_signals)}
━━━━━━━━━━━━━━━━
{report.summary[:200]}
"""
        return self.send_message(msg)
