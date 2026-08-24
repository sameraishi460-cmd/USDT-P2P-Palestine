/**
 * USDT P2P Palestine — Cloudflare Worker API entrypoint.
 *
 * Mounts:
 *   /api/health            — liveness + DB check
 *   /api/auth/*            — register/login/logout/telegram
 *   /api/market/*          — ads browse/create/buy/sell
 *   /api/trades/*          — trade lifecycle, chat, disputes
 *   /api/wallet/*          — balance, deposits (BSC verify), withdrawals
 *   /api/notifications/*   — in-app notifications
 *   /api/admin/*           — admin control center (server-side enforced)
 *   /api/uploads/*         — R2 payment proofs / evidence
 *   /telegram/webhook      — Telegram bot webhook
 */
import { Hono } from "hono";
import type { AppEnv } from "./types";
import { securityHeaders } from "./middleware/auth";
import authRoutes from "./routes/auth";
import marketRoutes from "./routes/market";
import tradeRoutes from "./routes/trades";
import walletRoutes from "./routes/wallet";
import adminRoutes from "./routes/admin";
import miscRoutes from "./routes/misc";
import uploadRoutes from "./routes/uploads";
import { registerV2Routes } from "./routes/v2";
import { handleTelegramUpdate } from "./telegram/webhook";
import { runScheduledTasks } from "./cron";
import { serveStaticFile } from "./static";
import { ensureTables, ensureV2Tables } from "./db-init";


const app = new Hono<AppEnv>();

// Global security headers on every response.
app.use("*", securityHeaders);

// Auto-migrate D1 tables on the first request after deployment.
// Idempotent — ensureTables() checks if tables exist before creating them.
let _dbReady = false;
app.use("/api/*", async (c, next) => {
  if (!_dbReady) {
    try {
      const result = await ensureTables(c.env.DB);
      if (result.migrated) {
        console.log(`[db-init] Auto-migrated: ${result.tableCount} tables created`);
      }
      _dbReady = true;
      // Also ensure V2 tables exist (independent of V1 migration)
      try { await ensureV2Tables(c.env.DB); } catch { /* best effort */ }
    } catch (e: any) {
      console.error("[db-init] Migration failed:", e?.message);
      // Still try V2 tables even if V1 failed
      try { await ensureV2Tables(c.env.DB); } catch { /* best effort */ }
    }
  }
  await next();
});

// ------------------------------------------------------------
// Health
// ------------------------------------------------------------
app.get("/api/health", async (c) => {
  const checks: Record<string, string> = {};
  // D1
  try { await c.env.DB.prepare("SELECT 1").first(); checks.database = "up"; } catch { checks.database = "down"; }
  // Secrets status (never expose values)
  checks.telegram = c.env.TELEGRAM_BOT_TOKEN ? "configured" : "no_token";
  checks.secret_key = c.env.SECRET_KEY ? "configured" : "missing";
  checks.admin_password = c.env.ADMIN_PASSWORD ? "configured" : "missing";
  // BSC RPC quick check
  try {
    const r = await fetch(c.env.BSC_RPC_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", method: "eth_blockNumber", params: [], id: 1 }),
      signal: AbortSignal.timeout(5000),
    });
    checks.bsc_rpc = r.ok ? "up" : "degraded";
  } catch { checks.bsc_rpc = "down"; }
  // Run auto-migration first, then check config
  try {
    const migration = await ensureTables(c.env.DB);
    if (migration.migrated) {
      console.log(`[health] Auto-migrated: ${migration.tableCount} tables`);
      _dbReady = true;
    }
  } catch { /* migration failed — will surface below */ }
  // Platform config — auto-seed if table exists but empty; skip gracefully if table missing
  try {
    const pw = await c.env.DB.prepare("SELECT value FROM platform_config WHERE key='p2p_fee_percent'").first();
    if (pw) {
      checks.config = "loaded";
    } else {
      // Table exists but empty — seed defaults
      const defaults: [string, string][] = [
        ["p2p_fee_percent", "1.0"],
        ["cash_fee_percent", "1.0"],
        ["min_fee", "0.1"],
        ["max_fee", "100.0"],
      ];
      for (const [k, v] of defaults) {
        await c.env.DB.prepare("INSERT OR IGNORE INTO platform_config (key, value) VALUES (?, ?)").bind(k, v).run();
      }
      await c.env.DB.prepare("INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, 3.7, 3.7)").run();
      checks.config = "seeded";
    }
  } catch (e: any) {
    const msg = e?.message || "unknown";
    if (msg.includes("no such table")) {
      checks.config = "pending_migration";
    } else {
      checks.config = "error: " + msg;
    }
  }
  const allUp = checks.database === "up";
  return c.json({
    ok: allUp,
    service: "usdt-palestine-worker",
    environment: c.env.ENVIRONMENT || "development",
    checks,
    time: new Date().toISOString(),
  }, allUp ? 200 : 503);
});

// ------------------------------------------------------------
// API modules
// ------------------------------------------------------------
app.route("/api/auth", authRoutes);
app.route("/api/market", marketRoutes);
app.route("/api/trades", tradeRoutes);
app.route("/api/wallet", walletRoutes);
app.route("/api/admin", adminRoutes);
app.route("/api", miscRoutes); // /api/notifications, /api/profile, /api/reviews, cash
app.route("/api/uploads", uploadRoutes);
// V2 Advanced Features — registered directly on main app
registerV2Routes(app);
console.log("[v2] V2 routes registered at /api/v2/*");

// ------------------------------------------------------------
// Telegram webhook
// ------------------------------------------------------------
app.post("/telegram/webhook", (c) => handleTelegramUpdate(c));

// ------------------------------------------------------------
// Static frontend files (served from bundled frontend/ directory)
// ------------------------------------------------------------
// Static frontend — only handles non-API, non-webhook paths
app.get("/*", async (c) => {
  const pathname = new URL(c.req.url).pathname;
  // Skip all API and webhook paths
  if (pathname.startsWith("/api/") || pathname.startsWith("/telegram/")) {
    return c.json({ error: "المسار غير موجود" }, 404);
  }
  const file = await serveStaticFile(c.env.ASSETS, pathname);
  return file ?? c.json({ error: "المسار غير موجود" }, 404);
});

// ------------------------------------------------------------
// Fallback — non-GET requests that didn't match any route.
// ------------------------------------------------------------
app.notFound((c) => c.json({ error: "المسار غير موجود" }, 404));

app.onError((err, c) => {
  const msg = err?.message || String(err);
  console.error("[worker] unhandled error:", msg, err?.stack?.slice(0, 500));
  // Surface D1 table-missing errors so the admin can diagnose.
  const isTableMissing = msg.includes("no such table") || msg.includes("SQLITE_ERROR");
  return c.json({
    error: "حدث خطأ داخلي، حاول لاحقاً",
    ...(isTableMissing ? { detail: "D1 table missing — run migrations" } : {}),
  }, 500);
});

// ------------------------------------------------------------
// Export: fetch handler + scheduled (Cron) handler
// ------------------------------------------------------------
export default {
  fetch: app.fetch,

  async scheduled(event: ScheduledEvent, env: AppEnv["Bindings"], ctx: ExecutionContext) {
    ctx.waitUntil(runScheduledTasks(env, event.cron));
  },
};
// v35496f6 deployed
