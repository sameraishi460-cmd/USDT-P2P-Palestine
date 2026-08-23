#!/usr/bin/env python3
"""
USDT P2P Palestine — Staging Seed Data Generator

Creates fake test accounts and transactions for staging environment.
All data is fake — no real user information or financial data.

Usage:
  python3 scripts/seed_staging_data.py                     # print SQL
  python3 scripts/seed_staging_data.py --apply             # apply to local D1
  python3 scripts/seed_staging_data.py --apply --remote    # apply to remote D1
"""

import hashlib
import os
import sys
import time
import json

# ============================================================
# Password hashing (PBKDF2 — matches Worker crypto.ts)
# ============================================================
def hash_password(password: str, salt: str = None) -> str:
    """PBKDF2-SHA256 hash matching the Worker's format."""
    if salt is None:
        salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"pbkdf2:{salt}:{dk.hex()}"


# ============================================================
# Seed data
# ============================================================
USERS = [
    {"username": "admin",       "password": "Admin123!@#", "status": "ADMIN",  "verified": 1},
    {"username": "seller_ahmed","password": "Test1234",     "status": "ACTIVE", "verified": 1},
    {"username": "buyer_khalid","password": "Test1234",     "status": "ACTIVE", "verified": 1},
    {"username": "trader_fatima","password": "Test1234",    "status": "ACTIVE", "verified": 1},
    {"username": "new_user",    "password": "Test1234",     "status": "ACTIVE", "verified": 0},
    {"username": "dispute_user","password": "Test1234",     "status": "ACTIVE", "verified": 1},
]

WALLETS = {
    "seller_ahmed":  {"balance": 1000.00, "locked": 0},
    "buyer_khalid":  {"balance": 500.00,  "locked": 0},
    "trader_fatima": {"balance": 2000.00, "locked": 0},
    "admin":         {"balance": 100.00,  "locked": 0},
    "new_user":      {"balance": 50.00,   "locked": 0},
    "dispute_user":  {"balance": 300.00,  "locked": 0},
}

ADS = [
    {"user": "seller_ahmed", "title": "USDT للبيع - بنك فلسطين", "amount": 500, "price": 3.72,
     "payment": "bank_transfer", "min_amount": 20, "max_amount": 500, "type": "SELL", "status": "OPEN"},
    {"user": "seller_ahmed", "title": "USDT للبيع - كاش", "amount": 200, "price": 3.70,
     "payment": "cash", "min_amount": 10, "max_amount": 200, "type": "SELL", "status": "OPEN"},
    {"user": "trader_fatima", "title": "USDT للبيع", "amount": 800, "price": 3.73,
     "payment": "bank_transfer", "min_amount": 50, "max_amount": 800, "type": "SELL", "status": "OPEN"},
    {"user": "buyer_khalid", "title": "شراء USDT", "amount": 300, "price": 3.68,
     "payment": "bank_transfer", "min_amount": 10, "max_amount": 300, "type": "BUY", "status": "OPEN"},
]


def generate_sql() -> list[str]:
    """Generate all seed SQL statements."""
    stmts = []

    stmts.append("-- ============================================================")
    stmts.append("-- STAGING SEED DATA — USDT P2P Palestine")
    stmts.append(f"-- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    stmts.append("-- ALL DATA IS FAKE — NO REAL USERS OR FINANCIAL DATA")
    stmts.append("-- ============================================================")
    stmts.append("")

    # Market price
    stmts.append("-- Market Price")
    stmts.append("INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, 3.70, 3.70);")
    stmts.append("")

    # Platform config
    stmts.append("-- Platform Config")
    stmts.append("INSERT OR REPLACE INTO platform_config (key, value) VALUES ('p2p_fee_percent', '1.0');")
    stmts.append("INSERT OR REPLACE INTO platform_config (key, value) VALUES ('min_fee', '0.1');")
    stmts.append("INSERT OR REPLACE INTO platform_config (key, value) VALUES ('max_fee', '100.0');")
    stmts.append("")

    # Users
    stmts.append("-- Test Users")
    for u in USERS:
        h = hash_password(u["password"])
        # Escape single quotes in hash
        h_escaped = h.replace("'", "''")
        stmts.append(
            f"INSERT OR IGNORE INTO users (username, password, status, verified) "
            f"VALUES ('{u['username']}', '{h_escaped}', '{u['status']}', {u['verified']});"
        )
    stmts.append("")

    # Wallets
    stmts.append("-- Test Wallets")
    for username, w in WALLETS.items():
        stmts.append(
            f"INSERT OR IGNORE INTO wallets (username, balance, locked) "
            f"VALUES ('{username}', {w['balance']}, {w['locked']});"
        )
    stmts.append("")

    # Wallet history (seed transactions)
    stmts.append("-- Seed Wallet History")
    for username, w in WALLETS.items():
        if w["balance"] > 0:
            stmts.append(
                f"INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, note) "
                f"VALUES ('{username}', 'ADMIN_CREDIT', {w['balance']}, 0, {w['balance']}, 'Staging seed data');"
            )
    stmts.append("")

    # Ads
    stmts.append("-- Test Ads")
    for ad in ADS:
        stmts.append(
            f"INSERT INTO ads (user, title, amount, price, payment_method, min_amount, max_amount, type, status) "
            f"VALUES ('{ad['user']}', '{ad['title']}', {ad['amount']}, {ad['price']}, "
            f"'{ad['payment']}', {ad['min_amount']}, {ad['max_amount']}, '{ad['type']}', '{ad['status']});"
        )
    stmts.append("")

    # Notifications
    stmts.append("-- Welcome Notifications")
    for u in USERS:
        stmts.append(
            f"INSERT INTO notifications (username, title, message) "
            f"VALUES ('{u['username']}', 'مرحباً بك! 🇵🇸', 'أهلاً بك في منصة USDT P2P فلسطين — بيئة الاختبار');"
        )
    stmts.append("")

    stmts.append("-- ============================================================")
    stmts.append("-- SEED DATA COMPLETE")
    stmts.append("-- Test accounts:")
    stmts.append("--   admin / Admin123!@# (ADMIN)")
    stmts.append("--   seller_ahmed / Test1234 (1000 USDT)")
    stmts.append("--   buyer_khalid / Test1234 (500 USDT)")
    stmts.append("--   trader_fatima / Test1234 (2000 USDT)")
    stmts.append("--   new_user / Test1234 (50 USDT, unverified)")
    stmts.append("--   dispute_user / Test1234 (300 USDT)")
    stmts.append("-- ============================================================")

    return stmts


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Staging seed data generator")
    parser.add_argument("--apply", action="store_true", help="Apply to D1")
    parser.add_argument("--remote", action="store_true", help="Apply to remote D1 (default: local)")
    args = parser.parse_args()

    stmts = generate_sql()

    if args.apply:
        sql = "\n".join(stmts)
        # Write to temp file and use wrangler
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write(sql)
            tmp = f.name
        target = "--remote" if args.remote else "--local"
        cmd = f"wrangler d1 execute usdt-palestine-db {target} --file={tmp}"
        print(f"Applying: {cmd}")
        os.system(cmd)
        os.unlink(tmp)
    else:
        for s in stmts:
            print(s)


if __name__ == "__main__":
    main()
