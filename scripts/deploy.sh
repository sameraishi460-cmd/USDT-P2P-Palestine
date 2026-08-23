#!/bin/bash
# ============================================================
# USDT P2P Palestine — Deploy with D1 Migration
# ============================================================
# This script MUST apply D1 migrations before deploying.
# If migrations fail, the entire build FAILS — no deploy.
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/.."

D1_NAME="usdt-palestine-db"

echo "=== Step 1: Apply D1 migrations ==="
echo "Running: wrangler d1 migrations apply $D1_NAME --remote"
bunx wrangler d1 migrations apply "$D1_NAME" --remote
MIGRATE_EXIT=$?
if [ $MIGRATE_EXIT -ne 0 ]; then
  echo "❌ FATAL: D1 migration failed with exit code $MIGRATE_EXIT"
  echo "The Worker will NOT be deployed until migrations succeed."
  exit 1
fi
echo "✅ D1 migrations applied successfully"

echo ""
echo "=== Step 2: Verify tables exist ==="
TABLE_COUNT=$(bunx wrangler d1 execute "$D1_NAME" --remote --command "SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'" 2>&1)
echo "Table count result: $TABLE_COUNT"
if echo "$TABLE_COUNT" | grep -q '"cnt":0'; then
  echo "❌ FATAL: No tables found after migration"
  exit 1
fi
echo "✅ Tables verified"

echo ""
echo "=== Step 3: Seed platform_config ==="
for kv in "p2p_fee_percent:1.0" "cash_fee_percent:1.0" "min_fee:0.1" "max_fee:100.0"; do
  key="${kv%%:*}"
  val="${kv##*:}"
  echo "Seeding $key = $val"
  bunx wrangler d1 execute "$D1_NAME" --remote \
    --command "INSERT OR IGNORE INTO platform_config (key, value) VALUES ('$key', '$val')"
done
echo "✅ platform_config seeded"

echo ""
echo "=== Step 4: Seed market_price ==="
bunx wrangler d1 execute "$D1_NAME" --remote \
  --command "INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, 3.7, 3.7)"
echo "✅ market_price seeded"

echo ""
echo "=== Step 5: Verify config exists ==="
CONFIG_CHECK=$(bunx wrangler d1 execute "$D1_NAME" --remote --command "SELECT value FROM platform_config WHERE key='p2p_fee_percent'" 2>&1)
echo "Config check: $CONFIG_CHECK"
if ! echo "$CONFIG_CHECK" | grep -q '"value"'; then
  echo "❌ FATAL: platform_config not seeded"
  exit 1
fi
echo "✅ Config verified"

echo ""
echo "=== Step 6: Deploy Worker ==="
bunx wrangler deploy
DEPLOY_EXIT=$?
if [ $DEPLOY_EXIT -ne 0 ]; then
  echo "❌ FATAL: Worker deploy failed with exit code $DEPLOY_EXIT"
  exit 1
fi
echo "✅ Worker deployed"

echo ""
echo "=== BUILD COMPLETE ==="
echo "D1 migrations: ✅ Applied"
echo "Config seeded: ✅ Yes"
echo "Worker deployed: ✅ Yes"
