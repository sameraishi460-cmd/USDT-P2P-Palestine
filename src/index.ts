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
import { handleTelegramUpdate } from "./telegram/webhook";
import { runScheduledTasks } from "./cron";
import { serveStaticFile } from "./static";


const app = new Hono<AppEnv>();

// Global security headers on every response.
app.use("*", securityHeaders);

// ------------------------------------------------------------
// Health
// ------------------------------------------------------------
app.get("/api/health", async (c) => {
  const checks: Record<string, string> = {};
  // D1
  try { await c.env.DB.prepare("SELECT 1").first(); checks.database = "up"; } catch { checks.database = "down"; }
  // Telegram token configured
  checks.telegram = c.env.TELEGRAM_BOT_TOKEN ? "configured" : "no_token";
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
  // Platform config
  try {
    const pw = await c.env.DB.prepare("SELECT value FROM platform_config WHERE key='p2p_fee_percent'").first();
    checks.config = pw ? "loaded" : "defaults";
  } catch { checks.config = "error"; }
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

// ------------------------------------------------------------
// Telegram webhook
// ------------------------------------------------------------
app.post("/telegram/webhook", (c) => handleTelegramUpdate(c));

// ------------------------------------------------------------
// Static frontend files (served from bundled frontend/ directory)
// ------------------------------------------------------------
app.get("/*", async (c) => {
  const file = await serveStaticFile(c.env.ASSETS, new URL(c.req.url).pathname);
  return file ?? c.json({ error: "المسار غير موجود" }, 404);
});

// ------------------------------------------------------------
// Fallback — non-GET requests that didn't match any route.
// ------------------------------------------------------------
app.notFound((c) => c.json({ error: "المسار غير موجود" }, 404));

app.onError((err, c) => {
  console.error("[worker] unhandled error:", err?.message, err?.stack?.slice(0, 500));
  return c.json({ error: "حدث خطأ داخلي، حاول لاحقاً" }, 500);
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
