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

  sql += " ORDER BY a.price ASC, u.rating DESC LIMIT 100";

  const ads = await c.env.DB.prepare(sql).bind(...params).all();
  const price = await c.env.DB.prepare("SELECT usd_ils, usdt_ils FROM market_price WHERE id = 1").first();

  return c.json({ ok: true, ads: ads.results ?? [], price });
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

  const feePercent = parseFloat(await getConfigValue(c) || "1.0");

  // Create trade first to get an ID for the ledger reference
  const res = await c.env.DB.prepare(
    `INSERT INTO trades (ad_id, buyer, seller, amount, price, platform_fee, status, escrow_status)
     VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)`
  ).bind(
    adId, buyer, ad.user, amount, ad.price,
    Math.round(amount * feePercent) / 100,
    ad.type === "SELL" ? "LOCKED" : "WAITING"
  ).run();
  const tradeId = Number(res.meta.last_row_id);

  // SELL ad → lock seller's funds in escrow atomically (with trade ref)
  if (ad.type === "SELL") {
    const lock = await escrowLock(c.env, ad.user, amount, tradeId);
    if (!lock.ok) {
      // Rollback: delete the just-created trade and fail cleanly
      await c.env.DB.prepare("DELETE FROM trades WHERE id = ?").bind(tradeId).run();
      return c.json({
        error: lock.reason,
        deposit_url: "/usdt_deposit",
        actions: ["إيداع USDT"],
      }, 400);
    }
  }

  await c.env.DB.prepare(
    "UPDATE ads SET amount = amount - ?, status = CASE WHEN amount - ? <= 0 THEN 'TRADED' ELSE 'OPEN' END WHERE id = ?"
  ).bind(amount, amount, adId).run();

  await notify(c.env, ad.user, "صفقة جديدة 🎉",
    `قام ${buyer} بشراء ${amount} USDT من إعلانك #${adId}. افتح الصفقة للتواصل.`);
  await notify(c.env, buyer, "تم إنشاء الصفقة ✅",
    `تواصل مع البائع ${ad.user} لإتمام الدفع. الصفقة #${tradeId}`);

  await auditLog(c, buyer, "user", "TRADE_CREATE", `trade:${tradeId}`, `${amount} USDT @ ${ad.price}`);
  return c.json({ ok: true, trade_id: tradeId });
});

async function getConfigValue(c: any): Promise<string> {
  const row = await c.env.DB.prepare(
    "SELECT value FROM platform_config WHERE key = 'p2p_fee_percent'"
  ).first() as { value: string } | null;
  return row?.value ?? "1.0";
}

export default market;
