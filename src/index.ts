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

const app = new Hono<AppEnv>();

// Global security headers on every response.
app.use("*", securityHeaders);

// ------------------------------------------------------------
// Health
// ------------------------------------------------------------
app.get("/api/health", async (c) => {
  try {
    await c.env.DB.prepare("SELECT 1").first();
    return c.json({ ok: true, service: "usdt-palestine-worker", db: "up", time: new Date().toISOString() });
  } catch {
    return c.json({ ok: false, db: "down" }, 503);
  }
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
// Fallbacks — never leak internal errors to clients.
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
