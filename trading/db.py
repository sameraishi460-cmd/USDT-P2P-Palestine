"""
AI Trading Engine — Database Schema & Persistence Layer

IMPORTANT: This is COMPLETELY ISOLATED from P2P user funds.
All trading tables use the prefix 'trading_' and have their own
equity tracking. The engine never touches wallets, escrow, or
deposit tables.
"""

import sqlite3
import json
from datetime import datetime


def create_trading_tables(con):
    """Create all trading engine tables."""

    # === BOT STATE ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            status TEXT DEFAULT 'STOPPED',
            mode TEXT DEFAULT 'PAPER',
            capital REAL DEFAULT 10000,
            equity REAL DEFAULT 10000,
            starting_equity REAL DEFAULT 10000,
            daily_start_equity REAL DEFAULT 10000,
            peak_equity REAL DEFAULT 10000,
            total_pnl REAL DEFAULT 0,
            today_pnl REAL DEFAULT 0,
            consecutive_losses INTEGER DEFAULT 0,
            safe_mode INTEGER DEFAULT 0,
            last_scan DATETIME,
            last_trade DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === OPEN POSITIONS ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL DEFAULT 0,
            quantity REAL NOT NULL,
            remaining_qty REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit1 REAL,
            take_profit2 REAL,
            trailing_stop REAL,
            trailing_active INTEGER DEFAULT 0,
            entry_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            entry_ai_score REAL DEFAULT 0,
            entry_tf TEXT DEFAULT '5m',
            regime TEXT DEFAULT '',
            tp1_hit INTEGER DEFAULT 0,
            tp2_hit INTEGER DEFAULT 0,
            break_even INTEGER DEFAULT 0,
            max_price REAL DEFAULT 0,
            min_price REAL DEFAULT 999999,
            pnl REAL DEFAULT 0,
            status TEXT DEFAULT 'OPEN',
            FOREIGN KEY (bot_id) REFERENCES trading_bots(id)
        )
    """)

    # === ORDER HISTORY ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            position_id INTEGER,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            order_type TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            filled_quantity REAL DEFAULT 0,
            status TEXT DEFAULT 'FILLED',
            slippage REAL DEFAULT 0,
            commission REAL DEFAULT 0,
            reason TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bot_id) REFERENCES trading_bots(id)
        )
    """)

    # === COMPLETED TRADES ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            quantity REAL NOT NULL,
            entry_time DATETIME NOT NULL,
            exit_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            pnl REAL DEFAULT 0,
            pnl_pct REAL DEFAULT 0,
            commission REAL DEFAULT 0,
            slippage REAL DEFAULT 0,
            net_pnl REAL DEFAULT 0,
            holding_periods INTEGER DEFAULT 0,
            exit_reason TEXT DEFAULT '',
            ai_score REAL DEFAULT 0,
            regime TEXT DEFAULT '',
            entry_tf TEXT DEFAULT '',
            strategy TEXT DEFAULT '',
            FOREIGN KEY (bot_id) REFERENCES trading_bots(id)
        )
    """)

    # === AI SIGNALS LOG ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            direction TEXT NOT NULL,
            ai_score REAL DEFAULT 0,
            technical_score REAL DEFAULT 0,
            ml_score REAL DEFAULT 0,
            trend_score REAL DEFAULT 0,
            momentum_score REAL DEFAULT 0,
            volume_score REAL DEFAULT 0,
            regime TEXT DEFAULT '',
            entry_price REAL,
            stop_loss REAL,
            take_profit1 REAL,
            take_profit2 REAL,
            rr_ratio REAL DEFAULT 0,
            executed INTEGER DEFAULT 0,
            reject_reason TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === EQUITY SNAPSHOTS ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_equity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            equity REAL NOT NULL,
            cash REAL NOT NULL,
            unrealized_pnl REAL DEFAULT 0,
            open_positions INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bot_id) REFERENCES trading_bots(id)
        )
    """)

    # === DAILY STATS ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            trades_count INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            gross_profit REAL DEFAULT 0,
            gross_loss REAL DEFAULT 0,
            net_pnl REAL DEFAULT 0,
            starting_equity REAL DEFAULT 0,
            ending_equity REAL DEFAULT 0,
            max_drawdown_pct REAL DEFAULT 0,
            win_rate REAL DEFAULT 0,
            profit_factor REAL DEFAULT 0,
            FOREIGN KEY (bot_id) REFERENCES trading_bots(id),
            UNIQUE(bot_id, date)
        )
    """)

    # === ML MODELS ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            model_type TEXT NOT NULL,
            features TEXT DEFAULT '[]',
            parameters TEXT DEFAULT '{}',
            train_start DATETIME,
            train_end DATETIME,
            train_samples INTEGER DEFAULT 0,
            validation_score REAL DEFAULT 0,
            out_of_sample_score REAL DEFAULT 0,
            is_active INTEGER DEFAULT 0,
            status TEXT DEFAULT 'TRAINED',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === BACKTEST RESULTS ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_backtests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER,
            symbol TEXT,
            timeframe TEXT,
            start_date DATETIME,
            end_date DATETIME,
            starting_capital REAL,
            final_capital REAL,
            net_profit REAL,
            roi_pct REAL,
            total_trades INTEGER,
            win_rate REAL,
            profit_factor REAL,
            max_drawdown_pct REAL,
            sharpe_ratio REAL,
            sortino_ratio REAL,
            expectancy REAL,
            avg_trade REAL,
            avg_win REAL,
            avg_loss REAL,
            largest_win REAL,
            largest_loss REAL,
            avg_holding_periods REAL,
            equity_curve TEXT DEFAULT '[]',
            parameters TEXT DEFAULT '{}',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === MARKET DATA CACHE ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL,
            timestamp DATETIME NOT NULL,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === SETTINGS ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === PERFORMANCE MONITORING ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_performance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === SCANNER LOG (Phase 2) ===
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_scanner_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER,
            symbol TEXT NOT NULL,
            scan_result TEXT DEFAULT '{}',
            regime TEXT DEFAULT '',
            regime_confidence REAL DEFAULT 0,
            alignment_score REAL DEFAULT 0,
            best_direction TEXT DEFAULT '',
            best_ai_score REAL DEFAULT 0,
            tradeable INTEGER DEFAULT 0,
            executed INTEGER DEFAULT 0,
            reject_reason TEXT DEFAULT '',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === INDEXES ===
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_tp_bot ON trading_positions(bot_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_tp_symbol ON trading_positions(symbol, status)",
        "CREATE INDEX IF NOT EXISTS idx_tt_bot ON trading_trades(bot_id, exit_time)",
        "CREATE INDEX IF NOT EXISTS idx_tt_symbol ON trading_trades(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_to_bot ON trading_orders(bot_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_ts_bot ON trading_signals(bot_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_te_bot ON trading_equity(bot_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_tds_bot_date ON trading_daily_stats(bot_id, date)",
        "CREATE INDEX IF NOT EXISTS idx_tmd_symbol_tf ON trading_market_data(symbol, timeframe, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_tp_status ON trading_positions(status)",
        "CREATE INDEX IF NOT EXISTS idx_tt_exit ON trading_trades(exit_reason)",
        "CREATE INDEX IF NOT EXISTS idx_tsl_bot ON trading_scanner_log(bot_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_tsl_symbol ON trading_scanner_log(symbol)",
    ]
    for idx in indexes:
        con.execute(idx)

    con.commit()


# ========================================
# PERSISTENCE HELPERS
# ========================================

def get_or_create_bot(con, username):
    """Get or create bot state for a user."""
    bot = con.execute(
        "SELECT * FROM trading_bots WHERE username=?", (username,)
    ).fetchone()
    if not bot:
        from trading.config import DEFAULT_CONFIG
        con.execute(
            """INSERT INTO trading_bots
            (username, status, capital, equity, starting_equity,
             daily_start_equity, peak_equity)
            VALUES (?, 'STOPPED', ?, ?, ?, ?, ?)""",
            (username,
             DEFAULT_CONFIG["starting_capital"],
             DEFAULT_CONFIG["starting_capital"],
             DEFAULT_CONFIG["starting_capital"],
             DEFAULT_CONFIG["starting_capital"],
             DEFAULT_CONFIG["starting_capital"]),
        )
        con.commit()
        bot = con.execute(
            "SELECT * FROM trading_bots WHERE username=?", (username,)
        ).fetchone()
    return bot


def save_position(con, bot_id, pos):
    """Insert a new position."""
    cur = con.execute(
        """INSERT INTO trading_positions
        (bot_id, symbol, side, entry_price, current_price, quantity,
         remaining_qty, stop_loss, take_profit1, take_profit2,
         entry_ai_score, entry_tf, regime)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bot_id, pos["symbol"], pos["side"], pos["entry_price"],
         pos["entry_price"], pos["quantity"], pos["quantity"],
         pos["stop_loss"], pos.get("take_profit1", 0),
         pos.get("take_profit2", 0), pos.get("ai_score", 0),
         pos.get("entry_tf", "5m"), pos.get("regime", "")),
    )
    con.commit()
    return cur.lastrowid


def update_position(con, position_id, **kwargs):
    """Update position fields."""
    sets = []
    vals = []
    for k, v in kwargs.items():
        sets.append(f"{k}=?")
        vals.append(v)
    if sets:
        vals.append(position_id)
        con.execute(
            f"UPDATE trading_positions SET {', '.join(sets)} WHERE id=?",
            vals,
        )
        con.commit()


def close_position(con, position_id, exit_price, exit_reason, pnl, net_pnl, holding_periods):
    """Close a position and record the trade."""
    pos = con.execute(
        "SELECT * FROM trading_positions WHERE id=?", (position_id,)
    ).fetchone()
    if not pos:
        return

    # Record completed trade
    con.execute(
        """INSERT INTO trading_trades
        (bot_id, symbol, side, entry_price, exit_price, quantity,
         entry_time, exit_time, pnl, net_pnl, holding_periods,
         exit_reason, ai_score, regime, entry_tf)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pos["bot_id"], pos["symbol"], pos["side"], pos["entry_price"],
         exit_price, pos["remaining_qty"], pos["entry_time"],
         datetime.now(), pnl, net_pnl, holding_periods,
         exit_reason, pos["entry_ai_score"], pos["regime"], pos["entry_tf"]),
    )

    # Update bot equity
    bot = con.execute(
        "SELECT * FROM trading_bots WHERE id=?", (pos["bot_id"],)
    ).fetchone()
    if bot:
        new_equity = bot["equity"] + net_pnl
        new_total = bot["total_pnl"] + net_pnl
        new_today = bot["today_pnl"] + net_pnl
        peak = max(bot["peak_equity"], new_equity)

        if net_pnl < 0:
            cons = bot["consecutive_losses"] + 1
        else:
            cons = 0

        con.execute(
            """UPDATE trading_bots SET
            equity=?, total_pnl=?, today_pnl=?, peak_equity=?,
            consecutive_losses=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (new_equity, new_total, new_today, peak,
             cons, pos["bot_id"]),
        )

    # Mark position closed
    con.execute(
        "UPDATE trading_positions SET status='CLOSED', pnl=? WHERE id=?",
        (net_pnl, position_id),
    )
    con.commit()


def record_order(con, bot_id, symbol, side, order_type, price, quantity,
                 slippage=0, commission=0, reason="", position_id=None):
    """Record an order execution."""
    con.execute(
        """INSERT INTO trading_orders
        (bot_id, position_id, symbol, side, order_type, price, quantity,
         filled_quantity, slippage, commission, reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (bot_id, position_id, symbol, side, order_type, price, quantity,
         quantity, slippage, commission, reason),
    )
    con.commit()


def record_signal(con, bot_id, signal_data):
    """Record an AI signal."""
    con.execute(
        """INSERT INTO trading_signals
        (bot_id, symbol, timeframe, direction, ai_score, technical_score,
         ml_score, trend_score, momentum_score, volume_score, regime,
         entry_price, stop_loss, take_profit1, take_profit2, rr_ratio,
         executed, reject_reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bot_id, signal_data["symbol"], signal_data.get("timeframe", ""),
         signal_data["direction"], signal_data.get("ai_score", 0),
         signal_data.get("technical_score", 0),
         signal_data.get("ml_score", 0),
         signal_data.get("trend_score", 0),
         signal_data.get("momentum_score", 0),
         signal_data.get("volume_score", 0),
         signal_data.get("regime", ""),
         signal_data.get("entry_price", 0),
         signal_data.get("stop_loss", 0),
         signal_data.get("take_profit1", 0),
         signal_data.get("take_profit2", 0),
         signal_data.get("rr_ratio", 0),
         1 if signal_data.get("executed") else 0,
         signal_data.get("reject_reason", "")),
    )
    con.commit()


def record_equity_snapshot(con, bot_id):
    """Record current equity state."""
    bot = con.execute(
        "SELECT * FROM trading_bots WHERE id=?", (bot_id,)
    ).fetchone()
    if not bot:
        return

    open_pos = con.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(pnl),0) as upnl FROM trading_positions WHERE bot_id=? AND status='OPEN'",
        (bot_id,),
    ).fetchone()

    cash = bot["equity"] - (open_pos["upnl"] or 0)

    con.execute(
        """INSERT INTO trading_equity
        (bot_id, equity, cash, unrealized_pnl, open_positions)
        VALUES (?,?,?,?,?)""",
        (bot_id, bot["equity"], cash,
         open_pos["upnl"] or 0, open_pos["cnt"]),
    )
    con.commit()


def update_daily_stats(con, bot_id):
    """Update today's stats."""
    today = datetime.now().strftime("%Y-%m-%d")
    bot = con.execute(
        "SELECT * FROM trading_bots WHERE id=?", (bot_id,)
    ).fetchone()
    if not bot:
        return

    trades = con.execute(
        """SELECT * FROM trading_trades
        WHERE bot_id=? AND date(exit_time)=?""",
        (bot_id, today),
    ).fetchall()

    wins = sum(1 for t in trades if t["net_pnl"] > 0)
    losses = sum(1 for t in trades if t["net_pnl"] <= 0)
    gross_profit = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gross_loss = abs(sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0))
    net_pnl = sum(t["net_pnl"] for t in trades)
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)

    # Max drawdown today
    peak = bot["peak_equity"]
    dd = ((peak - bot["equity"]) / peak * 100) if peak > 0 else 0

    con.execute(
        """INSERT OR REPLACE INTO trading_daily_stats
        (bot_id, date, trades_count, wins, losses, gross_profit,
         gross_loss, net_pnl, starting_equity, ending_equity,
         max_drawdown_pct, win_rate, profit_factor)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bot_id, today, total, wins, losses, gross_profit,
         gross_loss, net_pnl, bot["daily_start_equity"],
         bot["equity"], dd, win_rate, pf),
    )
    con.commit()


def get_open_positions(con, bot_id):
    """Get all open positions for a bot."""
    return con.execute(
        "SELECT * FROM trading_positions WHERE bot_id=? AND status='OPEN'",
        (bot_id,),
    ).fetchall()


def get_recent_trades(con, bot_id, limit=20):
    """Get recent completed trades."""
    return con.execute(
        "SELECT * FROM trading_trades WHERE bot_id=? ORDER BY exit_time DESC LIMIT ?",
        (bot_id, limit),
    ).fetchall()


def get_trade_stats(con, bot_id):
    """Calculate overall trading statistics."""
    trades = con.execute(
        "SELECT * FROM trading_trades WHERE bot_id=?", (bot_id,)
    ).fetchall()

    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0, "profit_factor": 0, "expectancy": 0,
            "avg_trade": 0, "avg_win": 0, "avg_loss": 0,
            "largest_win": 0, "largest_loss": 0,
            "max_drawdown_pct": 0, "sharpe_ratio": 0,
            "total_net_pnl": 0,
        }

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    total = len(trades)
    gross_profit = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))

    return {
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / total * 100, 1) if total else 0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0),
        "expectancy": round(sum(t["net_pnl"] for t in trades) / total, 2) if total else 0,
        "avg_trade": round(sum(t["net_pnl"] for t in trades) / total, 2) if total else 0,
        "avg_win": round(gross_profit / len(wins), 2) if wins else 0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0,
        "largest_win": round(max((t["net_pnl"] for t in wins), default=0), 2),
        "largest_loss": round(min((t["net_pnl"] for t in losses), default=0), 2),
        "max_drawdown_pct": 0,  # Calculated from equity curve
        "sharpe_ratio": 0,  # Calculated from returns
        "total_net_pnl": round(sum(t["net_pnl"] for t in trades), 2),
    }


def record_scanner_result(con, bot_id, symbol, scan_result, regime_info=None, alignment_info=None,
                          best_score=0, best_direction="", tradeable=False, executed=False, reject_reason=""):
    """Record a scanner result for a symbol."""
    import json
    regime = regime_info.get("composite_regime", "") if regime_info else ""
    regime_conf = regime_info.get("composite_confidence", 0) if regime_info else 0
    alignment = alignment_info.get("alignment_score", 0) if alignment_info else 0

    con.execute(
        """INSERT INTO trading_scanner_log
        (bot_id, symbol, scan_result, regime, regime_confidence,
         alignment_score, best_direction, best_ai_score, tradeable, executed, reject_reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (bot_id, symbol, json.dumps(str(scan_result)[:500]), regime, regime_conf,
         alignment, best_direction, best_score, 1 if tradeable else 0,
         1 if executed else 0, reject_reason),
    )
    con.commit()


def get_recent_scanner_results(con, bot_id, limit=20):
    """Get recent scanner results."""
    return con.execute(
        """SELECT * FROM trading_scanner_log
        WHERE bot_id=? ORDER BY timestamp DESC LIMIT ?""",
        (bot_id, limit),
    ).fetchall()


def get_scanner_summary(con, bot_id):
    """Get summary statistics from scanner log."""
    today = datetime.now().strftime("%Y-%m-%d")

    total = con.execute(
        "SELECT COUNT(*) FROM trading_scanner_log WHERE bot_id=?",
        (bot_id,),
    ).fetchone()[0]

    tradeable = con.execute(
        "SELECT COUNT(*) FROM trading_scanner_log WHERE bot_id=? AND tradeable=1",
        (bot_id,),
    ).fetchone()[0]

    executed = con.execute(
        "SELECT COUNT(*) FROM trading_scanner_log WHERE bot_id=? AND executed=1",
        (bot_id,),
    ).fetchone()[0]

    # Top opportunities today
    top = con.execute(
        """SELECT symbol, best_direction, best_ai_score, regime, alignment_score
        FROM trading_scanner_log
        WHERE bot_id=? AND date(timestamp)=? AND best_ai_score > 0
        ORDER BY best_ai_score DESC LIMIT 5""",
        (bot_id, today),
    ).fetchall()

    return {
        "total_scans": total,
        "tradeable_signals": tradeable,
        "executed_trades": executed,
        "top_opportunities": [dict(t) for t in top],
    }
