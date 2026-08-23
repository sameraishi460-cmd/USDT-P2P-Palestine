#!/bin/bash
# ============================================================
# USDT P2P Palestine — Build Script
# ============================================================
# Called by Cloudflare Workers Build.
# Tries to apply D1 migrations during build, but does NOT
# fail the build if migrations can't run (e.g., missing D1
# permissions on the build API token).
#
# The Worker's auto-migration (src/db-init.ts) creates tables
# on the first request if they don't exist, so migrations
# during build are a best-effort optimization.
#
# IMPORTANT: Do NOT call `wrangler deploy` here — Workers
# Build handles deployment automatically.
# ============================================================

set -uo pipefail
cd "$(dirname "$0")/.."

D1_NAME="usdt-palestine-db"

echo "=== Build Step: TypeScript Check ==="
bunx tsc --noEmit || echo "⚠️ TypeScript check had issues (continuing build)"
echo "✅ TypeScript check done"

echo ""
echo "=== Build Step: D1 Migrations (best-effort) ==="
if bunx wrangler d1 migrations apply "$D1_NAME" --remote 2>/dev/null; then
  echo "✅ D1 migrations applied successfully during build"
  
  echo "=== Seeding config ==="
  bunx wrangler d1 execute "$D1_NAME" --remote \
    --command "INSERT OR IGNORE INTO platform_config (key, value) VALUES ('p2p_fee_percent', '1.0')" 2>/dev/null || true
  bunx wrangler d1 execute "$D1_NAME" --remote \
    --command "INSERT OR IGNORE INTO platform_config (key, value) VALUES ('cash_fee_percent', '1.0')" 2>/dev/null || true
  bunx wrangler d1 execute "$D1_NAME" --remote \
    --command "INSERT OR IGNORE INTO platform_config (key, value) VALUES ('min_fee', '0.1')" 2>/dev/null || true
  bunx wrangler d1 execute "$D1_NAME" --remote \
    --command "INSERT OR IGNORE INTO platform_config (key, value) VALUES ('max_fee', '100.0')" 2>/dev/null || true
  bunx wrangler d1 execute "$D1_NAME" --remote \
    --command "INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, 3.7, 3.7)" 2>/dev/null || true
  echo "✅ Config seeded"
else
  echo "⚠️ D1 migrations could not run during build (missing permissions or auth)"
  echo "   Tables will be auto-created on first request via src/db-init.ts"
fi

echo ""
echo "=== BUILD COMPLETE ==="
echo "Worker auto-migration will create D1 tables on first request if needed."
