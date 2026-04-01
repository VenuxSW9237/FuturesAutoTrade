# ============================================================
#   VenuxTech Pullback Bot — indicators.py
#   Pure Python. No pandas. Works on Android.
#   Handles BOTH raw Bybit list format AND dict format.
# ============================================================

from config import (EMA_FAST, EMA_MID, EMA_SLOW, EMA_TREND,
                    ADX_PERIOD, RSI_PERIOD, VOL_MA_PERIOD, ADX_MIN,
                    ATR_SL_MULTIPLIER, REWARD_RATIO)


def _ema(values, period):
    result = [None] * len(values)
    k = 2.0 / (period + 1)
    for i in range(len(values)):
        v = values[i]
        if v is None:
            continue
        if result[i-1] is None and i >= period - 1:
            result[i] = sum(values[i-period+1:i+1]) / period
        elif result[i-1] is not None:
            result[i] = v * k + result[i-1] * (1 - k)
    return result


def _rsi(closes, period):
    result = [None] * len(closes)
    gains, losses = [], []
    avg_g = avg_l = 0
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
        if i < period:
            continue
        if i == period:
            avg_g = sum(gains) / period
            avg_l = sum(losses) / period
        else:
            avg_g = (avg_g * (period - 1) + gains[-1]) / period
            avg_l = (avg_l * (period - 1) + losses[-1]) / period
        rs = avg_g / (avg_l if avg_l != 0 else 1e-10)
        result[i] = 100 - (100 / (1 + rs))
    return result


def _atr(highs, lows, closes, period):
    trs = [None]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1])
        )
        trs.append(tr)
    result = [None] * len(closes)
    for i in range(1, len(trs)):
        if trs[i] is None:
            continue
        if result[i-1] is None and i >= period:
            result[i] = sum(trs[i-period+1:i+1]) / period
        elif result[i-1] is not None:
            result[i] = (result[i-1] * (period - 1) + trs[i]) / period
    return result


def _adx(highs, lows, closes, period):
    n = len(closes)
    di_plus_list  = [None] * n
    di_minus_list = [None] * n
    adx_list      = [None] * n
    atr           = _atr(highs, lows, closes, period)
    pdm_smooth = mdm_smooth = None
    dx_vals = []

    for i in range(1, n):
        up   = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        pdm  = up   if (up > down and up > 0)   else 0.0
        mdm  = down if (down > up and down > 0) else 0.0

        if pdm_smooth is None:
            pdm_smooth = pdm
            mdm_smooth = mdm
        else:
            pdm_smooth = (pdm_smooth * (period-1) + pdm) / period
            mdm_smooth = (mdm_smooth * (period-1) + mdm) / period

        if atr[i] and atr[i] != 0:
            di_plus_list[i]  = 100 * pdm_smooth / atr[i]
            di_minus_list[i] = 100 * mdm_smooth / atr[i]
            dip = di_plus_list[i]
            dim = di_minus_list[i]
            dxv = 100 * abs(dip - dim) / (dip + dim) if (dip + dim) != 0 else 0
            dx_vals.append(dxv)
            if len(dx_vals) >= period:
                if len(dx_vals) == period:
                    adx_list[i] = sum(dx_vals[-period:]) / period
                else:
                    prev = next((adx_list[j] for j in range(i-1, -1, -1)
                                 if adx_list[j] is not None), None)
                    if prev is not None:
                        adx_list[i] = (prev * (period-1) + dxv) / period

    return adx_list, di_plus_list, di_minus_list


def _vol_ma(volumes, period):
    result = [None] * len(volumes)
    for i in range(period - 1, len(volumes)):
        result[i] = sum(volumes[i-period+1:i+1]) / period
    return result


def compute(candles: list) -> dict:
    """
    Accepts EITHER:
      - list of dicts: [{"open":x,"high":x,"low":x,"close":x,"volume":x}, ...]
      - list of lists: [[timestamp,open,high,low,close,volume,...], ...]
    Returns dict of indicator lists.
    """
    if not candles:
        return {}

    # Detect format
    if isinstance(candles[0], dict):
        opens   = [float(c["open"])   for c in candles]
        highs   = [float(c["high"])   for c in candles]
        lows    = [float(c["low"])    for c in candles]
        closes  = [float(c["close"])  for c in candles]
        volumes = [float(c["volume"]) for c in candles]
    else:
        # Raw Bybit format — sort oldest first by timestamp
        candles = sorted(candles, key=lambda x: float(x[0]))
        opens   = [float(c[1]) for c in candles]
        highs   = [float(c[2]) for c in candles]
        lows    = [float(c[3]) for c in candles]
        closes  = [float(c[4]) for c in candles]
        volumes = [float(c[5]) for c in candles]

    adx, di_plus, di_minus = _adx(highs, lows, closes, ADX_PERIOD)

    return {
        "open":     opens,
        "high":     highs,
        "low":      lows,
        "close":    closes,
        "volume":   volumes,
        "ema9":     _ema(closes, EMA_FAST),
        "ema21":    _ema(closes, EMA_MID),
        "ema50":    _ema(closes, EMA_SLOW),
        "ema200":   _ema(closes, EMA_TREND),
        "rsi":      _rsi(closes, RSI_PERIOD),
        "atr":      _atr(highs, lows, closes, ADX_PERIOD),
        "adx":      adx,
        "di_plus":  di_plus,
        "di_minus": di_minus,
        "vol_ma":   _vol_ma(volumes, VOL_MA_PERIOD),
    }


def get_trend(ind_1h: dict) -> str:
    i = -2
    adx      = ind_1h["adx"][i]
    ema200   = ind_1h["ema200"][i]
    ema50    = ind_1h["ema50"][i]
    price    = ind_1h["close"][i]
    di_plus  = ind_1h["di_plus"][i]
    di_minus = ind_1h["di_minus"][i]

    if None in (adx, ema200, ema50, di_plus, di_minus):
        return "NONE"

    up     = price > ema50 > ema200
    down   = price < ema50 < ema200
    strong = adx >= ADX_MIN
    bull   = di_plus  > di_minus
    bear   = di_minus > di_plus

    if up   and strong and bull: return "LONG"
    if down and strong and bear: return "SHORT"
    return "NONE"


def get_signal(ind_15m: dict, trend: str):
    if trend == "NONE":
        return None

    ema21    = ind_15m["ema21"][-2]
    rsi      = ind_15m["rsi"][-2]
    close    = ind_15m["close"][-2]
    atr      = ind_15m["atr"][-2]
    vol      = ind_15m["volume"][-2]
    vol_ma   = ind_15m["vol_ma"][-2]
    prev_low = ind_15m["low"][-3]
    prev_high= ind_15m["high"][-3]
    prev_ema = ind_15m["ema21"][-3]
    open_    = ind_15m["open"][-2]

    if None in (ema21, rsi, atr, vol_ma):
        return None

    vol_ok = vol > vol_ma

    if trend == "LONG":
        if (prev_low <= prev_ema and close > ema21 and
                35 <= rsi <= 55 and vol_ok and close > open_):
            entry = close
            sl = round(entry - atr * ATR_SL_MULTIPLIER, 8)
            tp = round(entry + (entry - sl) * REWARD_RATIO, 8)
            return {"side": "LONG", "entry": entry, "sl": sl, "tp": tp, "atr": atr}

    if trend == "SHORT":
        if (prev_high >= prev_ema and close < ema21 and
                45 <= rsi <= 65 and vol_ok and close < open_):
            entry = close
            sl = round(entry + atr * ATR_SL_MULTIPLIER, 8)
            tp = round(entry - (sl - entry) * REWARD_RATIO, 8)
            return {"side": "SHORT", "entry": entry, "sl": sl, "tp": tp, "atr": atr}

    return None
