# ============================================================
#   VenuxTech Pullback Bot — executor.py
# ============================================================

import logging
from bybit_client import (get_klines, place_order,
                           get_open_position, get_last_price)
from indicators import compute, get_trend, get_signal
from risk_manager import can_trade, calculate_position, check_daily_loss_limit
from database import (log_trade_open, log_trade_close,
                       get_open_trades)
import trade_manager

log = logging.getLogger("executor")
_tg = None


def set_telegram(tg_module):
    global _tg
    _tg = tg_module
    trade_manager.set_telegram(tg_module)


def process_pair(symbol: str):
    if check_daily_loss_limit():
        return

    open_trades  = get_open_trades()
    open_symbols = [t["symbol"] for t in open_trades]

    allowed, reason = can_trade(symbol, open_symbols)
    if not allowed:
        log.debug(f"SKIP {symbol}: {reason}")
        return

    # ── Fetch candles ────────────────────────────────────────
    try:
        df_1h  = get_klines(symbol, "60",  limit=250)
        df_15m = get_klines(symbol, "15",  limit=250)
    except Exception as e:
        log.error(f"Kline error {symbol}: {e}")
        return

    df_1h  = compute(df_1h)
    df_15m = compute(df_15m)

    # ── Trend + Signal ───────────────────────────────────────
    trend = get_trend(df_1h)
    if trend == "NONE":
        log.debug(f"NO TREND {symbol}")
        return

    signal = get_signal(df_15m, trend)
    if signal is None:
        log.debug(f"NO SIGNAL {symbol} | trend={trend}")
        return

    log.info(f"SIGNAL {symbol} {signal['side']} entry={signal['entry']}")

    # ── Position size ────────────────────────────────────────
    try:
        pos = calculate_position(signal["entry"], signal["sl"])
    except Exception as e:
        log.error(f"Position calc error {symbol}: {e}")
        return

    # ── Re-check before firing ───────────────────────────────
    open_trades  = get_open_trades()
    open_symbols = [t["symbol"] for t in open_trades]
    allowed, reason = can_trade(symbol, open_symbols)
    if not allowed:
        return

    # ── Place order ──────────────────────────────────────────
    bybit_side = "Buy" if signal["side"] == "LONG" else "Sell"
    try:
        order_id = place_order(
            symbol   = symbol,
            side     = bybit_side,
            qty      = pos["qty"],
            sl       = signal["sl"],
            tp       = signal["tp"],
            leverage = pos["leverage"],
        )
    except Exception as e:
        log.error(f"Order failed {symbol}: {e}")
        return

    # ── Log to SQLite ────────────────────────────────────────
    trade_id = log_trade_open(
        symbol   = symbol,
        side     = signal["side"],
        entry    = signal["entry"],
        sl       = signal["sl"],
        tp       = signal["tp"],
        qty      = pos["qty"],
        leverage = pos["leverage"],
        risk     = pos["risk_usdt"],
        order_id = order_id,
    )

    log.info(f"TRADE OPEN id={trade_id} {symbol} {signal['side']} "
             f"qty={pos['qty']} lev={pos['leverage']}x "
             f"risk=${pos['risk_usdt']}")

    # ── Telegram alert ───────────────────────────────────────
    if _tg:
        _tg.alert_trade_opened(
            symbol, signal["side"], signal["entry"],
            signal["sl"], signal["tp"],
            round(pos["qty"], 6), pos["risk_usdt"], pos["leverage"]
        )


def monitor_open_trades():
    """Check if any open trades were closed by SL or TP on Bybit."""
    open_trades = get_open_trades()
    if not open_trades:
        return

    for trade in open_trades:
        symbol   = trade["symbol"]
        trade_id = trade["id"]
        entry    = float(trade["entry_price"])
        sl       = float(trade["sl_price"])
        tp       = float(trade["tp_price"])
        side     = trade["side"]

        try:
            position = get_open_position(symbol)
        except Exception as e:
            log.warning(f"Position check error {symbol}: {e}")
            continue

        if position is not None:
            # ── Still open — run BE and partial close logic ──
            trade_manager.manage_trade(trade)
            continue

        # Position closed by Bybit (SL or TP hit)
        try:
            last_price = get_last_price(symbol)
        except Exception:
            last_price = entry

        if side == "LONG":
            # Determine WIN or LOSS by whether price is closer to TP or SL
            status = "WIN" if abs(last_price - tp) < abs(last_price - sl) else "LOSS"
            pnl    = (last_price - entry) * float(trade["qty"])
        else:
            status = "WIN" if abs(last_price - tp) < abs(last_price - sl) else "LOSS"
            pnl    = (entry - last_price) * float(trade["qty"])

        log_trade_close(trade_id, status, last_price, round(pnl, 4))

        log.info(f"TRADE CLOSE id={trade_id} {symbol} {status} pnl=${pnl:.4f}")

        if _tg:
            _tg.alert_trade_closed(symbol, side, status, entry, last_price, pnl)
