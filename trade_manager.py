# ============================================================
#   VenuxTech Pullback Bot — trade_manager.py
#   Handles: Break Even, Partial Close, TP2
#   Called every 60s from executor.monitor_open_trades()
# ============================================================

import math
import logging
from bybit_client import session, get_last_price, get_open_position, _round_down, get_instrument_info
from database import get_open_trades, log_trade_close

log = logging.getLogger("trade_manager")
_tg = None


def set_telegram(tg_module):
    global _tg
    _tg = tg_module


# ── Bybit helpers ─────────────────────────────────────────────

def _set_sl(symbol: str, sl: float, side: str):
    """Move stop loss on an open position."""
    try:
        info = get_instrument_info(symbol)
        sl   = _round_down(sl, info["tick_size"])
        resp = session().set_trading_stop(
            category  = "linear",
            symbol    = symbol,
            stopLoss  = str(sl),
            slTriggerBy = "LastPrice",
            positionIdx = 0,
        )
        if resp["retCode"] != 0:
            log.warning(f"SL move failed {symbol}: {resp['retMsg']}")
        else:
            log.info(f"SL moved → {sl} on {symbol}")
    except Exception as e:
        log.warning(f"SL move error {symbol}: {e}")


def _close_partial(symbol: str, side: str, qty: float):
    """Close a portion of a position at market price."""
    try:
        info       = get_instrument_info(symbol)
        qty        = _round_down(qty, info["qty_step"])
        close_side = "Sell" if side == "LONG" else "Buy"
        resp = session().place_order(
            category     = "linear",
            symbol       = symbol,
            side         = close_side,
            orderType    = "Market",
            qty          = str(qty),
            reduceOnly   = True,
            timeInForce  = "GoodTillCancel",
        )
        if resp["retCode"] != 0:
            log.warning(f"Partial close failed {symbol}: {resp['retMsg']}")
        else:
            log.info(f"PARTIAL CLOSE {symbol} {qty} contracts")
    except Exception as e:
        log.warning(f"Partial close error {symbol}: {e}")


# ── Trade State Tracking ──────────────────────────────────────
# Tracks which trades already had BE or partial close applied
# so we don't apply them twice.
_be_applied      = set()   # trade_ids where BE already moved
_partial_applied = set()   # trade_ids where partial close already done


def reset():
    """Call this if bot restarts — clears in-memory state."""
    global _be_applied, _partial_applied
    _be_applied      = set()
    _partial_applied = set()


# ── Main Manager ──────────────────────────────────────────────

def manage_trade(trade: dict):
    """
    Called every 60s for each open trade.
    Applies BE and Partial Close logic.

    Levels:
      BE trigger  = entry + 50% of (tp - entry)   [LONG]
                  = entry - 50% of (entry - tp)   [SHORT]
      TP1         = original tp  (1.5× SL distance)
      TP2         = entry + 3.0× SL distance       [LONG]
                  = entry - 3.0× SL distance       [SHORT]
    """
    trade_id = trade["id"]
    symbol   = trade["symbol"]
    side     = trade["side"]
    entry    = float(trade["entry_price"])
    sl_orig  = float(trade["sl_price"])
    tp1      = float(trade["tp_price"])
    qty      = float(trade["qty"])

    # Calculate key levels
    sl_dist  = abs(entry - sl_orig)
    tp2      = (entry + sl_dist * 3.0) if side == "LONG" else (entry - sl_dist * 3.0)
    be_trigger = (entry + (tp1 - entry) * 0.5) if side == "LONG" else (entry - (entry - tp1) * 0.5)

    try:
        last_price = get_last_price(symbol)
    except Exception as e:
        log.warning(f"Price fetch error {symbol}: {e}")
        return

    # ── Break Even ───────────────────────────────────────────
    if trade_id not in _be_applied:
        be_hit = (last_price >= be_trigger) if side == "LONG" else (last_price <= be_trigger)
        if be_hit:
            log.info(f"BE TRIGGERED {symbol} id={trade_id} | moving SL to entry {entry}")
            _set_sl(symbol, entry, side)
            _be_applied.add(trade_id)
            if _tg:
                _tg.send(
                    f"🔒 <b>BREAK EVEN</b> — {symbol}\n"
                    f"SL moved to entry: {entry}\n"
                    f"Trade cannot lose money now."
                )

    # ── Partial Close at TP1 ──────────────────────────────────
    if trade_id not in _partial_applied:
        tp1_hit = (last_price >= tp1) if side == "LONG" else (last_price <= tp1)
        if tp1_hit:
            partial_qty = qty * 0.5
            log.info(f"TP1 HIT {symbol} id={trade_id} | closing 50% qty={partial_qty:.4f}")
            _close_partial(symbol, side, partial_qty)
            _partial_applied.add(trade_id)

            # Move SL to entry for remaining 50%
            if trade_id not in _be_applied:
                _set_sl(symbol, entry, side)
                _be_applied.add(trade_id)

            if _tg:
                pnl_partial = (last_price - entry) * partial_qty if side == "LONG" \
                              else (entry - last_price) * partial_qty
                _tg.send(
                    f"💰 <b>PARTIAL CLOSE — TP1 HIT</b>\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"Pair   : {symbol}\n"
                    f"Closed : 50% at {last_price}\n"
                    f"PnL    : +${pnl_partial:.4f} USDT\n"
                    f"Remaining 50% running to TP2: {tp2:.6f}\n"
                    f"SL moved to entry (zero risk)"
                )
