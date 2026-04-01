#!/usr/bin/env python3
# ============================================================
#   VenuxTech Precision Pullback Bot
#   Run: python bot.py
#   Stop: Ctrl+C  or  send /stop on Telegram
# ============================================================

import time
import logging
import schedule
from datetime import datetime, timezone

import config
import telegram_bot as tg
import risk_manager
import executor
from database import (init_db, get_active_pairs, upsert_daily_stats,
                       get_today_pnl, get_all_time_stats)
from pair_scanner import run_scan
from bybit_client import get_wallet_balance

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("venuxtech.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("main")

# Inject telegram into risk_manager and executor
risk_manager.set_telegram(tg)
executor.set_telegram(tg)


# ── Telegram Command Handlers ────────────────────────────────
def cmd_status() -> str:
    stopped = risk_manager.is_bot_stopped()
    balance = get_wallet_balance()
    pnl     = get_today_pnl()
    pairs   = get_active_pairs()
    mode    = "TESTNET 🧪" if config.BYBIT_TESTNET else "LIVE 💰"
    status  = "🛑 STOPPED" if stopped else "✅ RUNNING"
    return (
        f"🤖 <b>BOT STATUS</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Status  : {status}\n"
        f"Mode    : {mode}\n"
        f"Balance : ${balance:.2f} USDT\n"
        f"Day PnL : ${pnl:+.4f} USDT\n"
        f"Pairs   : {len(pairs)} active today\n"
        f"━━━━━━━━━━━━━━━━"
    )


def cmd_trades() -> str:
    from database import get_open_trades
    trades = get_open_trades()
    if not trades:
        return "📭 No open trades right now."
    lines = ["📂 <b>OPEN TRADES</b>\n━━━━━━━━━━━━━━━━"]
    for t in trades:
        icon = "🟢" if t["side"] == "LONG" else "🔴"
        lines.append(
            f"{icon} {t['symbol']} {t['side']}\n"
            f"   Entry: {t['entry_price']} | SL: {t['sl_price']} | TP: {t['tp_price']}"
        )
    return "\n".join(lines)


def cmd_pnl() -> str:
    pnl   = get_today_pnl()
    bal   = get_wallet_balance()
    limit = config.DAILY_LOSS_LIMIT_PCT
    used  = abs(min(0, (pnl / max(bal, 1)) * 100))
    bar   = "█" * int(used) + "░" * max(0, int(limit) - int(used))
    return (
        f"💰 <b>TODAY'S PnL</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"PnL     : <b>${pnl:+.4f} USDT</b>\n"
        f"Balance : ${bal:.2f} USDT\n"
        f"Risk used: [{bar}] {used:.1f}% / {limit}%\n"
        f"━━━━━━━━━━━━━━━━"
    )


def cmd_stats() -> str:
    s = get_all_time_stats()
    return (
        f"📈 <b>ALL-TIME STATS</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Total   : {s['total']} trades\n"
        f"Wins    : ✅ {s['wins']}\n"
        f"Losses  : ❌ {s['losses']}\n"
        f"Win Rate: <b>{s['win_rate']}%</b>\n"
        f"Total PnL: <b>${s['total_pnl']:+.4f} USDT</b>\n"
        f"━━━━━━━━━━━━━━━━"
    )


def cmd_pairs() -> str:
    pairs = get_active_pairs()
    if not pairs:
        return "No pairs selected yet."
    lines = ["🔍 <b>TODAY'S ACTIVE PAIRS</b>\n━━━━━━━━━━━━━━━━"]
    for i, p in enumerate(pairs, 1):
        lines.append(f"  {i}. {p}")
    return "\n".join(lines)


# ── Scheduled Jobs ────────────────────────────────────────────
def midnight_routine():
    log.info("Midnight UTC — running daily routine …")

    # Save closing stats
    try:
        from database import get_open_trades
        trades = get_open_trades()
        wins   = sum(1 for t in trades if t.get("status") == "WIN")
        losses = sum(1 for t in trades if t.get("status") == "LOSS")
        pnl    = get_today_pnl()
        bal    = get_wallet_balance()
        upsert_daily_stats({
            "trades_win": wins, "trades_loss": losses,
            "gross_pnl": pnl,  "balance_close": bal
        })
    except Exception as e:
        log.error(f"Stats error: {e}")

    # Reset daily risk
    risk_manager.reset_daily()

    # Fresh pair scan
    try:
        pairs = run_scan()
        bal   = get_wallet_balance()
        pnl   = get_today_pnl()
        wins  = sum(1 for _ in range(0))   # reset
        tg.alert_daily_summary(pairs, 0, 0, pnl, bal)
        tg.alert_scan_complete(pairs)
    except Exception as e:
        log.error(f"Midnight scan error: {e}")


# ── Trading Cycle ─────────────────────────────────────────────
def trading_cycle():
    if risk_manager.is_bot_stopped():
        return

    # Monitor open trades for SL/TP hits
    try:
        executor.monitor_open_trades()
    except Exception as e:
        log.error(f"Monitor error: {e}")

    # Get today's pairs
    pairs = get_active_pairs()
    if not pairs:
        log.warning("No active pairs — running emergency scan …")
        try:
            pairs = run_scan()
        except Exception as e:
            log.error(f"Emergency scan failed: {e}")
            return

    # Scan each pair for entry signals
    for symbol in pairs:
        if risk_manager.is_bot_stopped():
            break
        try:
            executor.process_pair(symbol)
        except Exception as e:
            log.error(f"Process error {symbol}: {e}")
        time.sleep(0.3)


# ── Startup ───────────────────────────────────────────────────
def startup():
    log.info("=" * 55)
    log.info("  VenuxTech Precision Pullback Bot — STARTING")
    log.info("=" * 55)

    init_db()

    try:
        bal = get_wallet_balance()
        upsert_daily_stats({"balance_open": bal})
        log.info(f"Balance: ${bal:.2f} USDT")
    except Exception as e:
        log.error(f"Balance error on start: {e}")
        bal = 0

    pairs = get_active_pairs()
    if not pairs:
        log.info("No pairs for today — scanning now …")
        try:
            pairs = run_scan()
        except Exception as e:
            log.error(f"Startup scan failed: {e}")
            pairs = []

    # Start Telegram command listener
    tg.start_listener(cmd_status, cmd_trades, cmd_pnl,
                      cmd_stats, cmd_pairs)

    # Notify yourself the bot started
    tg.alert_bot_started(bal, pairs)

    log.info(f"Ready. Watching {len(pairs)} pairs every {config.CYCLE_SECONDS}s")


# ── Main ──────────────────────────────────────────────────────
def main():
    startup()
    schedule.every().day.at("00:00").do(midnight_routine)

    while True:
        try:
            schedule.run_pending()
            trading_cycle()
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            tg.send("⚠️ Bot stopped by user (Ctrl+C)")
            break
        except Exception as e:
            log.error(f"Main loop error: {e}")
        time.sleep(config.CYCLE_SECONDS)


if __name__ == "__main__":
    main()
