# ============================================================
#   VenuxTech Pullback Bot — telegram_bot.py
#   Sends all alerts to your Telegram.
#   Also listens for your commands: /status /trades /pnl /stop
# ============================================================

import logging
import requests
import threading
import time
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger("telegram")

BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Shared flag — /stop command sets this True
_stop_requested = False
_last_update_id = 0


def send(message: str):
    """Send a message to your Telegram chat."""
    try:
        requests.post(
            f"{BASE}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=10
        )
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")


# ── Pre-built Message Templates ───────────────────────────────
def alert_trade_opened(symbol, side, entry, sl, tp, qty, risk_usdt, leverage):
    icon = "🟢" if side == "LONG" else "🔴"
    send(
        f"{icon} <b>TRADE OPENED</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Pair     : <b>{symbol}</b>\n"
        f"Side     : <b>{side}</b>\n"
        f"Entry    : {entry}\n"
        f"Stop Loss: {sl}\n"
        f"Take Prof: {tp}\n"
        f"Qty      : {qty}\n"
        f"Leverage : {leverage}×\n"
        f"Risk     : ${risk_usdt} USDT\n"
        f"━━━━━━━━━━━━━━━━"
    )


def alert_trade_closed(symbol, side, status, entry, close_price, pnl):
    icon = "✅" if status == "WIN" else "❌"
    send(
        f"{icon} <b>TRADE CLOSED — {status}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Pair    : <b>{symbol}</b>\n"
        f"Side    : {side}\n"
        f"Entry   : {entry}\n"
        f"Close   : {close_price}\n"
        f"PnL     : <b>${pnl:+.4f} USDT</b>\n"
        f"━━━━━━━━━━━━━━━━"
    )


def alert_daily_summary(pairs, wins, losses, pnl, balance):
    win_rate = round(wins / max(wins + losses, 1) * 100, 1)
    send(
        f"📊 <b>DAILY SUMMARY</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Trades  : {wins + losses}  (✅{wins} / ❌{losses})\n"
        f"Win Rate: {win_rate}%\n"
        f"Day PnL : <b>${pnl:+.4f} USDT</b>\n"
        f"Balance : ${balance:.2f} USDT\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Tomorrow's pairs:\n" +
        "\n".join(f"  • {p}" for p in pairs)
    )


def alert_daily_stop(pnl_pct, balance):
    send(
        f"🛑 <b>DAILY LOSS LIMIT HIT</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Loss    : {pnl_pct:.2f}%\n"
        f"Balance : ${balance:.2f} USDT\n"
        f"Bot stops until midnight UTC.\n"
        f"Account is protected. 🔒"
    )


def alert_scan_complete(pairs: list):
    send(
        f"🔍 <b>TODAY'S TOP 10 PAIRS</b>\n"
        f"━━━━━━━━━━━━━━━━\n" +
        "\n".join(f"  {i+1}. {p}" for i, p in enumerate(pairs)) +
        f"\n━━━━━━━━━━━━━━━━\n"
        f"Bot is scanning for entries now."
    )


def alert_bot_started(balance, pairs):
    send(
        f"🚀 <b>VENUXTECH BOT STARTED</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Balance : ${balance:.2f} USDT\n"
        f"Pairs   : {len(pairs)} active\n"
        f"Mode    : {'TESTNET 🧪' if __import__('config').BYBIT_TESTNET else 'LIVE 💰'}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Commands:\n"
        f"  /status — Bot health\n"
        f"  /trades — Open trades\n"
        f"  /pnl    — Today's PnL\n"
        f"  /stats  — All-time stats\n"
        f"  /pairs  — Active pairs\n"
        f"  /stop   — Emergency stop"
    )


# ── Command Listener ─────────────────────────────────────────
def is_stop_requested() -> bool:
    return _stop_requested


def _poll_commands(get_status_fn, get_trades_fn, get_pnl_fn,
                   get_stats_fn, get_pairs_fn):
    """Runs in a background thread. Listens for Telegram commands."""
    global _stop_requested, _last_update_id

    while True:
        try:
            resp = requests.get(
                f"{BASE}/getUpdates",
                params={"offset": _last_update_id + 1, "timeout": 30},
                timeout=35
            ).json()

            for update in resp.get("result", []):
                _last_update_id = update["update_id"]
                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip().lower()

                # Only respond to YOUR chat
                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                if text == "/status":
                    send(get_status_fn())

                elif text == "/trades":
                    send(get_trades_fn())

                elif text == "/pnl":
                    send(get_pnl_fn())

                elif text == "/stats":
                    send(get_stats_fn())

                elif text == "/pairs":
                    send(get_pairs_fn())

                elif text == "/stop":
                    _stop_requested = True
                    send("🛑 <b>EMERGENCY STOP ACTIVATED</b>\nBot will not open new trades.\nRestart bot.py to resume.")

        except Exception as e:
            log.warning(f"Telegram poll error: {e}")
            time.sleep(5)


def start_listener(get_status_fn, get_trades_fn, get_pnl_fn,
                   get_stats_fn, get_pairs_fn):
    """Start command listener in background thread."""
    t = threading.Thread(
        target=_poll_commands,
        args=(get_status_fn, get_trades_fn, get_pnl_fn,
              get_stats_fn, get_pairs_fn),
        daemon=True
    )
    t.start()
    log.info("Telegram command listener started.")
