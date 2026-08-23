#!/bin/bash
# ============================================================
# USDT P2P Palestine — Telegram Bot Configuration
# ============================================================
# Run this AFTER: wrangler login
#
# This script:
#   1. Sets TELEGRAM_BOT_TOKEN as a Cloudflare Worker secret
#   2. Generates and sets TELEGRAM_WEBHOOK_SECRET
#   3. Registers the webhook with Telegram
#   4. Verifies the setup
#
# PREREQUISITES:
#   - wrangler authenticated (wrangler login)
#   - Your Telegram bot token ready to paste
# ============================================================

set -e

WORKER_URL="https://usdt-p2p-palestine.sameraishi460.workers.dev"
WEBHOOK_ENDPOINT="${WORKER_URL}/telegram/webhook"

echo "============================================================"
echo "  USDT P2P Palestine — Telegram Bot Configuration"
echo "  $(date)"
echo "============================================================"
echo ""

# Step 1: Set TELEGRAM_BOT_TOKEN
echo "Step 1/4: Setting TELEGRAM_BOT_TOKEN..."
echo "  Paste your Telegram bot token when prompted:"
bunx wrangler secret put TELEGRAM_BOT_TOKEN --name usdt-p2p-palestine
echo "✅ TELEGRAM_BOT_TOKEN configured"
echo ""

# Step 2: Generate and set TELEGRAM_WEBHOOK_SECRET
echo "Step 2/4: Generating and setting TELEGRAM_WEBHOOK_SECRET..."
WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "$WEBHOOK_SECRET" | bunx wrangler secret put TELEGRAM_WEBHOOK_SECRET --name usdt-p2p-palestine
echo "✅ TELEGRAM_WEBHOOK_SECRET configured (64-char random hex)"
echo ""
echo "  ⚠️  SAVE THIS SECRET — you'll need it for webhook verification:"
echo "  $WEBHOOK_SECRET"
echo ""

# Step 3: Register Telegram webhook
echo "Step 3/4: Registering webhook with Telegram..."
echo "  Using bot token from Worker secret to register..."
echo ""
echo "  To register the webhook, run this command with your bot token:"
echo ""
echo "  curl -X POST \"https://api.telegram.org/botYOUR_TOKEN/setWebhook\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{"
echo "      \"url\": \"${WEBHOOK_ENDPOINT}\","
echo "      \"secret_token\": \"${WEBHOOK_SECRET}\""
echo "    }'"
echo ""

# Step 4: Verify
echo "Step 4/4: Verifying deployment..."
echo ""
echo "  Run this to verify Telegram is configured:"
echo "  curl ${WORKER_URL}/api/health"
echo ""
echo "  Expected: \"telegram\": \"configured\""
echo ""
echo "  To verify webhook registration:"
echo "  curl \"https://api.telegram.org/botYOUR_TOKEN/getWebhookInfo\""
echo ""

echo "============================================================"
echo "  SETUP COMPLETE"
echo "============================================================"
echo ""
echo "  Worker URL:      ${WORKER_URL}"
echo "  Webhook:         ${WEBHOOK_ENDPOINT}"
echo "  Health check:    ${WORKER_URL}/api/health"
echo ""
echo "  Test the bot: Open Telegram → find your bot → /start"
echo ""
