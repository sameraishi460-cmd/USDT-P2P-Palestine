/**
 * Market routes: browse ads with filters, create/edit/disable ads, buy.
 * Preserves existing business rules:
 * - SELL ads require sufficient available balance (locked at buy time).
 * - BUY creates trade + locks seller's USDT in escrow atomically.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireUser, requireCsrf, rateLimit } from "../middleware/auth";
import { escrowLock, notify, auditLog } from "../utils/db";
import { formBody } from "../utils/body";

const market = new Hono<AppEnv>();

// ============================================================
// GET /api/market/price — current market price with spread (public)
// ============================================================
market.get("/price", async (c) => {
  const row = await c.env.DB.prepare(
    "SELECT id, usd_ils, usdt_ils, updated FROM market_price WHERE id = 1"
  ).first<{ id: number; usd_ils: number; usdt_ils: number; updated: string }>();
  if (!row) return c.json({ ok: true, price: { usd_ils: 3.7, usdt_ils: 3.7, buy_price: 3.7, sell_price: 3.7, updated: null, source: 'fallback' } });

  // Read spread from platform config
  const getVal = async (k: string, fb: string) => {
    const r = await c.env.DB.prepare("SELECT value FROM platform_config WHERE key = ?").bind(k).first<{value:string}>();
    return r?.value ?? fb;
  };
  const buySpread = parseFloat(await getVal('buy_spread', '0.005'));
  const sellSpread = parseFloat(await getVal('sell_spread', '0.005'));
  const source = await getVal('market_source', 'unknown');

  const marketPrice = row.usdt_ils;
  const buyPrice = Math.round(marketPrice * (1 + buySpread) * 10000) / 10000;
  const sellPrice = Math.round(marketPrice * (1 - sellSpread) * 10000) / 10000;

  // Calculate 24h change from price_history
  let change24h = 0;
  try {
    const oldPrice = await c.env.DB.prepare(
      `SELECT market_price FROM price_history WHERE pair = 'USDT/ILS' AND created_at <= datetime('now', '-24 hours') ORDER BY created_at DESC LIMIT 1`
    ).first<{market_price: number}>();
    if (oldPrice && oldPrice.market_price > 0) {
      change24h = ((marketPrice - oldPrice.market_price) / oldPrice.market_price) * 100;
      change24h = Math.round(change24h * 100) / 100;
    }
  } catch { /* history may not exist yet */ }

  return c.json({
    ok: true,
    price: {
      usd_ils: row.usd_ils,
      usdt_ils: row.usdt_ils,
      buy_price: buyPrice,
      sell_price: sellPrice,
      buy_spread: buySpread,
      sell_spread: sellSpread,
      change_24h: change24h,
      source,
      updated: row.updated,
    },
  });
});

// ============================================================
// GET /api/market/price/history — price history for charts (public)
// Query: hours=24 (1H, 6H, 24H, 7D)
// ============================================================
market.get("/price/history", async (c) => {
  const hours = parseInt(c.req.query("hours") || "24", 10);
  const limit = Math.min(Math.max(hours, 1), 168); // max 7 days
  const rows = await c.env.DB.prepare(
    `SELECT market_price, buy_price, sell_price, source, created_at
     FROM price_history WHERE pair = 'USDT/ILS'
     AND created_at >= datetime('now', '-${limit} hours')
     ORDER BY created_at ASC LIMIT 200`
  ).all();
  return c.json({ ok: true, history: rows.results ?? [] });
});

// ============================================================
// GET /api/market/fees — fee calculator data (public)
// ============================================================
market.get("/fees", async (c) => {
  const feeRow = await c.env.DB.prepare(
    "SELECT value FROM platform_config WHERE key = 'p2p_fee_percent'"
  ).first<{value:string}>();
  const feePercent = parseFloat(feeRow?.value ?? '1.0');
  return c.json({ ok: true, fee_percent: feePercent });
});

// ============================================================
// GET /api/market/status — market status indicator (public)
// ============================================================
market.get("/status", async (c) => {
  const row = await c.env.DB.prepare(
    "SELECT updated FROM market_price WHERE id = 1"
  ).first<{updated: string}>();
  const source = await c.env.DB.prepare(
    "SELECT value FROM platform_config WHERE key = 'market_source'"
  ).first<{value:string}>();

  const lastUpdate = row?.updated ? new Date(row.updated).getTime() : 0;
  const now = Date.now;
  const age = lastUpdate ? now() - lastUpdate : Infinity;
  const isStale = age > 2 * 60 * 60 * 1000; // stale if > 2 hours old

  return c.json({
    ok: true,
    status: isStale ? 'stale' : 'live',
    source: source?.value ?? 'unknown',
    last_updated: row?.updated ?? null,
    age_minutes: lastUpdate ? Math.round(age / 60000) : null,
  });
});

// ============================================================
// GET /api/market — open ads with optional filters
// Query: type=SELL|BUY, payment=..., min_amount=..., max_amount=..., q=...
// ============================================================
market.get("/", async (c) => {
  const type = c.req.query("type")?.toUpperCase();
  const payment = c.req.query("payment");
  const minAmount = parseFloat(c.req.query("min_amount") || "");
  const maxAmount = parseFloat(c.req.query("max_amount") || "");
  const q = c.req.query("q");

  let sql = `
    SELECT a.id, a.user, a.title, a.amount, a.price, a.payment, a.type,
           a.min_amount, a.max_amount, a.created,
           u.verified, u.rating, u.trades_count
    FROM ads a JOIN users u ON a.user = u.username
    WHERE a.status = 'OPEN'
  `;
  const params: any[] = [];

  if (type === "SELL" || type === "BUY") { sql += " AND a.type = ?"; params.push(type); }
  if (payment) { sql += " AND a.payment LIKE ?"; params.push(`%${payment}%`); }
  if (Number.isFinite(minAmount)) { sql += " AND a.max_amount >= ?"; params.push(minAmount); }
  if (Number.isFinite(maxAmount)) { sql += " AND a.min_amount <= ?"; params.push(maxAmount); }
  if (q) { sql += " AND (a.title LIKE ? OR a.user LIKE ?)"; params.push(`%${q}%`, `%${q}%`); }

  // Sorting
  const sort = c.req.query("sort") || "price";
  if (sort === "rating") sql += " ORDER BY u.rating DESC, a.price ASC";
  else if (sort === "trades") sql += " ORDER BY u.trades_count DESC, a.price ASC";
  else sql += " ORDER BY a.price ASC, u.rating DESC";

  // Pagination
  const limit = Math.min(Number(c.req.query("limit") || "50"), 100);
  const offset = Math.max(Number(c.req.query("offset") || "0"), 0);
  sql += ` LIMIT ? OFFSET ?`;
  params.push(limit, offset);

  // Count for pagination
  let countSql = `SELECT COUNT(*) AS total FROM ads a JOIN users u ON a.user = u.username WHERE a.status = 'OPEN'`;
  const countParams: any[] = [];
  if (type === "SELL" || type === "BUY") { countSql += " AND a.type = ?"; countParams.push(type); }
  if (payment) { countSql += " AND a.payment LIKE ?"; countParams.push(`%${payment}%`); }

  const ads = await c.env.DB.prepare(sql).bind(...params).all();
  const countRow = await c.env.DB.prepare(countSql).bind(...countParams).first<{ total: number }>();
  const price = await c.env.DB.prepare("SELECT usd_ils, usdt_ils FROM market_price WHERE id = 1").first();

  return c.json({ ok: true, ads: ads.results ?? [], price, total: countRow?.total ?? 0, limit, offset });
});

// ============================================================
// GET /api/market/all — all open ads (legacy /all_ads)
// ============================================================
market.get("/all", async (c) => {
  const ads = await c.env.DB.prepare(`
    SELECT a.*, u.verified, u.rating FROM ads a
    JOIN users u ON a.user = u.username
    WHERE a.status = 'OPEN' ORDER BY a.id DESC LIMIT 200
  `).all();
  return c.json({ ok: true, ads: ads.results ?? [] });
});

// ============================================================
// POST /api/ads/create
// ============================================================
market.post("/ads/create", requireUser, requireCsrf, rateLimit(10, 60), async (c) => {
  const username = c.get("user")!.username;
  const body = await formBody(c);

  const title = String(body.title ?? "").trim().slice(0, 120);
  const amount = parseFloat(String(body.amount ?? ""));
  const price = parseFloat(String(body.price ?? ""));
  const payment = String(body.payment ?? "").trim().slice(0, 80);
  const adType = String(body.type ?? "SELL").toUpperCase() === "BUY" ? "BUY" : "SELL";
  const minAmount = Math.max(0, parseFloat(String(body.min_amount ?? "0")) || 0);
  const maxAmountRaw = parseFloat(String(body.max_amount ?? "")) || amount;
  const maxAmount = Math.min(maxAmountRaw, amount);

  if (!title) return c.json({ error: "العنوان مطلوب" }, 400);
  if (!(amount > 0)) return c.json({ error: "المبلغ يجب أن يكون أكبر من صفر" }, 400);
  if (!(price > 0)) return c.json({ error: "السعر يجب أن يكون أكبر من صفر" }, 400);
  if (minAmount >= maxAmount && minAmount > 0) return c.json({ error: "الحد الأدنى يجب أن يكون أقل من الأقصى" }, 400);

  // Business rule: SELL ad requires available balance ≥ amount
  if (adType === "SELL") {
    const wallet = await c.env.DB.prepare(
      "SELECT balance FROM wallets WHERE username = ?"
    ).bind(username).first<{ balance: number }>();
    const bal = wallet?.balance ?? 0;
    if (bal < amount) {
      return c.json({
        error: "رصيد USDT غير كافٍ",
        required: amount,
        available: bal,
        actions: ["إيداع USDT", "إضافة عنوان محفظتي"],
        deposit_url: "/usdt_deposit",
      }, 400);
    }
  }

  const res = await c.env.DB.prepare(
    `INSERT INTO ads (user, title, amount, price, payment, type, min_amount, max_amount)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(username, title, amount, price, payment, adType, minAmount, maxAmount).run();

  await auditLog(c, username, "user", "AD_CREATE", `ad:${res.meta.last_row_id}`, `${adType} ${amount} @ ${price}`);
  return c.json({ ok: true, ad_id: res.meta.last_row_id });
});

// ============================================================
// POST /api/ads/:id/edit
// ============================================================
market.post("/ads/:id/edit", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const body = await formBody(c);

  const ad = await c.env.DB.prepare("SELECT * FROM ads WHERE id = ?").bind(id).first<any>();
  if (!ad) return c.json({ error: "الإعلان غير موجود" }, 404);
  if (ad.user !== username && !c.get("user")!.isAdmin) {
    return c.json({ error: "غير مصرح" }, 403);
  }
  if (ad.status !== "OPEN") return c.json({ error: "لا يمكن تعديل إعلان مغلق" }, 400);

  const title = String(body.title ?? ad.title).trim().slice(0, 120);
  const price = parseFloat(String(body.price ?? ad.price));
  const payment = String(body.payment ?? ad.payment).trim().slice(0, 80);
  if (!(price > 0)) return c.json({ error: "السعر غير صالح" }, 400);

  await c.env.DB.prepare(
    "UPDATE ads SET title = ?, price = ?, payment = ? WHERE id = ?"
  ).bind(title, price, payment, id).run();

  await auditLog(c, username, "user", "AD_EDIT", `ad:${id}`);
  return c.json({ ok: true });
});

// ============================================================
// POST /api/ads/:id/disable
// ============================================================
market.post("/ads/:id/disable", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;

  const ad = await c.env.DB.prepare("SELECT user FROM ads WHERE id = ?").bind(id).first<any>();
  if (!ad) return c.json({ error: "الإعلان غير موجود" }, 404);
  if (ad.user !== username && !c.get("user")!.isAdmin) {
    return c.json({ error: "غير مصرح" }, 403);
  }

  await c.env.DB.prepare("UPDATE ads SET status = 'DISABLED' WHERE id = ?").bind(id).run();
  await auditLog(c, username, "user", "AD_DISABLE", `ad:${id}`);
  return c.json({ ok: true });
});

// ============================================================
// GET /api/ads/my-ads
// ============================================================
market.get("/my-ads", requireUser, async (c) => {
  const username = c.get("user")!.username;
  const ads = await c.env.DB.prepare(
    "SELECT * FROM ads WHERE user = ? ORDER BY id DESC LIMIT 100"
  ).bind(username).all();
  return c.json({ ok: true, ads: ads.results ?? [] });
});

// ============================================================
// POST /api/trades/buy/:adId — create trade + lock escrow atomically
// ============================================================
market.post("/trades/buy/:adId", requireUser, requireCsrf, rateLimit(10, 60), async (c) => {
  const adId = Number(c.req.param("adId"));
  const buyer = c.get("user")!.username;

  const ad = await c.env.DB.prepare(
    "SELECT * FROM ads WHERE id = ? AND status = 'OPEN'"
  ).bind(adId).first<any>();
  if (!ad) return c.json({ error: "الإعلان غير متاح" }, 404);
  if (ad.user === buyer) return c.json({ error: "لا يمكنك الشراء من إعلانك" }, 400);

  const body = await formBody(c);
  let amount = parseFloat(String(body.amount ?? "")) || ad.amount;

  // Clamp to ad limits
  amount = Math.min(Math.max(amount, ad.min_amount || 0), ad.max_amount || ad.amount);
  if (!(amount > 0) || amount > ad.amount) {
    return c.json({ error: `المبلغ يجب أن يكون بين ${ad.min_amount || 0} و ${Math.min(ad.amount, ad.max_amount || ad.amount)}` }, 400);
  }

  // ═══ CRITICAL: Atomically reserve ad amount BEFORE creating trade ═══
  // This prevents the race condition where two concurrent requests
  // both pass the amount check and create duplicate trades.
  // The conditional UPDATE only succeeds if amount >= requested amount AND status = 'OPEN'.
  const reserveResult = await c.env.DB.prepare(
    `UPDATE ads SET amount = amount - ?,
       status = CASE WHEN amount - ? <= 0 THEN 'TRADED' ELSE 'OPEN' END
     WHERE id = ? AND status = 'OPEN' AND amount >= ?`
  ).bind(amount, amount, adId, amount).run();

  if (reserveResult.meta.changes === 0) {
    // Ad was already sold out or another request reserved it first
    return c.json({ error: "الإعلان غير متاح أو المبلغ غير كافٍ" }, 400);
  }

  const feePercent = parseFloat(await getConfigValue(c) || "1.0");

  // Price is LOCKED at creation time — never recalculated later
  const lockedPrice = ad.price;
  const lockedFee = Math.round(amount * feePercent) / 100;

  // Create trade with price lock
  const res = await c.env.DB.prepare(
    `INSERT INTO trades (ad_id, buyer, seller, amount, price, platform_fee, status, escrow_status)
     VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)`
  ).bind(
    adId, buyer, ad.user, amount, lockedPrice,
    lockedFee,
    ad.type === "SELL" ? "LOCKED" : "WAITING"
  ).run();
  const tradeId = Number(res.meta.last_row_id);

  // SELL ad → lock seller's funds in escrow atomically
  if (ad.type === "SELL") {
    const { escrowLock: lockFn } = await import("../utils/db");
    const lock = await lockFn(c.env, ad.user, amount, tradeId);
    if (!lock.ok) {
      // Rollback: restore ad amount and status
      await c.env.DB.prepare(
        `UPDATE ads SET amount = amount + ?,
           status = CASE WHEN amount + ? > 0 THEN 'OPEN' ELSE status END
         WHERE id = ?`
      ).bind(amount, amount, adId).run();
      await c.env.DB.prepare("DELETE FROM trades WHERE id = ?").bind(tradeId).run();
      return c.json({
        error: lock.reason,
        deposit_url: "/usdt_deposit",
        actions: ["إيداع USDT"],
      }, 400);
    }

    // Record in escrow ledger
    const { recordEscrowTransaction } = await import("../escrow");
    await recordEscrowTransaction(c.env.DB, tradeId, ad.user, amount, "LOCK", {
      reason: `قفل ضمان: ${amount} USDT للصفقة #${tradeId}`,
    });
  }

  await notify(c.env, ad.user, "صفقة جديدة 🎉",
    `قام ${buyer} بشراء ${amount} USDT من إعلانك #${adId}. افتح الصفقة للتواصل.`);
  await notify(c.env, buyer, "تم إنشاء الصفقة ✅",
    `تواصل مع البائع ${ad.user} لإتمام الدفع. الصفقة #${tradeId}`);

  await auditLog(c, buyer, "user", "TRADE_CREATE", `trade:${tradeId}`, `${amount} USDT @ ${lockedPrice}`);
  return c.json({ ok: true, trade_id: tradeId });
});

// ============================================================
// GET /api/market/alerts — user's price alerts (auth required)
// ============================================================
market.get("/alerts", requireUser, async (c) => {
  const username = c.get("user")!.username;
  const alerts = await c.env.DB.prepare(
    `SELECT id, pair, direction, target_price, active, triggered, created_at, triggered_at
     FROM price_alerts WHERE username = ? ORDER BY created_at DESC LIMIT 20`
  ).bind(username).all();
  return c.json({ ok: true, alerts: alerts.results ?? [] });
});

// ============================================================
// POST /api/market/alerts — create price alert (auth required)
// ============================================================
market.post("/alerts", requireUser, requireCsrf, rateLimit(20, 60), async (c) => {
  const username = c.get("user")!.username;
  const body = await formBody(c);
  const direction = String(body.direction ?? "").toUpperCase();
  const targetPrice = parseFloat(String(body.target_price ?? ""));
  const pair = String(body.pair ?? "USDT/ILS").trim();

  if (direction !== "ABOVE" && direction !== "BELOW") {
    return c.json({ error: "الاتجاه غير صالح" }, 400);
  }
  if (!(targetPrice > 0)) {
    return c.json({ error: "السعر المستهدف غير صالح" }, 400);
  }

  // Limit: max 10 active alerts per user
  const count = await c.env.DB.prepare(
    "SELECT COUNT(*) as cnt FROM price_alerts WHERE username = ? AND active = 1 AND triggered = 0"
  ).bind(username).first<{cnt: number}>();
  if ((count?.cnt ?? 0) >= 10) {
    return c.json({ error: "الحد الأقصى 10 تنبيهات نشطة" }, 400);
  }

  await c.env.DB.prepare(
    `INSERT INTO price_alerts (username, pair, direction, target_price) VALUES (?, ?, ?, ?)`
  ).bind(username, pair, direction, targetPrice).run();

  return c.json({ ok: true });
});

// ============================================================
// DELETE /api/market/alerts/:id — delete price alert
// ============================================================
market.delete("/alerts/:id", requireUser, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  await c.env.DB.prepare(
    "DELETE FROM price_alerts WHERE id = ? AND username = ?"
  ).bind(id, username).run();
  return c.json({ ok: true });
});

async function getConfigValue(c: any): Promise<string> {
  const row = await c.env.DB.prepare(
    "SELECT value FROM platform_config WHERE key = 'p2p_fee_percent'"
  ).first() as { value: string } | null;
  return row?.value ?? "1.0";
}

export default market;
