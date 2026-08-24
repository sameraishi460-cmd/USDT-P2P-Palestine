-- ============================================================
-- USDT P2P Palestine — D1 Migration 0004: Add missing columns
--
-- Adds email to users (needed by auth/register), and
-- ensures V2 tables exist for workers that were deployed
-- before the V2 schema was added to the auto-migration.
-- ============================================================

-- Add email column to users if missing
ALTER TABLE users ADD COLUMN email TEXT DEFAULT '';

-- ============================================================
-- V2 tables (idempotent — IF NOT EXISTS)
-- ============================================================

CREATE TABLE IF NOT EXISTS ratings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_id INTEGER NOT NULL,
  from_user TEXT NOT NULL,
  to_user TEXT NOT NULL,
  rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
  comment TEXT DEFAULT '',
  created TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (trade_id) REFERENCES trades(id),
  FOREIGN KEY (from_user) REFERENCES users(username),
  FOREIGN KEY (to_user) REFERENCES users(username)
);

CREATE INDEX IF NOT EXISTS idx_ratings_to_user ON ratings(to_user);
CREATE INDEX IF NOT EXISTS idx_ratings_trade ON ratings(trade_id);

CREATE TABLE IF NOT EXISTS verification_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL,
  status TEXT DEFAULT 'PENDING',
  document_url TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  reviewed_by TEXT DEFAULT '',
  created TEXT DEFAULT (datetime('now')),
  reviewed_at TEXT,
  FOREIGN KEY (username) REFERENCES users(username)
);

CREATE INDEX IF NOT EXISTS idx_verify_user ON verification_requests(username);

CREATE TABLE IF NOT EXISTS fraud_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL,
  event_type TEXT NOT NULL,
  details TEXT DEFAULT '',
  risk_score INTEGER DEFAULT 0,
  ip TEXT DEFAULT '',
  created TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (username) REFERENCES users(username)
);

CREATE INDEX IF NOT EXISTS idx_fraud_user ON fraud_log(username);

CREATE TABLE IF NOT EXISTS referrals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE NOT NULL,
  referrer TEXT NOT NULL,
  referred TEXT NOT NULL,
  status TEXT DEFAULT 'PENDING',
  reward REAL DEFAULT 0,
  created TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (referrer) REFERENCES users(username),
  FOREIGN KEY (referred) REFERENCES users(username)
);

CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(code);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer);

CREATE TABLE IF NOT EXISTS promo_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE NOT NULL,
  discount_type TEXT DEFAULT 'PERCENT',
  discount_value REAL DEFAULT 0,
  max_discount REAL DEFAULT 0,
  min_trade REAL DEFAULT 0,
  max_uses INTEGER DEFAULT 100,
  used_count INTEGER DEFAULT 0,
  expires_at TEXT,
  active INTEGER DEFAULT 1,
  created TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_promo_code ON promo_codes(code);

CREATE TABLE IF NOT EXISTS featured_ads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ad_id INTEGER NOT NULL,
  start_date TEXT DEFAULT (datetime('now')),
  end_date TEXT,
  created_by TEXT DEFAULT '',
  FOREIGN KEY (ad_id) REFERENCES ads(id)
);

CREATE INDEX IF NOT EXISTS idx_featured_ad ON featured_ads(ad_id);

CREATE TABLE IF NOT EXISTS admin_activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT DEFAULT '',
  details TEXT DEFAULT '',
  ip TEXT DEFAULT '',
  created TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_admin_activity_created ON admin_activity(created);
