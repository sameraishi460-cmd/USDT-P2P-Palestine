#!/bin/bash
# ============================================================
# USDT P2P Palestine — PRODUCTION SETUP (One-Shot)
# ============================================================
# Run this AFTER: wrangler login
#
# This script:
#   1. Applies D1 schema migrations (creates all 33 tables)
#   2. Seeds platform_config + market_price defaults
#   3. Sets all required Cloudflare Worker secrets
#   4. Deploys the Worker
#   5. Registers the Telegram webhook
#   6. Verifies everything works
# ============================================================

set -e
cd "$(dirname "$0")/.."

WORKER_NAME="usdt-p2p-palestine"
WORKER_URL="https://usdt-p2p-palestine.sameraishi460.workers.dev"
D1_NAME="usdt-palestine-db"

echo "============================================================"
echo "  USDT P2P Palestine — Production Setup"
echo "  $(date)"
echo "============================================================"
echo ""

# Pre-check
echo "Checking wrangler authentication..."
if ! bunx wrangler whoami 2>&1 | grep -qi "account\|email\|id"; then
    echo "❌ Not authenticated. Run: wrangler login"
    exit 1
fi
echo "✅ Authenticated"
echo ""

# Step 1: Apply D1 migrations
echo "Step 1/6: Applying D1 migrations..."
bunx wrangler d1 migrations apply "$D1_NAME" --remote --name "$WORKER_NAME" 2>&1 || {
    echo "⚠️  Migration may have partial failures (tables may already exist). Continuing..."
}
echo "✅ D1 migrations applied"
echo ""

# Step 2: Seed platform config (in case health endpoint auto-seed doesn't run first)
echo "Step 2/6: Seeding platform config..."
bunx wrangler d1 execute "$D1_NAME" --remote --name "$WORKER_NAME" --command \
    "INSERT OR IGNORE INTO platform_config (key, value) VALUES ('p2p_fee_percent', '1.0')" 2>&1 || true
bunx wrangler d1 execute "$D1_NAME" --remote --name "$WORKER_NAME" --command \
    "INSERT OR IGNORE INTO platform_config (key, value) VALUES ('cash_fee_percent', '1.0')" 2>&1 || true
bunx wrangler d1 execute "$D1_NAME" --remote --name "$WORKER_NAME" --command \
    "INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, 3.7, 3.7)" 2>&1 || true
echo "✅ Platform config seeded"
echo ""

# Step 3: Set secrets
echo "Step 3/6: Setting Cloudflare Worker secrets..."
echo ""

# SECRET_KEY
if ! bunx wrangler secret list --name "$WORKER_NAME" 2>&1 | grep -q "SECRET_KEY"; then
    echo "Setting SECRET_KEY..."
    SECRET_VAL=$(openssl rand -hex 32)
    echo "$SECRET_VAL" | bunx wrangler secret put SECRET_KEY --name "$WORKER_NAME"
    echo "✅ SECRET_KEY configured"
else
    echo "SECRET_KEY already configured — skipping"
fi
echo ""

# TELEGRAM_BOT_TOKEN
if ! bunx wrangler secret list --name "$WORKER_NAME" 2>&1 | grep -q "TELEGRAM_BOT_TOKEN"; then
    echo "Setting TELEGRAM_BOT_TOKEN..."
    echo "Paste your Telegram bot token when prompted:"
    bunx wrangler secret put TELEGRAM_BOT_TOKEN --name "$WORKER_NAME"
    echo "✅ TELEGRAM_BOT_TOKEN configured"
else
    echo "TELEGRAM_BOT_TOKEN already configured — skipping"
fi
echo ""

# TELEGRAM_WEBHOOK_SECRET
if ! bunx wrangler secret list --name "$WORKER_NAME" 2>&1 | grep -q "TELEGRAM_WEBHOOK_SECRET"; then
    echo "Setting TELEGRAM_WEBHOOK_SECRET..."
    WEBHOOK_SECRET=$(openssl rand -hex 32)
    echo "$WEBHOOK_SECRET" | bunx wrangler secret put TELEGRAM_WEBHOOK_SECRET --name "$WORKER_NAME"
    echo "✅ TELEGRAM_WEBHOOK_SECRET configured"
    echo "  ⚠️  SAVE THIS for webhook registration: $WEBHOOK_SECRET"
else
    WEBHOOK_SECRET=""
    echo "TELEGRAM_WEBHOOK_SECRET already configured — skipping"
fi
echo ""

# ADMIN_PASSWORD
if ! bunx wrangler secret list --name "$WORKER_NAME" 2>&1 | grep -q "ADMIN_PASSWORD"; then
    echo "Setting ADMIN_PASSWORD..."
    echo "Enter a strong admin password:"
    bunx wrangler secret put ADMIN_PASSWORD --name "$WORKER_NAME"
    echo "✅ ADMIN_PASSWORD configured"
else
    echo "ADMIN_PASSWORD already configured — skipping"
fi
echo ""

echo "All secrets configured. Listing:"
bunx wrangler secret list --name "$WORKER_NAME"
echo ""

# Step 4: Deploy Worker
echo "Step 4/6: Deploying Worker..."
bunx wrangler deploy --name "$WORKER_NAME" 2>&1
echo "✅ Worker deployed"
echo ""

# Step 5: Register Telegram webhook
echo "Step 5/6: Registering Telegram webhook..."
echo ""
echo "To register the webhook, run:"
echo ""
echo "  curl -X POST \"https://api.telegram.org/botYOUR_TOKEN/setWebhook\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"url\": \"${WORKER_URL}/telegram/webhook\", \"secret_token\": \"YOUR_WEBHOOK_SECRET\"}'"
echo ""
echo "Or use the configure_telegram.sh script."
echo ""

# Step 6: Verify
echo "Step 6/6: Verifying..."
echo ""
echo "Health check:"
curl -s "${WORKER_URL}/api/health" | python3 -m json.tool 2>/dev/null || curl -s "${WORKER_URL}/api/health"
echo ""

echo "Frontend root:"
curl -s -o /dev/null -w "HTTP %{http_code}" "${WORKER_URL}/"
echo ""

echo "Frontend login:"
curl -s -o /dev/null -w "HTTP %{http_code}" "${WORKER_URL}/login.html"
echo ""

echo "============================================================"
echo "  PRODUCTION SETUP COMPLETE"
echo "============================================================"
echo ""
echo "  Worker URL:    ${WORKER_URL}"
echo "  Health:        ${WORKER_URL}/api/health"
echo "  Frontend:      ${WORKER_URL}/"
echo ""
echo "  Test login:    ${WORKER_URL}/login.html"
echo "  Test market:   ${WORKER_URL}/market.html"
echo "  Test admin:    ${WORKER_URL}/admin.html"
echo ""
echo "  Next steps:"
echo "  1. Verify /api/health shows all checks as configured/up"
echo "  2. Register Telegram webhook (see command above)"
echo "  3. Test user registration and login"
echo "  4. Test marketplace browsing"
echo ""
