# USDT P2P Palestine — Cloudflare Deployment Guide

## Architecture Overview

```
USDT Palestine Platform
        │
        ├── Cloudflare Pages    → Frontend (static HTML + CSS + JS)
        │
        ├── Cloudflare Worker   → Backend API (Hono + TypeScript)
        │       │
        │       ├── D1          → Database (SQLite-compatible)
        │       ├── R2          → File storage (payment proofs, evidence)
        │       ├── KV          → Rate limiting
        │       ├── Cron        → Scheduled tasks (price updates, trade expiry)
        │       └── Telegram    → Bot webhook
        │
        └── BSC RPC             → Blockchain verification (USDT on BEP-20)
```

## Prerequisites

1. Cloudflare account (free tier works for staging)
2. Node.js 18+ and Bun
3. Telegram BotFather access (for new bot token)
4. Wrangler CLI installed globally: `bun add -g wrangler`

## Step 1: Authenticate with Cloudflare

```bash
wrangler login
```

This opens a browser to authenticate. Your `account_id` is auto-detected.

## Step 2: Create Cloudflare Resources

### D1 Database
```bash
wrangler d1 create usdt-palestine-db
```
Copy the `database_id` and paste it into `wrangler.toml`:
```toml
[[d1_databases]]
binding = "DB"
database_name = "usdt-palestine-db"
database_id = "YOUR_DATABASE_ID_HERE"
```

### R2 Bucket
```bash
wrangler r2 bucket create usdt-palestine-uploads
```

### KV Namespace
```bash
wrangler kv namespace create RATE_LIMIT
```
Copy the `id` and paste it into `wrangler.toml`:
```toml
[[kv_namespaces]]
binding = "RATE_LIMIT"
id = "YOUR_KV_NAMESPACE_ID_HERE"
```

## Step 3: Run Database Migrations

### Local (for development/testing):
```bash
wrangler d1 migrations apply usdt-palestine-db --local
```

### Remote (staging):
```bash
wrangler d1 migrations apply usdt-palestine-db --remote
```

### Verify tables:
```bash
wrangler d1 execute usdt-palestine-db --remote --command "SELECT COUNT(*) as table_count FROM sqlite_master WHERE type='table'"
```

Expected: ~33 tables.

## Step 4: Configure Secrets

**CRITICAL:** Never commit these to GitHub. Use `wrangler secret put`.

```bash
# Session/JWT signing key (generate a random 64-char string)
wrangler secret put SECRET_KEY

# Telegram bot token (NEW — old one is compromised)
wrangler secret put TELEGRAM_BOT_TOKEN

# Telegram webhook secret (random string for webhook validation)
wrangler secret put TELEGRAM_WEBHOOK_SECRET

# Admin dashboard password
wrangler secret put ADMIN_PASSWORD
```

For production, also set:
```bash
wrangler secret put BSC_RPC_URL
```

## Step 5: Set Environment Variables

In `wrangler.toml`, update the `[vars]` section:

```toml
[vars]
ENVIRONMENT = "staging"
APP_URL = "https://your-worker.usdt-palestine.workers.dev"
PLATFORM_WALLET = "0x659dd7cba24363c903abe3fddfc89eb30ffbf58a"
USDT_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"
BSC_RPC_URL = "https://bsc-dataseed.binance.org/"
USDT_DECIMALS = "6"
TELEGRAM_ADMIN_ID = ""  # Set your Telegram user ID
```

## Step 6: Seed Staging Data

```bash
python3 scripts/seed_staging_data.py --apply --remote
```

This creates:
- Admin account: `admin` / `Admin123!@#`
- Seller: `seller_ahmed` / `Test1234` (1000 USDT)
- Buyer: `buyer_khalid` / `Test1234` (500 USDT)
- Trader: `trader_fatima` / `Test1234` (2000 USDT)
- New user: `new_user` / `Test1234` (50 USDT, unverified)
- Dispute user: `dispute_user` / `Test1234` (300 USDT)

## Step 7: Deploy the Worker

```bash
# Deploy to staging
wrangler deploy

# Verify deployment
wrangler tail
```

### Set the Worker URL in wrangler.toml:
```toml
[env.staging]
name = "usdt-palestine-api"
vars = { ENVIRONMENT = "staging", APP_URL = "https://usdt-palestine-api.YOUR_SUBDOMAIN.workers.dev" }
```

## Step 8: Verify the Health Endpoint

```bash
curl https://usdt-palestine-api.YOUR_SUBDOMAIN.workers.dev/api/health
```

Expected response:
```json
{
  "ok": true,
  "service": "usdt-palestine-worker",
  "environment": "staging",
  "checks": {
    "database": "up",
    "telegram": "configured",
    "bsc_rpc": "up",
    "config": "loaded"
  }
}
```

## Step 9: Register Telegram Webhook

```bash
# Set the webhook with your NEW bot token
curl -X POST "https://api.telegram.org/botYOUR_NEW_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://usdt-palestine-api.YOUR_SUBDOMAIN.workers.dev/telegram/webhook",
    "secret_token": "YOUR_WEBHOOK_SECRET"
  }'
```

Verify:
```bash
curl "https://api.telegram.org/botYOUR_NEW_TOKEN/getWebhookInfo"
```

## Step 10: Deploy Cloudflare Pages

### Option A: Via Wrangler (recommended)
```bash
wrangler pages deploy frontend --project-name=usdt-palestine
```

### Option B: Via Cloudflare Dashboard
1. Go to Pages → Create a project
2. Connect to GitHub repository
3. Set:
   - Build command: `echo "No build needed — static files"`
   - Build output directory: `frontend`
4. Deploy

### Configure Pages URL:
The Pages deployment gives you a URL like:
`https://usdt-palestine.pages.dev`

## Step 11: Configure Frontend API Base URL

In `frontend/assets/app.js`, the API_BASE is already configured to use the same origin:
```javascript
const API_BASE = window.API_BASE || location.origin + '/api';
```

For the Cloudflare architecture, the Pages frontend calls the Worker API.
If using different domains, you'll need CORS configuration or a custom domain.

### Recommended: Same-domain routing
1. Create a custom domain (e.g., `usdt-palestine.com`)
2. Set up Workers route: `usdt-palestine.com/api/*` → Worker
3. Serve Pages on `usdt-palestine.com/*`

### Alternative: Subdomain routing
1. Pages: `usdt-palestine.pages.dev`
2. Worker: `api.usdt-palestine.pages.dev`

For staging, you can set `window.API_BASE` in a config script tag:
```html
<script>window.API_BASE = 'https://usdt-palestine-api.YOUR_SUBDOMAIN.workers.dev/api';</script>
```

## Step 12: Configure Cron Triggers

Cron triggers are already configured in `wrangler.toml`:
```toml
[triggers]
crons = ["0 * * * *"]  # Every hour
```

The Worker's `scheduled()` handler runs:
1. **Price update** (every cron tick) — CoinGecko → Binance fallback
2. **Stale trade expiry** (every cron tick) — Cancel trades stuck >24h

### Verify Cron:
```bash
wrangler tail --format json
# Then trigger a cron manually from dashboard or wait for the next hour
```

## Step 13: Run Staging Tests

### Start local dev server:
```bash
bun run dev  # Runs on localhost:8788
```

### In another terminal:
```bash
python3 tests/staging_worker_tests.py --base http://localhost:8788
```

### Verify all tests pass before proceeding.

## Step 14: Migration Script

### Prepare production migration:
```bash
# Compare counts between SQLite and D1
python3 scripts/migrate_sqlite_to_d1.py database.db --compare

# Financial reconciliation
python3 scripts/migrate_sqlite_to_d1.py database.db --reconcile

# Export SQL (review before executing!)
python3 scripts/migrate_sqlite_to_d1.py database.db --export > migration.sql
```

### Execute production migration (ONLY after approval):
```bash
# First, backup the SQLite database
cp database.db database.db.backup.$(date +%Y%m%d_%H%M%S)

# Then apply to D1
wrangler d1 execute usdt-palestine-db --remote --file=migration.sql
```

## Step 15: Custom Domain (Post-Staging)

After staging verification:

1. Add custom domain in Cloudflare Pages
2. Set up Workers route for `/api/*`
3. Update `APP_URL` in wrangler.toml
4. Update Telegram webhook URL
5. Test all flows on custom domain

---

## Production Checklist

- [ ] D1 database created and migrations applied
- [ ] R2 bucket created
- [ ] KV namespace created
- [ ] All secrets configured (SECRET_KEY, TELEGRAM_BOT_TOKEN, etc.)
- [ ] NEW Telegram bot token (old one compromised)
- [ ] Telegram webhook registered
- [ ] Worker deployed and health check passing
- [ ] Pages deployed and accessible
- [ ] Cron triggers configured and verified
- [ ] Staging seed data loaded
- [ ] All staging tests passing
- [ ] SQLite backup created
- [ ] Migration script tested
- [ ] No production data migrated yet
- [ ] No DNS changes made yet
- [ ] Old Flask system still running and untouched

---

## Rollback Plan

If anything goes wrong:

1. **Worker issues:** `wrangler rollback` to revert last deployment
2. **Database issues:** The original SQLite database is untouched
3. **Pages issues:** Cloudflare Pages keeps deployment history
4. **Telegram:** Revert webhook to old URL if needed
5. **DNS:** No DNS changes were made during staging

---

## Monitoring

### Worker Logs
```bash
wrangler tail
```

### D1 Queries
```bash
wrangler d1 execute usdt-palestine-db --remote --command "SELECT COUNT(*) FROM trades WHERE status='COMPLETED'"
```

### Health Check
```bash
curl -s https://YOUR_WORKER_URL/api/health | jq .
```

### Cron Status
Check Cloudflare Dashboard → Workers → Triggers tab.
