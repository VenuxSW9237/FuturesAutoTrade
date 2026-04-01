# ============================================================
#   VenuxTech Pullback Bot — bybit_client.py
#   Pure Python. No pandas. Returns plain list of dicts.
# ============================================================

import math
import logging
from pybit.unified_trading import HTTP
from config import (BYBIT_API_KEY, BYBIT_API_SECRET,
                    BYBIT_TESTNET, CANDLES_NEEDED, MAX_LEVERAGE)

log = logging.getLogger("bybit")
_session = None


def session() -> HTTP:
    global _session
    if _session is None:
        _session = HTTP(
            testnet=BYBIT_TESTNET,
            demo=True,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
        )
    return _session


def get_klines(symbol: str, interval: str, limit: int = CANDLES_NEEDED) -> list:
    """
    Returns list of dicts:
    [{"timestamp":float, "open":float, "high":float,
      "low":float, "close":float, "volume":float}, ...]
    Sorted oldest → newest.
    """
    resp = session().get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit
    )
    if resp["retCode"] != 0:
        raise RuntimeError(f"Kline error {symbol}: {resp['retMsg']}")

    candles = []
    for r in resp["result"]["list"]:
        candles.append({
            "timestamp": float(r[0]),
            "open":      float(r[1]),
            "high":      float(r[2]),
            "low":       float(r[3]),
            "close":     float(r[4]),
            "volume":    float(r[5]),
        })

    # Bybit returns newest first — reverse to oldest first
    candles.sort(key=lambda c: c["timestamp"])
    return candles


def get_24h_volume_usd(symbol: str) -> float:
    resp = session().get_tickers(category="linear", symbol=symbol)
    if resp["retCode"] != 0:
        return 0.0
    return float(resp["result"]["list"][0].get("turnover24h", 0))


def get_wallet_balance() -> float:
    resp = session().get_wallet_balance(accountType="UNIFIED")
    if resp["retCode"] != 0:
        raise RuntimeError(f"Balance error: {resp['retMsg']}")
    for coin in resp["result"]["list"][0]["coin"]:
        if coin["coin"] == "USDT":
            return float(coin["equity"])
    return 0.0


def get_instrument_info(symbol: str) -> dict:
    resp = session().get_instruments_info(category="linear", symbol=symbol)
    if resp["retCode"] != 0:
        raise RuntimeError(f"Instrument info error: {resp['retMsg']}")
    info = resp["result"]["list"][0]
    lot  = info["lotSizeFilter"]
    return {
        "min_qty":   float(lot["minOrderQty"]),
        "qty_step":  float(lot["qtyStep"]),
        "tick_size": float(info["priceFilter"]["tickSize"]),
    }


def _round_down(value: float, step: float) -> float:
    factor = 1.0 / step
    return math.floor(value * factor) / factor


def set_leverage(symbol: str, leverage: int):
    try:
        session().set_leverage(
            category="linear", symbol=symbol,
            buyLeverage=str(leverage), sellLeverage=str(leverage)
        )
    except Exception as e:
        log.warning(f"Leverage warning {symbol}: {e}")


def place_order(symbol, side, qty, sl, tp, leverage=MAX_LEVERAGE) -> str:
    """Places market order with SL/TP. Returns order ID."""
    info = get_instrument_info(symbol)
    qty  = _round_down(qty, info["qty_step"])
    sl   = _round_down(sl,  info["tick_size"])
    tp   = _round_down(tp,  info["tick_size"])

    if qty < info["min_qty"]:
        raise ValueError(f"{symbol}: qty {qty} below min {info['min_qty']}")

    set_leverage(symbol, leverage)

    resp = session().place_order(
        category="linear", symbol=symbol,
        side=side, orderType="Market",
        qty=str(qty),
        stopLoss=str(sl), takeProfit=str(tp),
        slTriggerBy="LastPrice", tpTriggerBy="LastPrice",
        timeInForce="GoodTillCancel",
        reduceOnly=False, closeOnTrigger=False,
    )
    if resp["retCode"] != 0:
        raise RuntimeError(f"Order failed {symbol}: {resp['retMsg']}")
    return resp["result"].get("orderId", "UNKNOWN")


def get_open_position(symbol: str) -> dict | None:
    resp = session().get_positions(category="linear", symbol=symbol)
    if resp["retCode"] != 0:
        return None
    for p in resp["result"]["list"]:
        if float(p.get("size", 0)) > 0:
            return p
    return None


def get_last_price(symbol: str) -> float:
    candles = get_klines(symbol, "1", limit=3)
    return candles[-1]["close"]
