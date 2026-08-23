-- ============================================================
-- USDT P2P Palestine — D1 Migration 0003: Uploads metadata
-- R2 object metadata (objects themselves live in R2, never in D1).
-- ============================================================

CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('payment-proof', 'evidence')),
    mime TEXT NOT NULL,
    size INTEGER NOT NULL,
    created DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_uploads_owner ON uploads(owner, created);
CREATE INDEX IF NOT EXISTS idx_uploads_kind ON uploads(kind);
