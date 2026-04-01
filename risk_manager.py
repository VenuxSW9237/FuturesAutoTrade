# ============================================================
#   VenuxTech Pullback Bot — risk_manager.py
# ============================================================

import logging
from config import (RISK_PER_TRADE_PCT, MAX_OPEN_TRADES,
                    DAILY_LOSS_LIMIT_PCT, MAX_LEVERAGE)
from bybit_client import get_wallet_balance
from database import count_open_trades, get_today_pnl

log = logging.getLogger("risk")

_daily_stopped  = False
_balance_open   = None
_tg             = None   # injected by bot.py to avoid circular import


def set_telegram(tg_module):
    global _tg
    _tg = tg_module


def reset_daily():
    global _daily_stopped, _balance_open
    _daily_stopped = False
    _balance_open  = None
    log.info("Daily risk counters reset.")


def get_open_balance() -> float:
    global _balance_open
    if _balance_open is None:
        _balance_open = get_wallet_balance()
    return _balance_open


def is_bot_stopped() -> bool:
    global _daily_stopped
    # Also check Telegram /stop command
    if _tg and _tg.is_stop_requested():
        _daily_stopped = True
    return _daily_stopped


def check_daily_loss_limit() -> bool:
    global _daily_stopped
    if _daily_stopped:
        return True

    balance_open = get_open_balance()
    if balance_open <= 0:
        return False

    today_pnl = get_today_pnl()
    pnl_pct   = (today_pnl / balance_open) * 100

    if pnl_pct <= -DAILY_LOSS_LIMIT_PCT:
        _daily_stopped = True
        balance_now = get_wallet_balance()
        log.warning(f"Daily loss limit hit: {pnl_pct:.2f}%")
        if _tg:
            _tg.alert_daily_stop(pnl_pct, balance_now)
        return True
    return False


def can_trade(symbol: str, open_symbols: list) -> tuple[bool, str]:
    if is_bot_stopped():
        return False, "Bot stopped"
    if check_daily_loss_limit():
        return False, "Daily loss limit"
    if count_open_trades() >= MAX_OPEN_TRADES:
        return False, f"Max {MAX_OPEN_TRADES} trades open"
    if symbol in open_symbols:
        return False, "Already in trade"
    return True, ""


def calculate_position(entry: float, sl: float) -> dict:
    balance     = get_wallet_balance()
    sl_distance = abs(entry - sl)

    if sl_distance == 0:
        raise ValueError("SL distance is zero")

    risk_usdt = balance * (RISK_PER_TRADE_PCT / 100)
    qty       = risk_usdt / sl_distance
    notional  = qty * entry
    leverage  = max(1, min(int(notional / balance) + 1, MAX_LEVERAGE))

    return {
        "qty":       qty,
        "leverage":  leverage,
        "risk_usdt": round(risk_usdt, 4),
        "balance":   balance,
    }
