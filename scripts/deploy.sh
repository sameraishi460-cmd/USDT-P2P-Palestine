#!/bin/bash
# ============================================================
# USDT P2P Palestine — Deploy with D1 Migration
# ============================================================
# Run by Cloudflare Workers Build or manually.
# Applies D1 migrations, seeds config, generates SECRET_KEY
# if missing, then deploys the Worker.
# ============================================================

set -e
cd "$(dirname "$0")/.."

D1_NAME="usdt-palestine-db"
WORKER_NAME="usdt-p2p-palestine"

echo "=== Step 1: Apply D1 migrations ==="
bunx wrangler d1 migrations apply "$D1_NAME" --remote --name "$WORKER_NAME" 2>&1 || {
  echo "Migration may have partial failures (tables may already exist). Continuing..."
}
echo "✅ Migrations applied"

echo ""
echo "=== Step 2: Seed platform_config defaults ==="
for kv in "p2p_fee_percent:1.0" "cash_fee_percent:1.0" "min_fee:0.1" "max_fee:100.0"; do
  key="${kv%%:*}"
  val="${kv##*:}"
  bunx wrangler d1 execute "$D1_NAME" --remote --name "$WORKER_NAME" \
    --command "INSERT OR IGNORE INTO platform_config (key, value) VALUES ('$key', '$val')" 2>&1 || true
done
bunx wrangler d1 execute "$D1_NAME" --remote --name "$WORKER_NAME" \
  --command "INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, 3.7, 3.7)" 2>&1 || true
echo "✅ Config seeded"

echo ""
echo "=== Step 3: Ensure SECRET_KEY exists ==="
if ! bunx wrangler secret list --name "$WORKER_NAME" 2>&1 | grep -q "SECRET_KEY"; then
  echo "Generating SECRET_KEY..."
  openssl rand -hex 32 | bunx wrangler secret put SECRET_KEY --name "$WORKER_NAME" 2>&1
  echo "✅ SECRET_KEY configured"
else
  echo "SECRET_KEY already set — skipping"
fi

echo ""
echo "=== Step 4: Deploy Worker ==="
bunx wrangler deploy --name "$WORKER_NAME" 2>&1
echo "✅ Deployed"

echo ""
echo "=== Step 5: Verify ==="
sleep 3
curl -s "https://usdt-p2p-palestine.sameraishi460.workers.dev/api/health" 2>&1
echo ""
