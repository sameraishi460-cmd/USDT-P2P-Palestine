/**
 * D1 Auto-Migration: Creates application tables if they don't exist.
 *
 * Runs on the first request after deployment. Idempotent — safe to call
 * multiple times. Uses IF NOT EXISTS for every statement.
 *
 * This is the fallback for when `wrangler d1 migrations apply` does not
 * run during the Cloudflare Workers Build.
 *
 * Schema is an EXACT copy of:
 *   migrations/0001_init.sql  (tables + seed data)
 *   migrations/0002_indexes.sql (indexes)
 *   migrations/0003_uploads.sql (uploads table + indexes)
 */

// ---------------------------------------------------------------
// Individual CREATE TABLE statements — each is a single D1 call.
// This avoids issues with multi-statement exec() or semicolon splitting.
// ---------------------------------------------------------------
const TABLES: string[] = [
  `CREATE TABLE IF NOT EXISTS users (
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
    referred_by TEXT DEFAULT '',
    email TEXT DEFAULT ''
  )`,

  `CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    balance REAL DEFAULT 0.0,
    locked REAL DEFAULT 0.0,
    FOREIGN KEY (username) REFERENCES users(username)
  )`,

  `CREATE TABLE IF NOT EXISTS wallet_history (
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
  )`,

  `CREATE TABLE IF NOT EXISTS ads (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trades (
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
  )`,

  `CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    receiver TEXT NOT NULL,
    text TEXT NOT NULL,
    created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (sender) REFERENCES users(username),
    FOREIGN KEY (receiver) REFERENCES users(username)
  )`,

  `CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    seen INTEGER DEFAULT 0,
    created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (username) REFERENCES users(username)
  )`,

  `CREATE TABLE IF NOT EXISTS reviews (
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
  )`,

  `CREATE TABLE IF NOT EXISTS cash_ads (
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
  )`,

  `CREATE TABLE IF NOT EXISTS cash_trades (
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
  )`,

  `CREATE TABLE IF NOT EXISTS cash_ad_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    plan TEXT DEFAULT 'week',
    amount REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    tx_ref TEXT DEFAULT '',
    created TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (ad_id) REFERENCES cash_ads(id)
  )`,

  `CREATE TABLE IF NOT EXISTS disputes (
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
  )`,

  `CREATE TABLE IF NOT EXISTS usdt_deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    amount REAL NOT NULL,
    tx_hash TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'PENDING',
    created TEXT DEFAULT (datetime('now')),
    sender_wallet TEXT DEFAULT '',
    confirmed_at TEXT,
    FOREIGN KEY (username) REFERENCES users(username)
  )`,

  `CREATE TABLE IF NOT EXISTS withdraw_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    amount REAL NOT NULL,
    wallet TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',
    created TEXT DEFAULT (datetime('now')),
    tx_hash TEXT DEFAULT '',
    processed_at TEXT,
    FOREIGN KEY (username) REFERENCES users(username)
  )`,

  `CREATE TABLE IF NOT EXISTS market_price (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    usd_ils REAL DEFAULT 3.70,
    usdt_ils REAL DEFAULT 3.70,
    updated TEXT DEFAULT (datetime('now'))
  )`,

  `CREATE TABLE IF NOT EXISTS platform_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated TEXT DEFAULT (datetime('now'))
  )`,

  `CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    actor_role TEXT DEFAULT 'user',
    action TEXT NOT NULL,
    target TEXT DEFAULT '',
    details TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    created TEXT DEFAULT (datetime('now'))
  )`,

  // Trading engine tables (isolated, kept for compatibility)
  `CREATE TABLE IF NOT EXISTS trading_bots (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_positions (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_orders (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_trades (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_signals (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    unrealized_pnl REAL DEFAULT 0,
    open_positions INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (bot_id) REFERENCES trading_bots(id)
  )`,

  `CREATE TABLE IF NOT EXISTS trading_daily_stats (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_models (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_backtests (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL,
    timestamp TEXT NOT NULL,
    fetched_at TEXT DEFAULT (datetime('now'))
  )`,

  `CREATE TABLE IF NOT EXISTS trading_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated TEXT DEFAULT (datetime('now'))
  )`,

  `CREATE TABLE IF NOT EXISTS trading_performance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    timestamp TEXT DEFAULT (datetime('now'))
  )`,

  `CREATE TABLE IF NOT EXISTS trading_scanner_log (
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
  )`,

  `CREATE TABLE IF NOT EXISTS trading_notification_prefs (
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
  )`,

  // Uploads (from migration 0003)
  `CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL,
    kind TEXT NOT NULL,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL,
    created DATETIME DEFAULT CURRENT_TIMESTAMP
  )`,
];

const INDEXES: string[] = [
  `CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)`,
  `CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id)`,
  `CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)`,
  `CREATE INDEX IF NOT EXISTS idx_wallets_username ON wallets(username)`,
  `CREATE INDEX IF NOT EXISTS idx_wallet_history_username ON wallet_history(username, created)`,
  `CREATE INDEX IF NOT EXISTS idx_wallet_history_ref ON wallet_history(reference_id)`,
  `CREATE INDEX IF NOT EXISTS idx_ads_user ON ads(user, status)`,
  `CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status, created)`,
  `CREATE INDEX IF NOT EXISTS idx_trades_buyer ON trades(buyer, status)`,
  `CREATE INDEX IF NOT EXISTS idx_trades_seller ON trades(seller, status)`,
  `CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status, created)`,
  `CREATE INDEX IF NOT EXISTS idx_trades_ad_id ON trades(ad_id)`,
  `CREATE INDEX IF NOT EXISTS idx_trades_escrow ON trades(escrow_status)`,
  `CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(sender, receiver, created)`,
  `CREATE INDEX IF NOT EXISTS idx_notifications_username ON notifications(username, seen)`,
  `CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(username, created)`,
  `CREATE INDEX IF NOT EXISTS idx_reviews_trade ON reviews(trade_id)`,
  `CREATE INDEX IF NOT EXISTS idx_reviews_to_user ON reviews(to_user)`,
  `CREATE INDEX IF NOT EXISTS idx_cash_ads_user ON cash_ads(user, status)`,
  `CREATE INDEX IF NOT EXISTS idx_cash_ads_status ON cash_ads(status, created)`,
  `CREATE INDEX IF NOT EXISTS idx_cash_trades_ad ON cash_trades(ad_id)`,
  `CREATE INDEX IF NOT EXISTS idx_disputes_trade ON disputes(trade_id)`,
  `CREATE INDEX IF NOT EXISTS idx_disputes_status ON disputes(status)`,
  `CREATE INDEX IF NOT EXISTS idx_deposits_username ON usdt_deposits(username, status)`,
  `CREATE INDEX IF NOT EXISTS idx_deposits_status ON usdt_deposits(status, created)`,
  `CREATE INDEX IF NOT EXISTS idx_withdrawals_username ON withdraw_requests(username, status)`,
  `CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdraw_requests(status, created)`,
  `CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor, created)`,
  `CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, created)`,
  `CREATE INDEX IF NOT EXISTS idx_tb_username ON trading_bots(username)`,
  `CREATE INDEX IF NOT EXISTS idx_tp_bot ON trading_positions(bot_id, status)`,
  `CREATE INDEX IF NOT EXISTS idx_tp_symbol ON trading_positions(symbol, status)`,
  `CREATE INDEX IF NOT EXISTS idx_tt_bot ON trading_trades(bot_id, exit_time)`,
  `CREATE INDEX IF NOT EXISTS idx_to_bot ON trading_orders(bot_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_ts_bot ON trading_signals(bot_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_te_bot ON trading_equity(bot_id, timestamp)`,
  `CREATE INDEX IF NOT EXISTS idx_tds_bot_date ON trading_daily_stats(bot_id, date)`,
  `CREATE INDEX IF NOT EXISTS idx_tsl_bot ON trading_scanner_log(bot_id, timestamp)`,
  `CREATE INDEX IF NOT EXISTS idx_uploads_owner ON uploads(owner, created)`,
  `CREATE INDEX IF NOT EXISTS idx_uploads_kind ON uploads(kind)`,
];

const SEEDS: string[] = [
  `INSERT OR IGNORE INTO platform_config (key, value) VALUES ('p2p_fee_percent', '1.0')`,
  `INSERT OR IGNORE INTO platform_config (key, value) VALUES ('cash_fee_percent', '1.0')`,
  `INSERT OR IGNORE INTO platform_config (key, value) VALUES ('min_fee', '0.1')`,
  `INSERT OR IGNORE INTO platform_config (key, value) VALUES ('max_fee', '100.0')`,
  `INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, 3.70, 3.70)`,
];

/**
 * ALTER TABLE migrations for existing databases.
 * These handle columns that were added after the initial migration.
 * Safe to call multiple times (IF NOT EXISTS equivalent via try/catch).
 */
async function runAlterMigrations(db: D1Database): Promise<void> {
  const ALTERS = [
    "ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN first_name TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN referred_by TEXT DEFAULT ''",
    // Phase 3 — email verification
    "ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0",
    // Phase 3 — KYC submission data on verification_requests
    "ALTER TABLE verification_requests ADD COLUMN full_name TEXT DEFAULT ''",
    "ALTER TABLE verification_requests ADD COLUMN country TEXT DEFAULT ''",
    "ALTER TABLE verification_requests ADD COLUMN dob TEXT DEFAULT ''",
    "ALTER TABLE verification_requests ADD COLUMN upload_id TEXT DEFAULT ''",
    "ALTER TABLE verification_requests ADD COLUMN reject_reason TEXT DEFAULT ''",
  ];
  for (const sql of ALTERS) {
    try {
      await db.prepare(sql).run();
    } catch {
      // Column already exists — expected
    }
  }
}

/**
 * Check if tables exist and auto-create if missing.
 * Idempotent — safe to call on every request.
 */
export async function ensureTables(db: D1Database): Promise<{ migrated: boolean; tableCount: number }> {
  // Always run ALTER TABLE migrations for existing databases
  await runAlterMigrations(db);

  // Quick check: does platform_config exist?
  try {
    const row = await db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='platform_config'").first();
    if (row) {
      const count = await db.prepare("SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'").first<{ cnt: number }>();
      return { migrated: false, tableCount: count?.cnt ?? 0 };
    }
  } catch { /* table doesn't exist */ }

  // Tables missing — create each table individually
  console.log("[db-init] Tables missing — creating all tables individually...");

  let created = 0;
  for (const sql of TABLES) {
    try {
      await db.prepare(sql).run();
      created++;
    } catch (e: any) {
      if (!e?.message?.includes("already exists")) {
        console.error("[db-init] create table error:", e?.message?.slice(0, 100));
      }
    }
  }

  // Create indexes
  for (const sql of INDEXES) {
    try {
      await db.prepare(sql).run();
    } catch (e: any) {
      if (!e?.message?.includes("already exists")) {
        console.error("[db-init] create index error:", e?.message?.slice(0, 100));
      }
    }
  }

  // Seed config
  for (const sql of SEEDS) {
    try {
      await db.prepare(sql).run();
    } catch { /* ignore duplicates */ }
  }

  console.log(`[db-init] Created ${created}/${TABLES.length} tables`);

  // Run ALTER TABLE migrations again for safety
  await runAlterMigrations(db);

  // Also create V2 tables
  for (const sql of V2_TABLES) {
    try {
      await db.prepare(sql).run();
    } catch (e: any) {
      if (!e?.message?.includes("already exists")) {
        console.error("[db-init] v2 table error:", e?.message?.slice(0, 100));
      }
    }
  }
  for (const sql of V2_INDEXES) {
    try {
      await db.prepare(sql).run();
    } catch (e: any) {
      if (!e?.message?.includes("already exists")) {
        console.error("[db-init] v2 index error:", e?.message?.slice(0, 100));
      }
    }
  }

  const count = await db.prepare("SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'").first<{ cnt: number }>();
  return { migrated: true, tableCount: count?.cnt ?? 0 };
}

/**
 * Ensure V2 tables exist — called separately from ensureTables
 * to guarantee V2 features work even if V1 tables already existed.
 */
export async function ensureV2Tables(db: D1Database): Promise<{ created: boolean; count: number }> {
  let created = 0;
  for (const sql of V2_TABLES) {
    try {
      await db.prepare(sql).run();
      created++;
    } catch (e: any) {
      if (!e?.message?.includes("already exists")) {
        console.error("[db-init] v2 table error:", e?.message?.slice(0, 100));
      }
    }
  }
  for (const sql of V2_INDEXES) {
    try {
      await db.prepare(sql).run();
    } catch (e: any) {
      if (!e?.message?.includes("already exists")) {
        console.error("[db-init] v2 index error:", e?.message?.slice(0, 100));
      }
    }
  }
  return { created: created > 0, count: created };
}

// ============================================================
// V2 TABLES — Trust, Verification, Fraud, Referrals, VIP, etc.
// These are appended to the MIGRATION_SQL in ensureTables()
// ============================================================
const V2_TABLES: string[] = [
  // Trust Score & Ratings (enhanced)
  `CREATE TABLE IF NOT EXISTS user_trust (
    username TEXT PRIMARY KEY,
    trust_score REAL DEFAULT 50.0,
    total_ratings INTEGER DEFAULT 0,
    avg_rating REAL DEFAULT 0.0,
    completed_trades INTEGER DEFAULT 0,
    cancelled_trades INTEGER DEFAULT 0,
    disputed_trades INTEGER DEFAULT 0,
    completion_rate REAL DEFAULT 0.0,
    account_age_days INTEGER DEFAULT 0,
    last_trade_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
  )`,

  // Verification requests
  `CREATE TABLE IF NOT EXISTS verification_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',
    document_type TEXT DEFAULT '',
    document_key TEXT DEFAULT '',
    admin_note TEXT DEFAULT '',
    reviewed_by TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    reviewed_at TEXT,
    FOREIGN KEY (username) REFERENCES users(username)
  )`,

  // Fraud / risk log
  `CREATE TABLE IF NOT EXISTS fraud_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    risk_level TEXT DEFAULT 'LOW',
    event_type TEXT NOT NULL,
    details TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
  )`,

  // Referrals
  `CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer TEXT NOT NULL,
    referred TEXT NOT NULL UNIQUE,
    referral_code TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',
    completed_trades INTEGER DEFAULT 0,
    earnings REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (referrer) REFERENCES users(username),
    FOREIGN KEY (referred) REFERENCES users(username)
  )`,

  // Referral codes
  `CREATE TABLE IF NOT EXISTS referral_codes (
    code TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    total_referred INTEGER DEFAULT 0,
    total_earnings REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
  )`,

  // Promo / coupon codes
  `CREATE TABLE IF NOT EXISTS promo_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    discount_type TEXT DEFAULT 'PERCENT',
    discount_value REAL DEFAULT 0,
    max_discount REAL DEFAULT 0,
    min_trade_amount REAL DEFAULT 0,
    max_uses INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0,
    per_user_limit INTEGER DEFAULT 1,
    expires_at TEXT,
    active INTEGER DEFAULT 1,
    created_by TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
  )`,

  // Promo code usage
  `CREATE TABLE IF NOT EXISTS promo_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    trade_id INTEGER DEFAULT 0,
    discount_applied REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (promo_id) REFERENCES promo_codes(id),
    UNIQUE(promo_id, username)
  )`,

  // Featured ads
  `CREATE TABLE IF NOT EXISTS featured_ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id INTEGER NOT NULL UNIQUE,
    featured_by TEXT DEFAULT '',
    start_date TEXT DEFAULT (datetime('now')),
    end_date TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (ad_id) REFERENCES ads(id)
  )`,

  // Activity log (expanded audit trail for admin timeline)
  `CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    username TEXT DEFAULT '',
    target_type TEXT DEFAULT '',
    target_id TEXT DEFAULT '',
    details TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
  )`,

  // Risk scores per user
  `CREATE TABLE IF NOT EXISTS user_risk (
    username TEXT PRIMARY KEY,
    risk_score INTEGER DEFAULT 0,
    risk_level TEXT DEFAULT 'LOW',
    failed_logins INTEGER DEFAULT 0,
    rapid_trades INTEGER DEFAULT 0,
    cancelled_count INTEGER DEFAULT 0,
    dispute_count INTEGER DEFAULT 0,
    rate_limit_hits INTEGER DEFAULT 0,
    last_flag_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
  )`,

  // Telegram auth codes — temporary tokens for website ↔ Telegram linking
  `CREATE TABLE IF NOT EXISTS telegram_auth_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    telegram_user_id TEXT NOT NULL,
    telegram_username TEXT DEFAULT '',
    action TEXT NOT NULL DEFAULT 'login',
    used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
  )`,

  // Phase 3 — server-side revocable sessions (active sessions / logout-all)
  `CREATE TABLE IF NOT EXISTS user_sessions (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    user_agent TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    revoked INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    last_active TEXT DEFAULT (datetime('now'))
  )`,

  // Phase 3 — hashed, expiring, single-use auth tokens (email verify + password reset)
  `CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    username TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
  )`,

  // Telegram notification preferences per user
  `CREATE TABLE IF NOT EXISTS telegram_prefs (
    username TEXT PRIMARY KEY,
    notify_trades INTEGER DEFAULT 1,
    notify_payments INTEGER DEFAULT 1,
    notify_disputes INTEGER DEFAULT 1,
    notify_system INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT (datetime('now'))
  )`,

  // Phase 3 — login / security activity trail
  `CREATE TABLE IF NOT EXISTS login_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (username) REFERENCES users(username)
  )`,
];

const V2_INDEXES: string[] = [
  `CREATE INDEX IF NOT EXISTS idx_user_sessions_username ON user_sessions(username, revoked)`,
  `CREATE INDEX IF NOT EXISTS idx_auth_tokens_type ON auth_tokens(type, username)`,
  `CREATE INDEX IF NOT EXISTS idx_verify_req_status ON verification_requests(status, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_trust_score ON user_trust(trust_score DESC)`,
  `CREATE INDEX IF NOT EXISTS idx_verify_status ON verification_requests(username, status)`,
  `CREATE INDEX IF NOT EXISTS idx_fraud_user ON fraud_log(username, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_fraud_level ON fraud_log(risk_level)`,
  `CREATE INDEX IF NOT EXISTS idx_referral_code ON referrals(referral_code)`,
  `CREATE INDEX IF NOT EXISTS idx_referral_referrer ON referrals(referrer)`,
  `CREATE INDEX IF NOT EXISTS idx_refcode_code ON referral_codes(code)`,
  `CREATE INDEX IF NOT EXISTS idx_promo_code ON promo_codes(code)`,
  `CREATE INDEX IF NOT EXISTS idx_promo_active ON promo_codes(active, expires_at)`,
  `CREATE INDEX IF NOT EXISTS idx_featured_ad ON featured_ads(ad_id, active)`,
  `CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log(event_type, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(username, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_risk_user ON user_risk(username)`,
  `CREATE INDEX IF NOT EXISTS idx_risk_level ON user_risk(risk_level)`,
  `CREATE INDEX IF NOT EXISTS idx_tg_auth_code ON telegram_auth_codes(code)`,
  `CREATE INDEX IF NOT EXISTS idx_tg_auth_user ON telegram_auth_codes(telegram_user_id)`,
  `CREATE INDEX IF NOT EXISTS idx_tg_prefs_user ON telegram_prefs(username)`,
  `CREATE INDEX IF NOT EXISTS idx_login_activity_user ON login_activity(username, created_at)`,
];
