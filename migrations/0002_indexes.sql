-- ============================================================
-- USDT P2P Palestine — D1 Migration 0002: Indexes
-- ============================================================

-- Users
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

-- Wallets & history
CREATE INDEX IF NOT EXISTS idx_wallets_username ON wallets(username);
CREATE INDEX IF NOT EXISTS idx_wallet_history_username ON wallet_history(username, created);
CREATE INDEX IF NOT EXISTS idx_wallet_history_ref ON wallet_history(reference_id);

-- Ads
CREATE INDEX IF NOT EXISTS idx_ads_user ON ads(user, status);
CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status, created);

-- Trades
CREATE INDEX IF NOT EXISTS idx_trades_buyer ON trades(buyer, status);
CREATE INDEX IF NOT EXISTS idx_trades_seller ON trades(seller, status);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status, created);
CREATE INDEX IF NOT EXISTS idx_trades_ad_id ON trades(ad_id);
CREATE INDEX IF NOT EXISTS idx_trades_escrow ON trades(escrow_status);

-- Messages
CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(sender, receiver, created);

-- Notifications
CREATE INDEX IF NOT EXISTS idx_notifications_username ON notifications(username, seen);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(username, created);

-- Reviews
CREATE INDEX IF NOT EXISTS idx_reviews_trade ON reviews(trade_id);
CREATE INDEX IF NOT EXISTS idx_reviews_to_user ON reviews(to_user);

-- Cash
CREATE INDEX IF NOT EXISTS idx_cash_ads_user ON cash_ads(user, status);
CREATE INDEX IF NOT EXISTS idx_cash_ads_status ON cash_ads(status, created);
CREATE INDEX IF NOT EXISTS idx_cash_trades_ad ON cash_trades(ad_id);

-- Disputes
CREATE INDEX IF NOT EXISTS idx_disputes_trade ON disputes(trade_id);
CREATE INDEX IF NOT EXISTS idx_disputes_status ON disputes(status);

-- Deposits / withdrawals
CREATE INDEX IF NOT EXISTS idx_deposits_username ON usdt_deposits(username, status);
CREATE INDEX IF NOT EXISTS idx_deposits_status ON usdt_deposits(status, created);
CREATE INDEX IF NOT EXISTS idx_withdrawals_username ON withdraw_requests(username, status);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdraw_requests(status, created);

-- Audit
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor, created);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, created);

-- Trading engine
CREATE INDEX IF NOT EXISTS idx_tb_username ON trading_bots(username);
CREATE INDEX IF NOT EXISTS idx_tp_bot ON trading_positions(bot_id, status);
CREATE INDEX IF NOT EXISTS idx_tp_symbol ON trading_positions(symbol, status);
CREATE INDEX IF NOT EXISTS idx_tt_bot ON trading_trades(bot_id, exit_time);
CREATE INDEX IF NOT EXISTS idx_to_bot ON trading_orders(bot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ts_bot ON trading_signals(bot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_te_bot ON trading_equity(bot_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_tds_bot_date ON trading_daily_stats(bot_id, date);
CREATE INDEX IF NOT EXISTS idx_tsl_bot ON trading_scanner_log(bot_id, timestamp);
