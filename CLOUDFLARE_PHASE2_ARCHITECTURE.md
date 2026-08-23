# USDT-P2P-Palestine — Phase 2: Architecture & Migration Plan

> Status: **DESIGN COMPLETE — AWAITING APPROVAL**
> Date: August 23, 2026
> Commit: (pending approval)

---

## 1. Target Architecture (Final)

```
┌─────────────────────────────────────────────────────────────────┐
│                       Cloudflare Edge                             │
│                                                                   │
│  ┌──────────────────────┐     ┌───────────────────────────────┐  │
│  │   Cloudflare Pages    │     │    Cloudflare Worker API       │  │
│  │   (Static Frontend)   │◄───►│    (Hono / itty-router)       │  │
│  │                       │     │                               │  │
│  │   • index.html         │     │   /api/auth/*                 │  │
│  │   • market.html        │     │   /api/market/*               │  │
│  │   • wallet.html        │     │   /api/trades/*               │  │
│  │   • profile.html       │     │   /api/wallet/*               │  │
│  │   • admin.html         │     │   /api/ads/*                  │  │
│  │   • trade.html         │     │   /api/admin/*                │  │
│  │   • chat.html          │     │   /api/notifications/*        │  │
│  │   • notifications.html │     │   /api/deposits/*             │  │
│  │   • register.html      │     │   /api/withdrawals/*          │  │
│  │   • login.html         │     │   /telegram/webhook           │  │
│  │   • create_ad.html     │     │   /health                     │  │
│  │   • usdt_deposit.html  │     │                               │  │
│  │   • withdraw.html      │     └───────────────┬───────────────┘  │
│  │   • cash_*.html        │                      │                  │
│  │   • base.css           │         ┌────────────┼────────────┐    │
│  │   • app.js             │         │            │            │    │
│  └──────────────────────┘    ┌─────▼─────┐ ┌───▼────┐ ┌────▼───┐│
│                               │  Cloudflare│ │Cloudflare│ │Cloudflare││
│                               │  D1 (SQL)   │ │R2 (Files)│ │Cron    ││
│                               └───────────┘ └────────┘ └────────┘│
│                                                                   │
│  ┌──────────────────┐     ┌──────────────────────────────┐      │
│  │  BSC / USDT RPC   │     │  Telegram Bot API (webhook)  │      │
│  │  (ethers.js)      │     │  (setWebhook → Worker)       │      │
│  └──────────────────┘     └──────────────────────────────┘      │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Trading Engine (SEPARATE — NOT on Workers)              │    │
│  │  Python / pandas / scikit-learn / background threads     │    │
│  │  Optional: Deployed separately (Railway/Fly.io)          │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Final Project Structure

```
usdt-p2p-palestine/
├── wrangler.toml                 # Cloudflare Worker config
├── package.json                  # Node.js dependencies
├── tsconfig.json                 # TypeScript config
├── CLOUDFLARE_MIGRATION.md       # Phase 1 audit
├── CLOUDFLARE_PHASE2_ARCHITECTURE.md  # This document
│
├── src/                          # Cloudflare Worker API
│   ├── index.ts                  # Worker entry point (Hono router)
│   ├── auth.ts                   # Authentication middleware
│   ├── db.ts                     # D1 database helpers
│   ├── routes/
│   │   ├── auth.ts               # /api/auth/* routes
│   │   ├── market.ts             # /api/market/* routes
│   │   ├── ads.ts                # /api/ads/* routes
│   │   ├── trades.ts             # /api/trades/* routes
│   │   ├── wallet.ts             # /api/wallet/* routes
│   │   ├── deposits.ts           # /api/deposits/* routes
│   │   ├── withdrawals.ts        # /api/withdrawals/* routes
│   │   ├── notifications.ts      # /api/notifications/* routes
│   │   ├── admin.ts              # /api/admin/* routes
│   │   ├── cash.ts               # /api/cash/* routes (cash ads/trades)
│   │   └── profile.ts            # /api/profile/* routes
│   ├── telegram/
│   │   ├── webhook.ts            # Telegram webhook handler
│   │   ├── auth.ts               # Telegram WebApp HMAC verification
│   │   └── bot.ts                # Bot commands (start, keyboard, etc.)
│   ├── blockchain/
│   │   ├── bsc.ts                # BSC RPC connection
│   │   └── usdt.ts               # USDT transaction verification
│   ├── cron/
│   │   └── price-updater.ts      # Cron trigger: update market price
│   ├── middleware/
│   │   ├── csrf.ts               # CSRF protection
│   │   ├── rate-limit.ts         # Rate limiting (KV-based)
│   │   ├── security-headers.ts   # Security headers
│   │   └── error-handler.ts      # Error handling
│   └── utils/
│       ├── password.ts           # Password hashing (bcrypt)
│       ├── session.ts            # Session/token management
│       ├── validation.ts         # Input validation
│       └── audit.ts              # Audit logging
│
├── frontend/                     # Cloudflare Pages (static frontend)
│   ├── public/                   # Static assets
│   │   ├── design-system.css     # CSS design system (existing)
│   │   ├── style.css             # Additional styles (existing)
│   │   └── app.js                # Frontend JavaScript
│   ├── index.html                # Landing page
│   ├── login.html                # Login
│   ├── register.html             # Register
│   ├── market.html               # P2P marketplace
│   ├── dashboard.html            # Dashboard
│   ├── wallet.html               # Wallet
│   ├── trade.html                # Trade view/chat
│   ├── profile.html              # User profile
│   ├── notifications.html        # Notifications
│   ├── create_ad.html            # Create USDT ad
│   ├── create_cash_ad.html       # Create cash ad
│   ├── cash_market.html          # Cash marketplace
│   ├── cash_ad.html              # Cash ad detail
│   ├── cash_trade.html           # Cash trade
│   ├── chat.html                 # Trade chat
│   ├── usdt_deposit.html         # Deposit USDT
│   ├── withdraw.html             # Withdraw USDT
│   ├── my_ads.html               # My ads
│   ├── my_trades.html            # My trades
│   ├── edit_profile.html         # Edit profile
│   ├── all_ads.html              # All ads
│   ├── admin.html                # Admin dashboard
│   ├── admin_login.html          # Admin login
│   ├── admin_wallet.html         # Admin wallet view
│   ├── admin_usdt_deposits.html  # Admin deposits
│   ├── admin_cash_ads.html       # Admin cash ads
│   ├── admin_search.html         # Admin search
│   ├── admin_commission.html     # Admin commission
│   ├── admin_price.html          # Admin market price
│   ├── telegram_webapp.html      # Telegram WebApp entry
│   ├── telegram_login.html       # Telegram login
│   ├── 404.html                  # Not found
│   ├── 500.html                  # Server error
│   └── payment_success.html      # Payment success
│
├── migrations/                   # D1 database migrations
│   ├── 0001_init.sql             # Create all tables
│   └── 0002_indexes.sql          # Add indexes
│
├── trading/                      # AI Trading Engine (SEPARATE)
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── engine.py
│   ├── features.py
│   ├── ml_engine.py
│   └── ...                       # Keep all existing Python files
│
├── app.py                        # KEEP as backup reference
├── telegram_bot.py               # KEEP as backup reference
├── price_updater.py              # KEEP as backup reference
├── models.py                     # KEEP as backup reference
├── templates/                    # KEEP as backup reference
└── static/                       # KEEP as backup reference
```

---

## 3. D1 Database Schema Plan

### Migration 0001_init.sql — All 26 Tables

```sql
-- ============================================
-- USDT-P2P-Palestine D1 Schema
-- ============================================

-- USERS
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

-- WALLETS
CREATE TABLE IF NOT EXISTS wallets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  balance REAL DEFAULT 0.0,
  locked REAL DEFAULT 0.0,
  FOREIGN KEY (username) REFERENCES users(username)
);

-- WALLET HISTORY (audit log)
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

-- ADS (USDT P2P)
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

-- TRADES
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

-- MESSAGES (trade chat)
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sender TEXT NOT NULL,
  receiver TEXT NOT NULL,
  text TEXT NOT NULL,
  created TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (sender) REFERENCES users(username),
  FOREIGN KEY (receiver) REFERENCES users(username)
);

-- NOTIFICATIONS
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  seen INTEGER DEFAULT 0,
  created TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (username) REFERENCES users(username)
);

-- REVIEWS
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

-- CASH ADS
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

-- CASH TRADES
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

-- DISPUTES
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

-- USDT DEPOSITS
CREATE TABLE IF NOT EXISTS usdt_deposits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL,
  amount REAL NOT NULL,
  tx_hash TEXT NOT NULL,
  status TEXT DEFAULT 'PENDING',
  created TEXT DEFAULT (datetime('now')),
  sender_wallet TEXT DEFAULT '',
  confirmed_at TEXT,
  FOREIGN KEY (username) REFERENCES users(username)
);

-- WITHDRAW REQUESTS
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

-- MARKET PRICE
CREATE TABLE IF NOT EXISTS market_price (
  id INTEGER PRIMARY KEY,
  usd_ils REAL DEFAULT 3.70,
  usdt_ils REAL DEFAULT 3.70,
  updated TEXT DEFAULT (datetime('now'))
);

-- PLATFORM CONFIG
CREATE TABLE IF NOT EXISTS platform_config (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated TEXT DEFAULT (datetime('now'))
);

-- ============================================
-- TRADING BOT TABLES (kept for future use)
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
```

### Migration 0002_indexes.sql — All Indexes

```sql
-- P2P indexes
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_wallets_username ON wallets(username);
CREATE INDEX IF NOT EXISTS idx_ads_user ON ads(user);
CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status);
CREATE INDEX IF NOT EXISTS idx_trades_buyer ON trades(buyer);
CREATE INDEX IF NOT EXISTS idx_trades_seller ON trades(seller);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_ad_id ON trades(ad_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender, receiver);
CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver);
CREATE INDEX IF NOT EXISTS idx_notifications_username ON notifications(username);
CREATE INDEX IF NOT EXISTS idx_notifications_seen ON notifications(username, seen);
CREATE INDEX IF NOT EXISTS idx_reviews_trade ON reviews(trade_id);
CREATE INDEX IF NOT EXISTS idx_reviews_to_user ON reviews(to_user);
CREATE INDEX IF NOT EXISTS idx_cash_ads_user ON cash_ads(user);
CREATE INDEX IF NOT EXISTS idx_cash_ads_status ON cash_ads(status);
CREATE INDEX IF NOT EXISTS idx_cash_trades_ad ON cash_trades(ad_id);
CREATE INDEX IF NOT EXISTS idx_deposits_username ON usdt_deposits(username);
CREATE INDEX IF NOT EXISTS idx_deposits_status ON usdt_deposits(status);
CREATE INDEX IF NOT EXISTS idx_deposits_tx ON usdt_deposits(tx_hash);
CREATE INDEX IF NOT EXISTS idx_withdrawals_username ON withdraw_requests(username);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdraw_requests(status);
CREATE INDEX IF NOT EXISTS idx_wallet_history_username ON wallet_history(username);
CREATE INDEX IF NOT EXISTS idx_wallet_history_ref ON wallet_history(reference_id);
CREATE INDEX IF NOT EXISTS idx_disputes_trade ON disputes(trade_id);
CREATE INDEX IF NOT EXISTS idx_disputes_status ON disputes(status);

-- Trading bot indexes
CREATE INDEX IF NOT EXISTS idx_tb_username ON trading_bots(username);
CREATE INDEX IF NOT EXISTS idx_tp_bot ON trading_positions(bot_id, status);
CREATE INDEX IF NOT EXISTS idx_tp_symbol ON trading_positions(symbol, status);
CREATE INDEX IF NOT EXISTS idx_tt_bot ON trading_trades(bot_id, exit_time);
CREATE INDEX IF NOT EXISTS idx_tt_symbol ON trading_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_to_bot ON trading_orders(bot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ts_bot ON trading_signals(bot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_te_bot ON trading_equity(bot_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_tds_bot_date ON trading_daily_stats(bot_id, date);
CREATE INDEX IF NOT EXISTS idx_tmd_symbol_tf ON trading_market_data(symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS idx_tsl_bot ON trading_scanner_log(bot_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_tsl_symbol ON trading_scanner_log(symbol);
```

---

## 4. Worker API Plan

### Framework: Hono (lightweight, Workers-native)

### Route Mapping (Flask → Worker)

| Flask Route | Worker Route | Method | Auth |
|---|---|---|---|
| `/register` | `POST /api/auth/register` | POST | Public |
| `/login` | `POST /api/auth/login` | POST | Public |
| `/logout` | `POST /api/auth/logout` | POST | User |
| `/admin_login` | `POST /api/auth/admin-login` | POST | Public |
| `/telegram_auth` | `POST /api/auth/telegram` | POST | Public |
| `/dashboard` | `GET /api/dashboard` | GET | User |
| `/market` | `GET /api/market` | GET | Public |
| `/all_ads` | `GET /api/market/all-ads` | GET | Public |
| `/create_ad` | `POST /api/ads/create` | POST | User |
| `/my_ads` | `GET /api/ads/my-ads` | GET | User |
| `/buy/<id>` | `POST /api/trades/buy/:id` | POST | User |
| `/trade/<id>` | `GET /api/trades/:id` | GET | User |
| `/trade/<id>` (POST) | `POST /api/trades/:id/message` | POST | User |
| `/confirm_payment/<id>` | `POST /api/trades/:id/confirm-payment` | POST | User |
| `/upload_payment/<id>` | `POST /api/trades/:id/upload-proof` | POST | User |
| `/seller_confirm/<id>` | `POST /api/trades/:id/seller-confirm` | POST | User |
| `/open_dispute/<id>` | `POST /api/trades/:id/dispute` | POST | User |
| `/cancel_trade/<id>` | `POST /api/trades/:id/cancel` | POST | User |
| `/my_trades` | `GET /api/trades/my-trades` | GET | User |
| `/wallet` | `GET /api/wallet` | GET | User |
| `/save_wallet` | `POST /api/wallet/save-address` | POST | User |
| `/usdt_deposit` | `POST /api/deposits/usdt` | POST | User |
| `/withdraw` | `POST /api/withdrawals/request` | POST | User |
| `/profile` | `GET /api/profile` | GET | User |
| `/edit_profile` | `POST /api/profile/edit` | POST | User |
| `/notifications` | `GET /api/notifications` | GET | User |
| `/review/<id>` | `POST /api/reviews/:trade_id` | POST | User |
| `/cash_market` | `GET /api/cash/market` | GET | Public |
| `/cash_ad/<id>` | `GET /api/cash/ad/:id` | GET | Public |
| `/create_cash_ad` | `POST /api/cash/create-ad` | POST | User |
| `/cash_buy/<id>` | `POST /api/cash/buy/:id` | POST | User |
| `/cash_trade/<id>` | `GET/POST /api/cash/trade/:id` | GET/POST | User |
| `/admin` | `GET /api/admin` | GET | Admin |
| `/admin_ban_user/<u>` | `POST /api/admin/ban/:username` | POST | Admin |
| `/admin_unban_user/<u>` | `POST /api/admin/unban/:username` | POST | Admin |
| `/admin_verify_user/<u>` | `POST /api/admin/verify/:username` | POST | Admin |
| `/admin_resolve_dispute/<id>` | `POST /api/admin/dispute/:id/resolve` | POST | Admin |
| `/admin_price` | `GET/POST /api/admin/price` | GET/POST | Admin |
| `/admin_commission` | `GET/POST /api/admin/commission` | GET/POST | Admin |
| `/admin_wallet` | `GET /api/admin/wallets` | GET | Admin |
| `/admin_cash_ads` | `GET /api/admin/cash-ads` | GET | Admin |
| `/admin_search` | `POST /api/admin/search` | POST | Admin |
| `/admin_usdt_deposits` | `GET /api/admin/deposits` | GET | Admin |
| `/admin_credit_user` | `POST /api/admin/credit` | POST | Admin |
| `/admin_confirm_deposit/<id>` | `POST /api/admin/deposits/:id/confirm` | POST | Admin |
| `/admin_reject_deposit/<id>` | `POST /api/admin/deposits/:id/reject` | POST | Admin |
| `/admin_approve_withdraw/<id>` | `POST /api/admin/withdrawals/:id/approve` | POST | Admin |
| `/admin_reject_withdraw/<id>` | `POST /api/admin/withdrawals/:id/reject` | POST | Admin |
| `/telegram/webhook` | `POST /telegram/webhook` | POST | Telegram |
| `/health` | `GET /health` | GET | Public |

### Worker Entry Point Pattern

```typescript
import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { jwt } from 'hono/jwt'

type Bindings = {
  DB: D1Database
  R2: R2Bucket
  TELEGRAM_BOT_TOKEN: string
  TELEGRAM_WEBAPP_URL: string
  SECRET_KEY: string
  PLATFORM_WALLET: string
  BSC_RPC_URL: string
}

const app = new Hono<{ Bindings: Bindings }>()

// Middleware
app.use('*', cors())
app.use('*', securityHeaders())

// Routes
app.route('/api/auth', authRoutes)
app.route('/api/market', marketRoutes)
app.route('/api/trades', tradeRoutes)
app.route('/api/wallet', walletRoutes)
app.route('/api/deposits', depositRoutes)
app.route('/api/withdrawals', withdrawalRoutes)
app.route('/api/notifications', notificationRoutes)
app.route('/api/admin', adminRoutes)
app.route('/api/cash', cashRoutes)
app.route('/api/profile', profileRoutes)
app.route('/telegram', telegramWebhook)

// Health
app.get('/health', (c) => c.json({ status: 'ok', timestamp: new Date().toISOString() }))

export default app
```

---

## 5. Telegram Webhook Architecture

### Current (Polling)
```
Flask Process → Thread → bot_loop() → getUpdates → process → sendMessage
```

### Target (Webhook)
```
Telegram API → POST /telegram/webhook → Worker → process → sendMessage
```

### Webhook Handler Plan

```typescript
// src/telegram/webhook.ts
import { Hono } from 'hono'

const telegram = new Hono()

// Telegram webhook endpoint
telegram.post('/webhook', async (c) => {
  const update = await c.req.json()
  
  // Handle messages
  if (update.message) {
    await handleMessage(c, update.message)
  }
  
  // Handle callback queries (inline keyboard buttons)
  if (update.callback_query) {
    await handleCallbackQuery(c, update.callback_query)
  }
  
  return c.json({ ok: true })
})

// /start command
async function handleMessage(c, message) {
  const chatId = message.chat.id
  const text = message.text
  
  if (text === '/start') {
    const keyboard = {
      inline_keyboard: [
        [{ text: '🚀 فتح منصة USDT P2P فلسطين', web_app: { url: WEBAPP_URL } }],
        [
          { text: '💰 محفظتي', web_app: { url: WEBAPP_URL + '/wallet' } },
          { text: '📊 السوق', web_app: { url: WEBAPP_URL + '/market' } }
        ],
        [
          { text: '💵 شراء USDT', web_app: { url: WEBAPP_URL + '/market' } },
          { text: '💸 بيع USDT', web_app: { url: WEBAPP_URL + '/create_ad' } }
        ],
        [
          { text: '📥 إيداع', web_app: { url: WEBAPP_URL + '/deposit' } },
          { text: '📤 سحب', web_app: { url: WEBAPP_URL + '/withdraw' } }
        ],
        [
          { text: '📊 تداولاتي', web_app: { url: WEBAPP_URL + '/my_trades' } },
          { text: '👤 حسابي', web_app: { url: WEBAPP_URL + '/profile' } }
        ]
      ]
    }
    await sendMessage(chatId, 'مرحباً بك في منصة USDT P2P فلسطين 🇵🇸', keyboard)
  }
}
```

### Webhook Setup
- On Worker deploy, call `setWebhook` API to register the webhook URL
- URL: `https://<worker-name>.<account>.workers.dev/telegram/webhook`
- Use Cloudflare Secrets for bot token

---

## 6. R2 Storage Plan

### Buckets
- **`usdt-palestine-uploads`** — Payment proofs, user-uploaded files

### Object Key Structure
```
uploads/
├── payment-proofs/
│   └── {trade_id}_{timestamp}.{ext}
├── profiles/
│   └── {username}_{timestamp}.{ext}
└── evidence/
    └── {dispute_id}_{timestamp}.{ext}
```

### Access Pattern
- **Upload**: Worker receives multipart form → validates → stores in R2
- **Serve**: Worker generates signed URL (temporary, 1-hour expiry)
- **Delete**: Worker deletes from R2 (admin/user action)

### File Validation
- Max size: 5MB
- Allowed types: image/jpeg, image/png, image/webp, application/pdf
- Scan for malicious content (basic header check)

---

## 7. Authentication Plan

### Strategy: Secure HTTP-only Cookies + JWT

```
User Login/Register
        ↓
Worker validates credentials
        ↓
Generate JWT token (user_id, username, is_admin)
        ↓
Set HTTP-only, Secure, SameSite=Lax cookie
        ↓
All subsequent requests include cookie
        ↓
Middleware validates JWT from cookie
```

### Token Structure
```json
{
  "sub": "user_id",
  "username": "ahmed",
  "is_admin": false,
  "iat": 1724448000,
  "exp": 1727040000
}
```

### Password Hashing
- Use `bcrypt` via `@aspect-build/hash` or similar Workers-compatible library
- Or use Web Crypto API with PBKDF2 (Workers-native, no external deps)

### Session Management
- JWT stored in HTTP-only cookie
- 30-day expiry (matching current Flask config)
- Refresh on each request if < 7 days remaining
- Invalidate on logout (client-side cookie deletion)

### Admin Authorization
- JWT includes `is_admin: true` claim
- Middleware checks `is_admin` for all `/api/admin/*` routes
- Server-side enforcement — hiding UI elements is NOT sufficient

---

## 8. Web3/BSC Migration Plan

### Current: Python web3.py
### Target: TypeScript ethers.js or raw JSON-RPC

### Verification Function (TypeScript)

```typescript
// src/blockchain/usdt.ts

const USDT_CONTRACT = '0x55d398326f99059fF775485246999027B3197955'
const PLATFORM_WALLET = '0x659dd7cba24363c903abe3fddfc89eb30ffbf58a'

// Minimal ABI for Transfer event
const TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

export async function checkUsdtTransaction(
  rpcUrl: string,
  txHash: string,
  expectedAmount: number
): Promise<{ verified: boolean; reason: string }> {
  
  // 1. Get transaction receipt
  const receipt = await fetch(rpcUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      method: 'eth_getTransactionReceipt',
      params: [txHash],
      id: 1
    })
  })
  const receiptData = await receipt.json()
  
  if (!receiptData.result) {
    return { verified: false, reason: 'Transaction not found' }
  }
  
  // 2. Check status
  if (receiptData.result.status !== '0x1') {
    return { verified: false, reason: 'Transaction failed' }
  }
  
  // 3. Find Transfer event log
  const transferLog = receiptData.result.logs.find(
    (log: any) => log.address.toLowerCase() === USDT_CONTRACT.toLowerCase()
      && log.topics[0] === TRANSFER_TOPIC
  )
  
  if (!transferLog) {
    return { verified: false, reason: 'No USDT Transfer event found' }
  }
  
  // 4. Verify recipient
  const toAddr = '0x' + transferLog.topics[2].slice(-40)
  if (toAddr.toLowerCase() !== PLATFORM_WALLET.toLowerCase()) {
    return { verified: false, reason: 'Recipient does not match platform wallet' }
  }
  
  // 5. Verify amount (USDT has 6 decimals)
  const amount = parseInt(transferLog.data, 16) / 1e6
  if (Math.abs(amount - expectedAmount) > 0.01) {
    return { verified: false, reason: `Amount mismatch: expected ${expectedAmount}, got ${amount}` }
  }
  
  return { verified: true, reason: 'Transaction verified' }
}
```

### Environment Variables (Cloudflare Secrets)
- `BSC_RPC_URL` → `https://bsc-dataseed.binance.org/`
- `PLATFORM_WALLET` → `0x659dd7cba24363c903abe3fddfc89eb30ffbf58a`
- `USDT_CONTRACT` → `0x55d398326f99059fF775485246999027B3197955`

---

## 9. Frontend Migration Plan

### Strategy: Server-rendered HTML + Client-side JavaScript

The frontend will be **static HTML files** served from Cloudflare Pages, with **JavaScript** that calls the Worker API.

### Pattern for Each Page

```html
<!-- frontend/market.html -->
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>السوق — USDT P2P Palestine</title>
  <link rel="stylesheet" href="/design-system.css">
</head>
<body>
  <div id="app"></div>
  <script src="/app.js"></script>
  <script>
    // Load market data from API
    App.loadMarket()
  </script>
</body>
</html>
```

### app.js Pattern

```javascript
const API_BASE = ''  // Same origin (Pages → Worker)

const App = {
  // Fetch with auth cookie
  async api(path, options = {}) {
    const res = await fetch(`${API_BASE}${api}`, {
      ...options,
      credentials: 'include',  // Include cookies
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    })
    return res.json()
  },
  
  // Load market page
  async loadMarket() {
    const data = await this.api('/api/market')
    document.getElementById('app').innerHTML = this.renderMarket(data)
  },
  
  // Render market HTML
  renderMarket(data) {
    return `
      <nav class="navbar">...</nav>
      <main>
        ${data.ads.map(ad => this.renderAdCard(ad)).join('')}
      </main>
      <nav class="bottom-nav">...</nav>
    `
  }
}
```

### Design System Preservation
- Keep existing `design-system.css` and `style.css`
- These work as-is on Cloudflare Pages
- No changes needed for CSS

### Key UI Pages to Preserve
All 39 existing templates will have corresponding HTML files in `frontend/`:
1. `index.html` — Landing/home
2. `login.html` — Login
3. `register.html` — Register
4. `dashboard.html` — Dashboard
5. `market.html` — P2P marketplace
6. `wallet.html` — Wallet
7. `trade.html` — Trade detail/chat
8. `profile.html` — Profile
9. `notifications.html` — Notifications
10. `create_ad.html` — Create USDT ad
11. `create_cash_ad.html` — Create cash ad
12. `cash_market.html` — Cash marketplace
13. `cash_ad.html` — Cash ad detail
14. `cash_trade.html` — Cash trade
15. `chat.html` — Trade chat
16. `usdt_deposit.html` — Deposit USDT
17. `withdraw.html` — Withdraw USDT
18. `my_ads.html` — My ads
19. `my_trades.html` — My trades
20. `edit_profile.html` — Edit profile
21. `all_ads.html` — All ads
22. `admin.html` — Admin dashboard
23. `admin_login.html` — Admin login
24. `admin_wallet.html` — Admin wallets
25. `admin_usdt_deposits.html` — Admin deposits
26. `admin_cash_ads.html` — Admin cash ads
27. `admin_search.html` — Admin search
28. `admin_commission.html` — Admin commission
29. `admin_price.html` — Admin price
30. `telegram_webapp.html` — Telegram WebApp entry
31. `telegram_login.html` — Telegram login
32. `404.html` — Not found
33. `500.html` — Server error
34. `payment_success.html` — Payment success

---

## 10. Security Plan

### Immediately Fixed
1. ✅ **Remove hardcoded bot token** from `telegram_bot.py` source code
2. ✅ **Remove hardcoded admin ID** from source code
3. ✅ **Remove hardcoded secret key** fallback

### New Security Measures
| Measure | Implementation |
|---|---|
| **CSRF** | Double-submit cookie pattern (Worker generates token, client sends in header) |
| **Rate Limiting** | KV-based sliding window per IP/endpoint |
| **Security Headers** | X-Content-Type-Options, X-Frame-Options, CSP, HSTS |
| **Input Validation** | Zod schemas for all API inputs |
| **Authorization** | JWT middleware checks user/admin for every route |
| **SQL Injection** | D1 parameterized queries (no string concatenation) |
| **XSS** | HTML escaping in all template rendering, CSP headers |
| **File Upload** | Type validation, size limits, R2 storage |
| **Telegram HMAC** | Verified server-side using Web Crypto API |
| **Audit Logs** | All financial actions logged to `wallet_history` table |
| **Error Handling** | Never expose internals; return generic error messages |

---

## 11. Cron Trigger Plan

### Price Updater
```toml
# wrangler.toml
[[cron]]
pattern = "0 * * * *"  # Every hour
handler = "./src/cron/price-updater.ts"
```

### Price Updater Logic
```typescript
// src/cron/price-updater.ts
export default {
  async scheduled(event, env) {
    const res = await fetch('https://open.er-api.com/v6/latest/USD')
    const data = await res.json()
    const usdIls = data.rates.ILS
    
    await env.DB.prepare(
      'UPDATE market_price SET usd_ils=?, usdt_ils=?, updated=datetime("now") WHERE id=1'
    ).bind(usdIls, usdIls).run()
  }
}
```

---

## 12. Deployment Plan

### Step-by-Step

1. **Create Cloudflare Account** (if not exists)
2. **Create D1 Database**: `wrangler d1 create usdt-palestine-db`
3. **Run Migrations**: `wrangler d1 migrations apply usdt-palestine-db`
4. **Create R2 Bucket**: `wrangler r2 bucket create usdt-palestine-uploads`
5. **Set Secrets**:
   ```bash
   wrangler secret put SECRET_KEY
   wrangler secret put TELEGRAM_BOT_TOKEN
   wrangler secret put ADMIN_PASSWORD
   ```
6. **Deploy Worker**: `wrangler deploy`
7. **Deploy Pages**: Connect GitHub repo, auto-deploy from `frontend/`
8. **Set Telegram Webhook**:
   ```bash
   curl "https://api.telegram.org/bot<token>/setWebhook?url=https://<worker>.workers.dev/telegram/webhook"
   ```
9. **Configure Cron**: Already in wrangler.toml
10. **Test All Routes**
11. **Verify Telegram Integration**
12. **Verify BSC Transaction Verification**

---

## 13. Complete File Change List

### Files to CREATE (new)

| File | Purpose |
|---|---|
| `wrangler.toml` | Cloudflare Worker configuration |
| `package.json` | Node.js dependencies |
| `tsconfig.json` | TypeScript configuration |
| `src/index.ts` | Worker entry point (Hono router) |
| `src/auth.ts` | Authentication middleware |
| `src/db.ts` | D1 database helpers |
| `src/routes/auth.ts` | Auth routes |
| `src/routes/market.ts` | Market routes |
| `src/routes/ads.ts` | Ad creation routes |
| `src/routes/trades.ts` | Trade routes |
| `src/routes/wallet.ts` | Wallet routes |
| `src/routes/deposits.ts` | Deposit routes |
| `src/routes/withdrawals.ts` | Withdrawal routes |
| `src/routes/notifications.ts` | Notification routes |
| `src/routes/admin.ts` | Admin routes |
| `src/routes/cash.ts` | Cash trading routes |
| `src/routes/profile.ts` | Profile routes |
| `src/telegram/webhook.ts` | Telegram webhook handler |
| `src/telegram/auth.ts` | Telegram HMAC verification |
| `src/telegram/bot.ts` | Bot commands |
| `src/blockchain/bsc.ts` | BSC RPC connection |
| `src/blockchain/usdt.ts` | USDT verification |
| `src/cron/price-updater.ts` | Price updater cron |
| `src/middleware/csrf.ts` | CSRF protection |
| `src/middleware/rate-limit.ts` | Rate limiting |
| `src/middleware/security-headers.ts` | Security headers |
| `src/middleware/error-handler.ts` | Error handling |
| `src/utils/password.ts` | Password hashing |
| `src/utils/session.ts` | Session management |
| `src/utils/validation.ts` | Input validation |
| `src/utils/audit.ts` | Audit logging |
| `migrations/0001_init.sql` | D1 schema |
| `migrations/0002_indexes.sql` | D1 indexes |
| `frontend/public/design-system.css` | CSS (copy from static/) |
| `frontend/public/style.css` | CSS (copy from static/) |
| `frontend/public/app.js` | Frontend JavaScript |
| `frontend/index.html` | Landing page |
| `frontend/login.html` | Login |
| `frontend/register.html` | Register |
| `frontend/dashboard.html` | Dashboard |
| `frontend/market.html` | Marketplace |
| `frontend/wallet.html` | Wallet |
| `frontend/trade.html` | Trade view |
| `frontend/profile.html` | Profile |
| `frontend/notifications.html` | Notifications |
| `frontend/create_ad.html` | Create ad |
| `frontend/create_cash_ad.html` | Create cash ad |
| `frontend/cash_market.html` | Cash market |
| `frontend/cash_ad.html` | Cash ad detail |
| `frontend/cash_trade.html` | Cash trade |
| `frontend/chat.html` | Trade chat |
| `frontend/usdt_deposit.html` | Deposit |
| `frontend/withdraw.html` | Withdraw |
| `frontend/my_ads.html` | My ads |
| `frontend/my_trades.html` | My trades |
| `frontend/edit_profile.html` | Edit profile |
| `frontend/all_ads.html` | All ads |
| `frontend/admin.html` | Admin dashboard |
| `frontend/admin_login.html` | Admin login |
| `frontend/admin_wallet.html` | Admin wallets |
| `frontend/admin_usdt_deposits.html` | Admin deposits |
| `frontend/admin_cash_ads.html` | Admin cash ads |
| `frontend/admin_search.html` | Admin search |
| `frontend/admin_commission.html` | Admin commission |
| `frontend/admin_price.html` | Admin price |
| `frontend/telegram_webapp.html` | Telegram WebApp |
| `frontend/telegram_login.html` | Telegram login |
| `frontend/404.html` | Not found |
| `frontend/500.html` | Server error |
| `frontend/payment_success.html` | Payment success |
| `DEPLOYMENT.md` | Deployment documentation |

### Files to KEEP (no changes)
| File | Reason |
|---|---|
| `app.py` | Backup reference — keep for reference |
| `telegram_bot.py` | Backup reference — keep for reference |
| `price_updater.py` | Backup reference — keep for reference |
| `models.py` | Backup reference — keep for reference |
| `templates/` | Backup reference — keep for reference |
| `static/` | Backup reference — keep for reference |
| `trading/` | AI Trading Engine — separate service |
| `CLOUDFLARE_MIGRATION.md` | Audit document |
| `CLOUDFLARE_PHASE2_ARCHITECTURE.md` | This document |

### Files to MODIFY
| File | Change |
|---|---|
| `.gitignore` | Add: `node_modules/`, `wrangler.toml` secrets, `.env` |
| `CLOUDFLARE_MIGRATION.md` | Update with Phase 2 findings |

### Files to DELETE
**None** — All existing files are preserved as backup reference.

---

## 14. Implementation Order

1. **Project setup** — `wrangler.toml`, `package.json`, `tsconfig.json`
2. **D1 schema** — `migrations/0001_init.sql`, `migrations/0002_indexes.sql`
3. **Worker foundation** — `src/index.ts`, `src/db.ts`, `src/auth.ts`
4. **Auth routes** — Register, login, logout, admin, Telegram
5. **Market routes** — Browse ads, create ad, view ad
6. **Trade routes** — Buy, trade view, payment, chat, disputes
7. **Wallet routes** — Balance, deposit, withdraw, history
8. **Admin routes** — Dashboard, manage users, deposits, withdrawals
9. **Cash trading routes** — Cash ads, cash trades
10. **Telegram webhook** — Bot commands, notifications
11. **Cron triggers** — Price updater
12. **R2 file uploads** — Payment proofs
13. **BSC verification** — USDT transaction checking
14. **Frontend HTML** — All pages
15. **Frontend JS** — API integration
16. **Security hardening** — CSRF, rate limiting, headers
17. **Testing** — All routes and flows
18. **Deployment** — Cloudflare Pages + Workers

---

*This architecture document is ready for review. No code has been changed.*
*Upon approval, implementation will proceed in the order listed above.*
