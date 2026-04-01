# ============================================================
#   VenuxTech Pullback Bot — pair_scanner.py
#   Pure Python. No pandas. Scores 60 pairs, picks top 10.
# ============================================================

import time
import logging
from config import ALL_PAIRS, TOP_PAIRS_COUNT, MIN_VOLUME_USD
from bybit_client import get_klines, get_24h_volume_usd
from indicators import compute
from database import save_active_pairs, get_active_pairs

log = logging.getLogger("scanner")


def _normalize(values: list) -> list:
    valid = [v for v in values if v is not None]
    if not valid:
        return [0.0] * len(values)
    mn, mx = min(valid), max(valid)
    span = mx - mn if mx != mn else 1e-9
    return [(v - mn) / span if v is not None else 0.0 for v in values]


def _score_pair(symbol: str) -> dict | None:
    try:
        vol_usd = get_24h_volume_usd(symbol)
        if vol_usd < MIN_VOLUME_USD:
            return None

        candles = get_klines(symbol, "60", limit=100)
        if len(candles) < 50:
            return None
        ind     = compute(candles)

        adx   = ind["adx"][-2]
        atr   = ind["atr"][-2]
        close = ind["close"][-2]

        if None in (adx, atr) or close == 0 or adx < 20:
            return None

        return {
            "symbol":    symbol,
            "adx_score": round(adx, 4),
            "volume_usd":float(vol_usd),
            "atr_pct":   round((atr / close) * 100, 6),
            "composite": 0.0,
        }
    except Exception as e:
        log.warning(f"Score error {symbol}: {e}")
        return None


def run_scan() -> list:
    log.info("Daily pair scan — scoring all pairs …")
    results = []

    for symbol in ALL_PAIRS:
        data = _score_pair(symbol)
        if data:
            results.append(data)
        time.sleep(0.15)

    if not results:
        log.error("Scan returned 0 pairs. Keeping yesterday's.")
        return get_active_pairs()

    # Normalize each metric
    adx_norm = _normalize([r["adx_score"]  for r in results])
    vol_norm = _normalize([r["volume_usd"] for r in results])
    atr_norm = _normalize([r["atr_pct"]    for r in results])

    for i, r in enumerate(results):
        r["composite"] = round(
            vol_norm[i] * 0.35 +
            adx_norm[i] * 0.40 +
            atr_norm[i] * 0.25,
            6
        )

    results.sort(key=lambda x: x["composite"], reverse=True)
    top = results[:TOP_PAIRS_COUNT]

    save_active_pairs(top)

    symbols = [r["symbol"] for r in top]
    log.info(f"Top {TOP_PAIRS_COUNT} selected: {symbols}")
    for r in top:
        log.info(
            f"  {r['symbol']:<16} ADX={r['adx_score']:.1f}  "
            f"VOL=${r['volume_usd']/1e6:.0f}M  "
            f"SCORE={r['composite']:.4f}"
        )
    return symbols
