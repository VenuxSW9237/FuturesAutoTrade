# ============================================================
#   VenuxTech Pullback Bot — config.py
#   Fill in your keys here. That's all you need to do.
# ============================================================

# ── Bybit ───────────────────────────────────────────────────
BYBIT_API_KEY    = "RqCZey0kxd3fip21NE"
BYBIT_API_SECRET = "atPAZGct72vFMnIrpXPNmjSuJBWbe4IpBHXh"
BYBIT_TESTNET    = False  # ← Set False when going live
BYBIT_DEMO       = True      #  For demo to change to live you have to set False or delete this line 

# ── Telegram ────────────────────────────────────────────────
# How to get these:
#   BOT_TOKEN  → Talk to @BotFather on Telegram → /newbot
#   CHAT_ID    → Talk to @userinfobot on Telegram → it gives your ID
TELEGRAM_BOT_TOKEN = "8748119126:AAHItQlIsDphPyEkHhmujpDMh6Cqiz8J0aw"
TELEGRAM_CHAT_ID   = "8616801544"

# ── Strategy ────────────────────────────────────────────────
TREND_TF      = "60"   # 1H  candles for trend
ENTRY_TF      = "15"   # 15M candles for entry
EMA_FAST      = 9
EMA_MID       = 21
EMA_SLOW      = 50
EMA_TREND     = 200
ADX_PERIOD    = 14
ADX_MIN       = 25
RSI_PERIOD    = 14
VOL_MA_PERIOD = 20

# ── Risk ────────────────────────────────────────────────────
RISK_PER_TRADE_PCT   = 1.5   # % of balance per trade
REWARD_RATIO         = 1.5   # TP = 1.5 × SL distance
ATR_SL_MULTIPLIER    = 1.2   # SL = 1.2 × ATR from entry
MAX_OPEN_TRADES      = 5
DAILY_LOSS_LIMIT_PCT = 6.0   # Stop trading if -6% today
MAX_LEVERAGE         = 10

# ── Scanner ─────────────────────────────────────────────────
TOP_PAIRS_COUNT  = 10
MIN_VOLUME_USD   = 10_000_000
CANDLES_NEEDED   = 250
CYCLE_SECONDS    = 60        # Check signals every 60 seconds

# ── All 60 Candidate Pairs ───────────────────────────────────
ALL_PAIRS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
    "DOGEUSDT","AVAXUSDT","LINKUSDT","ADAUSDT","DOTUSDT",
    "UNIUSDT","NEARUSDT","AAVEUSDT","APTUSDT","ARBUSDT",
    "OPUSDT","INJUSDT","SUIUSDT","TIAUSDT","LDOUSDT",
    "STXUSDT","RUNEUSDT","HBARUSDT","EGLDUSDT","KAVAUSDT",
    "GMXUSDT","DYDXUSDT","CRVUSDT","SNXUSDT","GALAUSDT",
    "SANDUSDT","MANAUSDT","APEUSDT","CHZUSDT","ENSUSDT",
    "GRTUSDT","1000PEPEUSDT","WIFUSDT","JUPUSDT","RENDERUSDT",
    "ARKMUSDT","STORJUSDT","CFXUSDT","1000LUNCUSDT","ZILUSDT",
    "QNTUSDT","MASKUSDT","FLOWUSDT","WLDUSDT","PYTHUSDT",
]
