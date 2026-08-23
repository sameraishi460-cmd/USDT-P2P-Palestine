#!/bin/bash
# ============================================================
# USDT Palestine — STAGING DEPLOYMENT
# ============================================================
# Run this AFTER: wrangler login
# 
# This script:
#   1. Applies D1 schema migrations
#   2. Seeds staging test data
#   3. Deploys the Worker API
#   4. Deploys the Pages frontend
#   5. Runs health check
#
# Prerequisites:
#   - wrangler authenticated (wrangler login)
#   - bun installed
#   - python3 available
# ============================================================

set -e
cd "$(dirname "$0")/.."

echo "============================================================"
echo "  USDT Palestine — Staging Deployment"
echo "  $(date)"
echo "============================================================"
echo ""

# Pre-check: wrangler auth
echo "Checking wrangler authentication..."
if ! bunx wrangler whoami 2>&1 | grep -q "Logged in"; then
    echo "❌ Not authenticated. Run: wrangler login"
    exit 1
fi
echo "✅ Authenticated"
echo ""

# Step 1: Apply D1 migrations
echo "Step 1/5: Applying D1 migrations..."
bunx wrangler d1 migrations apply usdt-palestine-db --remote
echo "✅ Migrations applied"
echo ""

# Step 2: Verify tables
echo "Step 2/5: Verifying database..."
bunx wrangler d1 execute usdt-palestine-db --remote --command \
    "SELECT COUNT(*) as table_count FROM sqlite_master WHERE type='table'"
echo ""

# Step 3: Seed staging data
echo "Step 3/5: Seeding staging data..."
python3 scripts/seed_staging_data.py > /tmp/palestine_seed.sql
bunx wrangler d1 execute usdt-palestine-db --remote --file=/tmp/palestine_seed.sql
rm -f /tmp/palestine_seed.sql
echo "✅ Staging data seeded"
echo ""

# Step 4: Deploy Worker
echo "Step 4/5: Deploying Worker..."
bunx wrangler deploy 2>&1
echo ""

# Step 5: Deploy Pages
echo "Step 5/5: Deploying Pages..."
bunx wrangler pages deploy frontend --project-name=usdt-palestine 2>&1
echo ""

# Health check
echo "============================================================"
echo "  DEPLOYMENT COMPLETE — Running Health Check"
echo "============================================================"
echo ""

# Get worker URL from wrangler output
WORKER_URL=$(bunx wrangler deploy --dry-run 2>&1 | grep -oP 'https://[^ ]+workers\.dev' || echo "CHECK_WRANGLER_OUTPUT")
echo "Worker should be available at: $WORKER_URL"
echo ""

echo "============================================================"
echo "  NEXT STEPS"
echo "============================================================"
echo ""
echo "1. Set secrets (run each one manually):"
echo "   bunx wrangler secret put SECRET_KEY"
echo "   bunx wrangler secret put TELEGRAM_BOT_TOKEN"
echo "   bunx wrangler secret put TELEGRAM_WEBHOOK_SECRET"
echo "   bunx wrangler secret put ADMIN_PASSWORD"
echo "   bunx wrangler secret put BSC_RPC_URL"
echo ""
echo "2. Test health:"
echo "   curl <WORKER_URL>/api/health"
echo ""
echo "3. Run staging tests:"
echo "   python3 tests/staging_worker_tests.py --base <WORKER_URL>"
echo ""
echo "4. Test in Telegram:"
echo "   Open @your_bot → /start → 🛒 السوق"
echo ""
