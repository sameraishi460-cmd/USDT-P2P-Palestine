# USDT P2P Palestine — Staging Deployment Runbook

## Quick Start (One-Shot)

If you have `wrangler login` already done:

```bash
bash scripts/provision_cloudflare.sh
```

Then manually set secrets (Step 5 below).

---

## Manual Step-by-Step

### Step 1: Authenticate with Cloudflare

```bash
wrangler login
```

This opens a browser. Log in to your Cloudflare account.

Verify:
```bash
wrangler whoami
```

Expected: Shows your account email and ID.

---

### Step 2: Create Cloudflare Resources

#### D1 Database
```bash
wrangler d1 create usdt-palestine-db
```
Copy the `database_id` from the output.

#### R2 Bucket
```bash
wrangler r2 bucket create usdt-palestine-uploads
```

#### KV Namespace
```bash
wrangler kv namespace create RATE_LIMIT
```
Copy the `id` from the output.

---

### Step 3: Update wrangler.toml

Replace the placeholder IDs in `wrangler.toml`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "usdt-palestine-db"
database_id = "YOUR_D1_DATABASE_ID"

[[r2_buckets]]
binding = "R2"
bucket_name = "usdt-palestine-uploads"

[[kv_namespaces]]
binding = "RATE_LIMIT"
id = "YOUR_KV_NAMESPACE_ID"
```

---

### Step 4: Apply Schema & Seed Data

```bash
# Apply migrations
wrangler d1 migrations apply usdt-palestine-db --remote

# Verify tables (should show ~33)
wrangler d1 execute usdt-palestine-db --remote --command "SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table'"

# Seed staging data
python3 scripts/seed_staging_data.py > /tmp/seed.sql
wrangler d1 execute usdt-palestine-db --remote --file=/tmp/seed.sql
rm /tmp/seed.sql
```

---

### Step 5: Set Secrets

**CRITICAL: Never commit these values. Set them interactively.**

```bash
# Generate a random SECRET_KEY (64 chars)
wrangler secret put SECRET_KEY
# Paste: openssl rand -hex 32

# Telegram bot token (NEW — old one is compromised in Git history)
wrangler secret put TELEGRAM_BOT_TOKEN
# Paste: your new token from @BotFather

# Webhook secret (random string)
wrangler secret put TELEGRAM_WEBHOOK_SECRET
# Paste: openssl rand -hex 16

# Admin password
wrangler secret put ADMIN_PASSWORD
# Paste: your strong admin password

# BSC RPC
wrangler secret put BSC_RPC_URL
# Paste: https://bsc-dataseed.binance.org/
```

---

### Step 6: Deploy Worker

```bash
wrangler deploy
```

Verify:
```bash
# Get your Worker URL from the output, then:
curl https://YOUR-WORKER-URL/api/health
```

Expected:
```json
{
  "ok": true,
  "service": "usdt-palestine-worker",
  "environment": "development",
  "checks": {
    "database": "up",
    "telegram": "configured",
    "config": "loaded"
  }
}
```

---

### Step 7: Deploy Pages Frontend

```bash
wrangler pages deploy frontend --project-name=usdt-palestine
```

This gives you a URL like:
`https://usdt-palestine.pages.dev`

---

### Step 8: Configure Frontend → Worker Connection

Since Pages and Worker are on different domains, update the frontend to point at the Worker:

In `frontend/assets/app.js`, change line 5:
```javascript
const API_BASE = window.API_BASE || location.origin + '/api';
```
to:
```javascript
const API_BASE = window.API_BASE || 'https://YOUR-WORKER-URL/api';
```

Then re-deploy Pages:
```bash
wrangler pages deploy frontend --project-name=usdt-palestine
```

---

### Step 9: Register Telegram Webhook

```bash
curl -X POST "https://api.telegram.org/botYOUR_NEW_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://YOUR-WORKER-URL/telegram/webhook",
    "secret_token": "YOUR_WEBHOOK_SECRET"
  }'
```

Verify:
```bash
curl "https://api.telegram.org/botYOUR_NEW_TOKEN/getWebhookInfo"
```

---

### Step 10: Run Staging Tests

```bash
python3 tests/staging_worker_tests.py --base https://YOUR-WORKER-URL
```

Also test manually in Telegram:
1. Open @YOUR_BOT in Telegram
2. Send /start
3. Click "🛒 السوق" to open the WebApp
4. Register a test account
5. Browse marketplace
6. Create a trade
7. Test wallet deposit/withdrawal

---

## Staging Test Accounts

| Username | Password | Role | Balance |
|---|---|---|---|
| `admin` | `Admin123!@#` | ADMIN | 100 USDT |
| `seller_ahmed` | `Test1234` | SELLER | 1,000 USDT |
| `buyer_khalid` | `Test1234` | BUYER | 500 USDT |
| `trader_fatima` | `Test1234` | TRADER | 2,000 USDT |
| `new_user` | `Test1234` | UNVERIFIED | 50 USDT |
| `dispute_user` | `Test1234` | DISPUTE | 300 USDT |

---

## Troubleshooting

### Health check returns 503
- Check D1 binding: `wrangler d1 execute usdt-palestine-db --remote --command "SELECT 1"`
- Check secrets: `wrangler secret list`

### Frontend can't reach API
- Verify API_BASE in app.js matches your Worker URL
- Check CORS: Worker uses Hono's default CORS (allows all origins in dev)

### Telegram bot not responding
- Verify webhook: `curl "https://api.telegram.org/botTOKEN/getWebhookInfo"`
- Check secret token matches what's configured
- Ensure new bot token (old one is compromised)

### Cron not running
- Check in Cloudflare Dashboard → Workers → Triggers
- Manual test: `curl https://YOUR-WORKER-URL/api/health` (cron runs hourly)

---

## What's Running Where

| Component | URL | Status |
|---|---|---|
| Frontend (Pages) | https://usdt-palestine.pages.dev | After deploy |
| API (Worker) | https://YOUR-WORKER-URL | After deploy |
| Database (D1) | usdt-palestine-db | After migrations |
| Storage (R2) | usdt-palestine-uploads | After creation |
| Rate Limit (KV) | RATE_LIMIT | After creation |
| Cron | Hourly (price + trade expiry) | Built into Worker |
| Telegram | Webhook on Worker | After registration |

---

## ⚠️ What NOT To Do

- ❌ Do NOT run `wrangler d1 execute ... --file=migration.sql` with production data
- ❌ Do NOT change production DNS
- ❌ Do NOT switch the production Telegram bot webhook
- ❌ Do NOT disable the Flask application
- ❌ Do NOT delete the SQLite database
- ❌ Do NOT commit any secrets to Git
