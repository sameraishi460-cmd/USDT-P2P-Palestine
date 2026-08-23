#!/bin/bash
# ============================================================
# USDT P2P Palestine — Cloudflare Staging Provisioning Script
# ============================================================
# Run this script AFTER: wrangler login
#
# This script:
#   1. Creates D1 database, R2 bucket, KV namespace
#   2. Applies schema migrations
#   3. Seeds staging data
#   4. Deploys the Worker
#   5. Deploys the Pages frontend
#
# Prerequisites:
#   - bun installed
#   - wrangler authenticated (wrangler login)
#   - python3 available (for seed script)
#
# Usage:
#   bash scripts/provision_cloudflare.sh
# ============================================================

set -e

echo "============================================================"
echo "USDT P2P Palestine — Cloudflare Staging Provisioning"
echo "Time: $(date)"
echo "============================================================"
echo ""

# Step 1: Create D1 Database
echo "Step 1/8: Creating D1 database..."
D1_OUTPUT=$(bunx wrangler d1 create usdt-palestine-db 2>&1)
echo "$D1_OUTPUT"

# Extract database_id from output
D1_ID=$(echo "$D1_OUTPUT" | grep -oP 'database_id = "\K[^"]+' || echo "")
if [ -z "$D1_ID" ]; then
    echo "ERROR: Could not extract D1 database ID"
    echo "Please check the output above and manually set the ID in wrangler.toml"
    exit 1
fi
echo "D1 Database ID: $D1_ID"

# Update wrangler.toml with the real D1 ID
sed -i "s/database_id = \"REPLACE_WITH_D1_DATABASE_ID\"/database_id = \"$D1_ID\"/" wrangler.toml
echo "✅ wrangler.toml updated with D1 ID"
echo ""

# Step 2: Create R2 Bucket
echo "Step 2/8: Creating R2 bucket..."
bunx wrangler r2 bucket create usdt-palestine-uploads 2>&1 || echo "Note: Bucket may already exist"
echo "✅ R2 bucket configured"
echo ""

# Step 3: Create KV Namespace
echo "Step 3/8: Creating KV namespace..."
KV_OUTPUT=$(bunx wrangler kv namespace create RATE_LIMIT 2>&1)
echo "$KV_OUTPUT"

KV_ID=$(echo "$KV_OUTPUT" | grep -oP 'id = "\K[^"]+' || echo "")
if [ -n "$KV_ID" ]; then
    sed -i "s/id = \"REPLACE_WITH_KV_NAMESPACE_ID\"/id = \"$KV_ID\"/" wrangler.toml
    echo "✅ wrangler.toml updated with KV ID: $KV_ID"
else
    echo "WARNING: Could not extract KV ID. Please set manually in wrangler.toml"
fi
echo ""

# Step 4: Apply Schema Migrations
echo "Step 4/8: Applying D1 migrations..."
bunx wrangler d1 migrations apply usdt-palestine-db --remote 2>&1
echo "✅ Schema migrations applied"
echo ""

# Step 5: Verify Tables
echo "Step 5/8: Verifying database tables..."
TABLE_COUNT=$(bunx wrangler d1 execute usdt-palestine-db --remote --command "SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'" 2>&1 | grep -oP '"cnt":\K\d+' || echo "?")
echo "Tables created: $TABLE_COUNT"
echo ""

# Step 6: Seed Staging Data
echo "Step 6/8: Seeding staging data..."
python3 scripts/seed_staging_data.py > /tmp/staging_seed.sql
bunx wrangler d1 execute usdt-palestine-db --remote --file=/tmp/staging_seed.sql 2>&1
rm -f /tmp/staging_seed.sql
echo "✅ Staging data seeded"
echo ""

# Step 7: Deploy Worker
echo "Step 7/8: Deploying Worker..."
bunx wrangler deploy 2>&1
echo "✅ Worker deployed"
echo ""

# Step 8: Deploy Pages
echo "Step 8/8: Deploying Pages frontend..."
bunx wrangler pages deploy frontend --project-name=usdt-palestine 2>&1
echo "✅ Pages deployed"
echo ""

echo "============================================================"
echo "PROVISIONING COMPLETE"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Set secrets: wrangler secret put SECRET_KEY"
echo "  2. Set secrets: wrangler secret put TELEGRAM_BOT_TOKEN"
echo "  3. Set secrets: wrangler secret put TELEGRAM_WEBHOOK_SECRET"
echo "  4. Set secrets: wrangler secret put ADMIN_PASSWORD"
echo "  5. Verify health: curl <YOUR_WORKER_URL>/api/health"
echo "  6. Register Telegram webhook"
echo ""
echo "Run: python3 tests/staging_worker_tests.py --base <YOUR_WORKER_URL>"
