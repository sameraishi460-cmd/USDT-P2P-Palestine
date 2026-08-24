/**
 * Misc routes: notifications, profile, reviews, cash marketplace/trades.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireUser, requireCsrf, rateLimit } from "../middleware/auth";
import { notify, auditLog, ensureWallet } from "../utils/db";
import { formBody } from "../utils/body";

const misc = new Hono<AppEnv>();

// ============================================================
// Notifications
// ============================================================
misc.get("/notifications", requireUser, async (c) => {
  const username = c.get("user")!.username;
  const rows = await c.env.DB.prepare(
    "SELECT * FROM notifications WHERE username = ? ORDER BY id DESC LIMIT 50"
  ).bind(username).all();
  const unseen = await c.env.DB.prepare(
    "SELECT COUNT(*) AS cnt FROM notifications WHERE username = ? AND seen = 0"
  ).bind(username).first<{ cnt: number }>();
  return c.json({ ok: true, notifications: rows.results ?? [], unread: unseen?.cnt ?? 0 });
});

misc.post("/notifications/mark-read", requireUser, requireCsrf, async (c) => {
  await c.env.DB.prepare(
    "UPDATE notifications SET seen = 1 WHERE username = ?"
  ).bind(c.get("user")!.username).run();
  return c.json({ ok: true });
});

// ============================================================
// Profile
// ============================================================
misc.get("/profile", requireUser, async (c) => {
  const username = c.get("user")!.username;
  const user = await c.env.DB.prepare(
    `SELECT username, phone, bank, iban, payment_method, usdt_wallet,
            rating, verified, trades_count, status, first_name, created_at
     FROM users WHERE username = ?`
  ).bind(username).first();

  const stats = await c.env.DB.prepare(
    `SELECT
       COUNT(*) AS total,
       SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS completed,
       SUM(CASE WHEN status='DISPUTED' THEN 1 ELSE 0 END) AS disputed
     FROM trades WHERE buyer = ? OR seller = ?`
  ).bind(username, username).first<any>();

  return c.json({ ok: true, profile: user, stats });
});

misc.post("/profile/edit", requireUser, requireCsrf, async (c) => {
  const username = c.get("user")!.username;
  const body = await formBody(c);

  const phone = String(body.phone ?? "").trim().slice(0, 20);
  const bank = String(body.bank ?? "").trim().slice(0, 60);
  const iban = String(body.iban ?? "").trim().slice(0, 40);
  const paymentMethod = String(body.payment_method ?? "").trim().slice(0, 80);
  const firstName = String(body.first_name ?? "").trim().slice(0, 40);

  if (!/^[0-9+\-\s]{6,20}$/.test(phone)) return c.json({ error: "رقم الهاتف غير صالح" }, 400);

  await c.env.DB.prepare(
    `UPDATE users SET phone=?, bank=?, iban=?, payment_method=?, first_name=? WHERE username=?`
  ).bind(phone, bank, iban, paymentMethod, firstName, username).run();

  return c.json({ ok: true });
});

// ============================================================
// Reviews
// ============================================================
misc.post("/reviews/:tradeId", requireUser, requireCsrf, async (c) => {
  const tradeId = Number(c.req.param("tradeId"));
  const from = c.get("user")!.username;

  const trade = await c.env.DB.prepare(
    "SELECT * FROM trades WHERE id = ? AND status = 'COMPLETED'"
  ).bind(tradeId).first<any>();
  if (!trade) return c.json({ error: "الصفقة غير موجودة أو غير مكتملة" }, 404);
  if (trade.buyer !== from && trade.seller !== from) {
    return c.json({ error: "غير مصرح" }, 403);
  }
  const to = trade.buyer === from ? trade.seller : trade.buyer;

  const already = await c.env.DB.prepare(
    "SELECT id FROM reviews WHERE trade_id = ? AND from_user = ?"
  ).bind(tradeId, from).first();
  if (already) return c.json({ error: "قيّمت هذه الصفقة بالفعل" }, 409);

  const body = await formBody(c);
  const rating = parseInt(String(body.rating ?? ""), 10);
  const comment = String(body.comment ?? "").trim().slice(0, 300);
  if (!(rating >= 1 && rating <= 5)) return c.json({ error: "التقييم يجب أن يكون من 1 إلى 5" }, 400);

  await c.env.DB.batch([
    c.env.DB.prepare(
      "INSERT INTO reviews (trade_id, from_user, to_user, rating, comment) VALUES (?, ?, ?, ?, ?)"
    ).bind(tradeId, from, to, rating, comment),
    // Recompute rating from actual reviews — cannot be faked
    c.env.DB.prepare(
      `UPDATE users SET rating = (SELECT AVG(rating) FROM reviews WHERE to_user = ?)
       WHERE username = ?`
    ).bind(to, to),
  ]);

  return c.json({ ok: true });
});

// ============================================================
// Cash marketplace
// ============================================================
misc.get("/cash/market", async (c) => {
  const city = c.req.query("city");
  let sql = `
    SELECT ca.*, u.verified, u.rating, u.trades_count
    FROM cash_ads ca JOIN users u ON ca.user = u.username
    WHERE ca.status = 'OPEN'`;
  const params: any[] = [];
  if (city) { sql += " AND ca.city LIKE ?"; params.push(`%${city}%`); }
  sql += " ORDER BY ca.id DESC LIMIT 100";
  const ads = await c.env.DB.prepare(sql).bind(...params).all();
  return c.json({ ok: true, cash_ads: ads.results ?? [] });
});

misc.post("/cash/create-ad", requireUser, requireCsrf, rateLimit(5, 300), async (c) => {
  const username = c.get("user")!.username;
  const body = await formBody(c);

  const title = String(body.title ?? "").trim().slice(0, 120);
  const amount = parseFloat(String(body.amount ?? ""));
  const price = parseFloat(String(body.price ?? ""));
  const city = String(body.city ?? "").trim().slice(0, 60);
  const location = String(body.location ?? "").trim().slice(0, 200);
  const notes = String(body.notes ?? "").trim().slice(0, 500);
  const payment = String(body.payment ?? "").trim().slice(0, 80);

  if (!title) return c.json({ error: "العنوان مطلوب" }, 400);
  if (!(amount > 0)) return c.json({ error: "المبلغ غير صالح" }, 400);
  if (!(price > 0)) return c.json({ error: "السعر غير صالح" }, 400);
  if (!city) return c.json({ error: "المدينة مطلوبة للمقابلة الشخصية" }, 400);

  const res = await c.env.DB.prepare(
    `INSERT INTO cash_ads (user, title, amount, price, payment, city, location, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(username, title, amount, price, payment, city, location, notes).run();

  await auditLog(c, username, "user", "CASH_AD_CREATE", `cash_ad:${res.meta.last_row_id}`);
  return c.json({ ok: true, ad_id: res.meta.last_row_id });
});

misc.get("/cash/ad/:id", async (c) => {
  const id = Number(c.req.param("id"));
  const ad = await c.env.DB.prepare(
    `SELECT ca.*, u.verified, u.rating, u.trades_count
     FROM cash_ads ca JOIN users u ON ca.user = u.username
     WHERE ca.id = ? AND ca.status != 'DISABLED'`
  ).bind(id).first();
  if (!ad) return c.json({ error: "الإعلان غير موجود" }, 404);
  return c.json({ ok: true, ad });
});

misc.post("/cash/buy/:adId", requireUser, requireCsrf, async (c) => {
  const adId = Number(c.req.param("adId"));
  const buyer = c.get("user")!.username;

  const ad = await c.env.DB.prepare(
    "SELECT * FROM cash_ads WHERE id = ? AND status = 'OPEN'"
  ).bind(adId).first<any>();
  if (!ad) return c.json({ error: "الإعلان غير متاح" }, 404);
  if (ad.user === buyer) return c.json({ error: "لا يمكنك الشراء من إعلانك" }, 400);

  // Cash trades do NOT lock USDT escrow — funds settle in person.
  const res = await c.env.DB.prepare(
    `INSERT INTO cash_trades (ad_id, buyer, seller, amount, price, status, meeting_location)
     VALUES (?, ?, ?, ?, ?, 'PENDING', ?)`
  ).bind(adId, buyer, ad.user, ad.amount, ad.price, `${ad.city || ""} ${ad.location || ""}`.trim()).run();

  await c.env.DB.prepare("UPDATE cash_ads SET status = 'TRADED' WHERE id = ?").bind(adId).run();

  const tradeId = Number(res.meta.last_row_id);
  await notify(c.env, ad.user, "طلب مقابلة شخصية 🤝",
    `${buyer} يريد شراء ${ad.amount} USDT مقابل كاش. صفقة #${tradeId}.`);
  await auditLog(c, buyer, "user", "CASH_TRADE_CREATE", `cash_trade:${tradeId}`);
  return c.json({ ok: true, trade_id: tradeId });
});

misc.get("/cash/trade/:id", requireUser, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const t = await c.env.DB.prepare(
    `SELECT ct.*, ca.title FROM cash_trades ct LEFT JOIN cash_ads ca ON ct.ad_id = ca.id
     WHERE ct.id = ?`
  ).bind(id).first<any>();
  if (!t) return c.json({ error: "غير موجود" }, 404);
  if (t.buyer !== username && t.seller !== username && !c.get("user")!.isAdmin) {
    return c.json({ error: "غير مصرح" }, 403);
  }
  return c.json({ ok: true, trade: t });
});

misc.post("/cash/trade/:id/confirm-meeting", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const t = await c.env.DB.prepare("SELECT * FROM cash_trades WHERE id = ?").bind(id).first<any>();
  if (!t || (t.buyer !== username && t.seller !== username)) {
    return c.json({ error: "غير مصرح" }, 403);
  }

  const body = await formBody(c);
  const location = String(body.location ?? t.meeting_location ?? "").trim().slice(0, 200);

  await c.env.DB.prepare(
    "UPDATE cash_trades SET meeting_confirmed = 1, meeting_location = ?, status = 'MEETING_SET' WHERE id = ?"
  ).bind(location, id).run();

  const other = username === t.buyer ? t.seller : t.buyer;
  await notify(c.env, other, "تم تأكيد المقابلة ✅",
    `المكان: ${location || "كما اتفقنا"} — صفقة #${id}`);
  return c.json({ ok: true });
});

misc.post("/cash/trade/:id/complete", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const t = await c.env.DB.prepare("SELECT * FROM cash_trades WHERE id = ?").bind(id).first<any>();
  if (!t || (t.buyer !== username && t.seller !== username)) {
    return c.json({ error: "غير مصرح" }, 403);
  }
  if (t.status === "COMPLETED") return c.json({ error: "تم الإتمام بالفعل" }, 400);

  await c.env.DB.prepare(
    "UPDATE cash_trades SET status = 'COMPLETED', completed_at = datetime('now') WHERE id = ?"
  ).bind(id).run();

  const other = username === t.buyer ? t.seller : t.buyer;
  await notify(c.env, other, "اكتملت الصفقة الكاشية ✅", `صفقة #${id} — لا تنسَ التقييم.`);
  await auditLog(c, username, "user", "CASH_TRADE_COMPLETE", `cash_trade:${id}`);
  return c.json({ ok: true });
});

// ============================================================
// Telegram Notification Preferences
// ============================================================
misc.get("/telegram/prefs", requireUser, async (c) => {
  const username = c.get("user")!.username;
  try {
    const prefs = await c.env.DB.prepare(
      "SELECT * FROM telegram_prefs WHERE username = ?"
    ).bind(username).first();
    return c.json({
      ok: true,
      notify_trades: true,
      notify_payments: true,
      notify_disputes: true,
      notify_system: true,
      ...prefs,
    });
  } catch {
    return c.json({ ok: true, notify_trades: true, notify_payments: true, notify_disputes: true, notify_system: true });
  }
});

misc.post("/telegram/prefs", requireUser, requireCsrf, async (c) => {
  const username = c.get("user")!.username;
  const raw: Record<string, unknown> = await c.req.json().catch(() => ({})) as Record<string, unknown>;
  const trades = typeof raw.trades === "boolean" ? raw.trades : undefined;
  const payments = typeof raw.payments === "boolean" ? raw.payments : undefined;
  const disputes = typeof raw.disputes === "boolean" ? raw.disputes : undefined;
  const system = typeof raw.system === "boolean" ? raw.system : undefined;
  try {
    await c.env.DB.prepare(
      `INSERT INTO telegram_prefs (username, notify_trades, notify_payments, notify_disputes, notify_system, updated_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))
       ON CONFLICT(username) DO UPDATE SET
         notify_trades = COALESCE(excluded.notify_trades, telegram_prefs.notify_trades),
         notify_payments = COALESCE(excluded.notify_payments, telegram_prefs.notify_payments),
         notify_disputes = COALESCE(excluded.notify_disputes, telegram_prefs.notify_disputes),
         notify_system = COALESCE(excluded.notify_system, telegram_prefs.notify_system),
         updated_at = datetime('now')`
    ).bind(
      username,
      trades !== undefined ? (trades ? 1 : 0) : 1,
      payments !== undefined ? (payments ? 1 : 0) : 1,
      disputes !== undefined ? (disputes ? 1 : 0) : 1,
      system !== undefined ? (system ? 1 : 0) : 1
    ).run();
    return c.json({ ok: true });
  } catch {
    return c.json({ ok: true });
  }
});

export default misc;
