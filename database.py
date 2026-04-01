# ============================================================
#   VenuxTech Pullback Bot — database.py
#   SQLite — no installation, no password, just a file.
#   Creates trades.db automatically on first run.
# ============================================================

import sqlite3
import logging
from datetime import date, datetime

log = logging.getLogger("database")
DB_FILE = "trades.db"


def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_pairs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            adx_score   REAL,
            volume_usd  REAL,
            atr_pct     REAL,
            composite   REAL,
            selected_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol         TEXT NOT NULL,
            side           TEXT NOT NULL,
            entry_price    REAL,
            sl_price       REAL,
            tp_price       REAL,
            qty            REAL,
            leverage       INTEGER,
            risk_usdt      REAL,
            bybit_order_id TEXT,
            status         TEXT DEFAULT 'OPEN',
            open_time      TEXT DEFAULT (datetime('now')),
            close_time     TEXT,
            pnl_usdt       REAL DEFAULT 0,
            close_price    REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_date     TEXT UNIQUE NOT NULL,
            trades_total  INTEGER DEFAULT 0,
            trades_win    INTEGER DEFAULT 0,
            trades_loss   INTEGER DEFAULT 0,
            gross_pnl     REAL DEFAULT 0,
            balance_open  REAL DEFAULT 0,
            balance_close REAL DEFAULT 0,
            bot_stopped   INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    log.info("SQLite database ready → trades.db")


# ── Active Pairs ─────────────────────────────────────────────
def save_active_pairs(pair_rows: list):
    today = str(date.today())
    conn  = get_conn()
    cur   = conn.cursor()
    cur.execute("DELETE FROM active_pairs WHERE selected_at=?", (today,))
    for p in pair_rows:
        cur.execute("""
            INSERT INTO active_pairs
              (symbol, adx_score, volume_usd, atr_pct, composite, selected_at)
            VALUES (?,?,?,?,?,?)
        """, (p["symbol"], p["adx_score"], p["volume_usd"],
              p["atr_pct"], p["composite"], today))
    conn.commit()
    conn.close()


def get_active_pairs() -> list[str]:
    today = str(date.today())
    conn  = get_conn()
    cur   = conn.cursor()
    cur.execute("""
        SELECT symbol FROM active_pairs
        WHERE selected_at=?
        ORDER BY composite DESC
    """, (today,))
    rows = cur.fetchall()
    conn.close()
    return [r["symbol"] for r in rows]


# ── Trades ───────────────────────────────────────────────────
def log_trade_open(symbol, side, entry, sl, tp, qty, leverage, risk, order_id) -> int:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO trades
          (symbol, side, entry_price, sl_price, tp_price,
           qty, leverage, risk_usdt, bybit_order_id)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (symbol, side, entry, sl, tp, qty, leverage, risk, order_id))
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def log_trade_close(trade_id, status, close_price, pnl):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        UPDATE trades
        SET status=?, close_price=?, pnl_usdt=?,
            close_time=datetime('now')
        WHERE id=?
    """, (status, close_price, pnl, trade_id))
    conn.commit()
    conn.close()


def get_open_trades() -> list:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM trades WHERE status='OPEN'")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def count_open_trades() -> int:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'")
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_today_pnl() -> float:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT COALESCE(SUM(pnl_usdt), 0)
        FROM trades
        WHERE date(close_time) = date('now')
          AND status IN ('WIN','LOSS')
    """)
    val = cur.fetchone()[0]
    conn.close()
    return float(val)


def get_all_time_stats() -> dict:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT
          COUNT(*) as total,
          SUM(CASE WHEN status='WIN'  THEN 1 ELSE 0 END) as wins,
          SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) as losses,
          ROUND(SUM(pnl_usdt), 4) as total_pnl
        FROM trades
        WHERE status IN ('WIN','LOSS')
    """)
    row = dict(cur.fetchone())
    conn.close()
    total = row["total"] or 1
    row["win_rate"] = round((row["wins"] or 0) / total * 100, 1)
    return row


# ── Daily Stats ───────────────────────────────────────────────
def upsert_daily_stats(data: dict):
    conn = get_conn()
    cur  = conn.cursor()
    today = str(date.today())
    cur.execute("""
        INSERT INTO daily_stats (stat_date, balance_open)
        VALUES (?, ?)
        ON CONFLICT(stat_date) DO UPDATE SET
          trades_total  = excluded.trades_total,
          trades_win    = excluded.trades_win,
          trades_loss   = excluded.trades_loss,
          gross_pnl     = excluded.gross_pnl,
          balance_close = excluded.balance_close,
          bot_stopped   = excluded.bot_stopped
    """, (
        today,
        data.get("balance_open", 0),
    ))

    updates = {k: v for k, v in data.items() if k != "balance_open"}
    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [today]
        cur.execute(f"UPDATE daily_stats SET {set_clause} WHERE stat_date=?", vals)

    conn.commit()
    conn.close()
