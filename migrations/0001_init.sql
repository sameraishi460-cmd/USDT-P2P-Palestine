-- ============================================================
-- USDT P2P Palestine — D1 Migration 0001: Initial Schema
--
-- Converted from SQLite (database.db). Preserves all 26 tables,
-- columns, defaults, unique constraints and foreign keys.
-- D1 uses SQLite engine; datetime('now') is UTC.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ============================================
-- USERS
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    phone TEXT DEFAULT '',
    bank TEXT DEFAULT '',
    iban TEXT DEFAULT '',
    payment_method TEXT DEFAULT '',
    usdt_wallet TEXT DEFAULT '',
    rating REAL DEFAULT 5.0,
    verified INTEGER DEFAULT 0,
    trades_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ACTIVE',
    telegram_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    first_name TEXT DEFAULT '',
    referred_by TEXT DEFAULT ''
);

-- ============================================
-- WALLETS
-- ============================================
CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    balance REAL DEFAULT 0.0,
    locked REAL DEFAULT 0.0,
    FOREIGN KEY (username) REFERENCES users(username)
);

-- ============================================
-- WALLET HISTORY (audit ledger)
-- ============================================
CREATE TABLE IF NOT EXISTS wallet_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    amount REAL NOT NULL,
    balance_before REAL DEFAULT 0,
    balance_after REAL DEFAULT 0,
    reference_id INTEGER DEFAULT 0,
    note TEXT DEFAULT '',
    created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (username) REFERENCES users(username)
);

-- ============================================
-- ADS (USDT P2P)
-- ============================================
CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT NOT NULL,
    title TEXT NOT NULL,
    amount REAL NOT NULL,
    price REAL NOT NULL,
    payment TEXT DEFAULT '',
    status TEXT DEFAULT 'OPEN',
    created TEXT DEFAULT (datetime('now')),
    type TEXT DEFAULT 'SELL',
    min_amount REAL DEFAULT 0,
    max_amount REAL DEFAULT 0,
    FOREIGN KEY (user) REFERENCES users(username)
);

-- ============================================
-- TRADES
-- ============================================
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id INTEGER NOT NULL,
    buyer TEXT NOT NULL,
    seller TEXT NOT NULL,
    amount REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    payment_proof TEXT DEFAULT '',
    escrow_status TEXT DEFAULT 'WAITING',
    usdt_tx_hash TEXT DEFAULT '',
    release_tx_hash TEXT DEFAULT '',
    created TEXT DEFAULT (datetime('now')),
    platform_fee REAL DEFAULT 0,
    dispute_status TEXT DEFAULT '',
    dispute_reason TEXT DEFAULT '',
    dispute_by TEXT DEFAULT '',
    completed_at TEXT,
    FOREIGN KEY (ad_id) REFERENCES ads(id),
    FOREIGN KEY (buyer) REFERENCES users(username),
    FOREIGN KEY (seller) REFERENCES users(username)
);

-- ============================================
-- MESSAGES (trade chat)
-- ============================================
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    receiver TEXT NOT NULL,
    text TEXT NOT NULL,
    created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (sender) REFERENCES users(username),
    FOREIGN KEY (receiver) REFERENCES users(username)
);

-- ============================================
-- NOTIFICATIONS
-- ============================================
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    seen INTEGER DEFAULT 0,
    created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (username) REFERENCES users(username)
);

-- ============================================
-- REVIEWS
-- ============================================
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    from_user TEXT NOT NULL,
    to_user TEXT NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT DEFAULT '',
    created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (trade_id) REFERENCES trades(id),
    FOREIGN KEY (from_user) REFERENCES users(username),
    FOREIGN KEY (to_user) REFERENCES users(username)
);

-- ============================================
-- CASH ADS
-- ============================================
CREATE TABLE IF NOT EXISTS cash_ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT NOT NULL,
    title TEXT NOT NULL,
    amount REAL NOT NULL,
    price REAL NOT NULL,
    payment TEXT DEFAULT '',
    status TEXT DEFAULT 'OPEN',
    created TEXT DEFAULT (datetime('now')),
    city TEXT DEFAULT '',
    location TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    plan TEXT DEFAULT 'week',
    FOREIGN KEY (user) REFERENCES users(username)
);

-- ============================================
-- CASH TRADES
-- ============================================
CREATE TABLE IF NOT EXISTS cash_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id INTEGER NOT NULL,
    buyer TEXT NOT NULL,
    seller TEXT NOT NULL,
    amount REAL NOT NULL,
    price REAL NOT NULL,
    status TEXT DEFAULT 'PENDING',
    created TEXT DEFAULT (datetime('now')),
    meeting_confirmed INTEGER DEFAULT 0,
    meeting_location TEXT DEFAULT '',
    completed_at TEXT,
    FOREIGN KEY (ad_id) REFERENCES cash_ads(id)
);

-- ============================================
-- CASH AD PAYMENTS
-- ============================================
CREATE TABLE IF NOT EXISTS cash_ad_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    plan TEXT DEFAULT 'week',
    amount REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    tx_ref TEXT DEFAULT '',
    created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (ad_id) REFERENCES cash_ads(id)
);

-- ============================================
-- DISPUTES
-- ============================================
CREATE TABLE IF NOT EXISTS disputes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    trade_type TEXT DEFAULT 'USDT',
    opened_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence TEXT DEFAULT '',
    status TEXT DEFAULT 'OPEN',
    admin_decision TEXT DEFAULT '',
    admin_note TEXT DEFAULT '',
    created TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    FOREIGN KEY (trade_id) REFERENCES trades(id)
);

-- ============================================
-- USDT DEPOSITS
-- ============================================
CREATE TABLE IF NOT EXISTS usdt_deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    amount REAL NOT NULL,
    tx_hash TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'PENDING',
    created TEXT DEFAULT (datetime('now')),
    sender_wallet TEXT DEFAULT '',
    confirmed_at TEXT,
    FOREIGN KEY (username) REFERENCES users(username)
);

-- ============================================
-- WITHDRAW REQUESTS
-- ============================================
CREATE TABLE IF NOT EXISTS withdraw_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    amount REAL NOT NULL,
    wallet TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',
    created TEXT DEFAULT (datetime('now')),
    tx_hash TEXT DEFAULT '',
    processed_at TEXT,
    FOREIGN KEY (username) REFERENCES users(username)
);

-- ============================================
-- MARKET PRICE
-- ============================================
CREATE TABLE IF NOT EXISTS market_price (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    usd_ils REAL DEFAULT 3.70,
    usdt_ils REAL DEFAULT 3.70,
    updated TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, 3.70, 3.70);

-- ============================================
-- PLATFORM CONFIG
-- ============================================
CREATE TABLE IF NOT EXISTS platform_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated TEXT DEFAULT (datetime('now'))
);

-- Default commission config
INSERT OR IGNORE INTO platform_config (key, value) VALUES ('p2p_fee_percent', '1.0');
INSERT OR IGNORE INTO platform_config (key, value) VALUES ('cash_fee_percent', '1.0');
INSERT OR IGNORE INTO platform_config (key, value) VALUES ('min_fee', '0.1');
INSERT OR IGNORE INTO platform_config (key, value) VALUES ('max_fee', '100.0');

-- ============================================
-- AUDIT LOG (admin + security actions)
-- ============================================
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    actor_role TEXT DEFAULT 'user',
    action TEXT NOT NULL,
    target TEXT DEFAULT '',
    details TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    created TEXT DEFAULT (datetime('now'))
);

-- ============================================
-- TRADING ENGINE TABLES (schema preserved for the
-- isolated Python trading service — Option D)
-- ============================================

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
    last_scan TEXT,
    last_trade TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

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
    entry_time TEXT DEFAULT (datetime('now')),
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
);

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
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (bot_id) REFERENCES trading_bots(id)
);

CREATE TABLE IF NOT EXISTS trading_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    quantity REAL NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT DEFAULT (datetime('now')),
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
);

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
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trading_equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    unrealized_pnl REAL DEFAULT 0,
    open_positions INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (bot_id) REFERENCES trading_bots(id)
);

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
);

CREATE TABLE IF NOT EXISTS trading_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    model_type TEXT NOT NULL,
    features TEXT DEFAULT '[]',
    parameters TEXT DEFAULT '{}',
    train_start TEXT,
    train_end TEXT,
    train_samples INTEGER DEFAULT 0,
    validation_score REAL DEFAULT 0,
    out_of_sample_score REAL DEFAULT 0,
    is_active INTEGER DEFAULT 0,
    status TEXT DEFAULT 'TRAINED',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trading_backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER,
    symbol TEXT,
    timeframe TEXT,
    start_date TEXT,
    end_date TEXT,
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
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trading_market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL,
    timestamp TEXT NOT NULL,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trading_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trading_performance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    timestamp TEXT DEFAULT (datetime('now'))
);

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
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trading_notification_prefs (
    username TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    daily_reports INTEGER DEFAULT 1,
    min_ai_score REAL DEFAULT 70,
    notify_long INTEGER DEFAULT 1,
    notify_short INTEGER DEFAULT 1,
    notify_tp INTEGER DEFAULT 1,
    notify_sl INTEGER DEFAULT 1,
    notify_signals INTEGER DEFAULT 1,
    notify_errors INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT (datetime('now'))
);
