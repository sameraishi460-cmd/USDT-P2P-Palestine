/**
 * Trade routes: detail, chat, payment confirmation, seller confirm (release),
 * cancel, dispute. Escrow/release logic mirrors the existing Flask app:
 * - Buyer uploads payment proof + confirms payment
 * - Seller verifies and confirms release → escrow released to buyer
 * - Disputes freeze the trade until admin resolves
 * - Double-release / double-cancel protected by status checks
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireUser, requireCsrf, rateLimit } from "../middleware/auth";
import { escrowReleaseToBuyer, escrowRefundSeller, notify, auditLog } from "../utils/db";
import { formBody } from "../utils/body";

const trades = new Hono<AppEnv>();

async function getTrade(c: any, tradeId: number) {
  return c.env.DB.prepare(`
    SELECT t.*, a.title AS ad_title
    FROM trades t LEFT JOIN ads a ON t.ad_id = a.id
    WHERE t.id = ?
  `).bind(tradeId).first();
}

function isParticipant(user: string, trade: any): boolean {
  return trade.buyer === user || trade.seller === user;
}

// ============================================================
// GET /api/trades — my trades list
// ============================================================
trades.get("/", requireUser, async (c) => {
  const username = c.get("user")!.username;
  const rows = await c.env.DB.prepare(
    `SELECT * FROM trades WHERE buyer = ? OR seller = ? ORDER BY id DESC LIMIT 100`
  ).bind(username, username).all();
  return c.json({ ok: true, trades: rows.results ?? [] });
});

// ============================================================
// GET /api/trades/:id — trade detail with messages
// ============================================================
trades.get("/:id", requireUser, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade) return c.json({ error: "الصفقة غير موجودة" }, 404);
  if (!isParticipant(username, trade) && !c.get("user")!.isAdmin) {
    return c.json({ error: "غير مصرح" }, 403);
  }
  const messages = await c.env.DB.prepare(
    "SELECT id, sender, receiver, text, created FROM messages WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?) ORDER BY id ASC LIMIT 200"
  ).bind(trade.buyer, trade.seller, trade.seller, trade.buyer).all();
  return c.json({ ok: true, trade, messages: messages.results ?? [] });
});

// ============================================================
// POST /api/trades/:id/message — chat
// ============================================================
trades.post("/:id/message", requireUser, requireCsrf, rateLimit(30, 60), async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade || !isParticipant(username, trade)) {
    return c.json({ error: "غير مصرح" }, 403);
  }
  if (["COMPLETED", "CANCELLED"].includes(trade.status)) {
    return c.json({ error: "لا يمكن إرسال رسائل في صفقة منتهية" }, 400);
  }

  const body = await formBody(c);
  const text = String(body.text ?? "").trim().slice(0, 1000);
  if (!text) return c.json({ error: "الرسالة فارغة" }, 400);

  const receiver = username === trade.buyer ? trade.seller : trade.buyer;
  await c.env.DB.prepare(
    "INSERT INTO messages (sender, receiver, text) VALUES (?, ?, ?)"
  ).bind(username, receiver, text).run();

  await notify(c.env, receiver, "رسالة جديدة 💬",
    `${username}: ${text.slice(0, 80)}${text.length > 80 ? "…" : ""} (صفقة #${id})`);
  return c.json({ ok: true });
});

// ============================================================
// POST /api/trades/:id/confirm-payment — buyer confirms payment sent
// ============================================================
trades.post("/:id/confirm-payment", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade || !isParticipant(username, trade)) return c.json({ error: "غير مصرح" }, 403);
  if (username !== trade.buyer) return c.json({ error: "المشتري فقط يؤكد الدفع" }, 403);
  if (trade.status !== "PENDING") {
    return c.json({ error: `لا يمكن تأكيد الدفع في الحالة الحالية (${trade.status})` }, 400);
  }

  await c.env.DB.prepare(
    "UPDATE trades SET status = 'PAYMENT_SENT' WHERE id = ? AND status = 'PENDING'"
  ).bind(id).run();

  await notify(c.env, trade.seller, "المشتري أكد الدفع ✅",
    `تأكد من استلام الدفع ثم حرر USDT للصفقة #${id}.`);
  await auditLog(c, username, "user", "PAYMENT_CONFIRMED", `trade:${id}`);
  return c.json({ ok: true });
});

// ============================================================
// POST /api/trades/:id/upload-proof — payment proof upload metadata (R2 key)
// ============================================================
trades.post("/:id/upload-proof", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade || !isParticipant(username, trade)) return c.json({ error: "غير مصرح" }, 403);
  if (username !== trade.buyer) return c.json({ error: "المشتري فقط يرفع إثبات الدفع" }, 403);

  // The actual file upload goes through POST /api/uploads/payment-proof
  // which returns an R2 object key; we store it here.
  const body = await formBody(c);
  const proofKey = String(body.proof_key ?? "").trim();
  if (!proofKey || !proofKey.startsWith("payment-proofs/")) {
    return c.json({ error: "مفتاح الملف غير صالح" }, 400);
  }

  await c.env.DB.prepare(
    "UPDATE trades SET payment_proof = ? WHERE id = ?"
  ).bind(proofKey, id).run();
  await auditLog(c, username, "user", "PROOF_UPLOAD", `trade:${id}`, proofKey);
  return c.json({ ok: true });
});

// ============================================================
// POST /api/trades/:id/seller-confirm — seller releases escrow
// ============================================================
trades.post("/:id/seller-confirm", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade || !isParticipant(username, trade)) return c.json({ error: "غير مصرح" }, 403);
  if (username !== trade.seller) return c.json({ error: "البائع فقط يحرر USDT" }, 403);
  if (trade.status === "DISPUTED") {
    return c.json({ error: "الصفقة تحت نزاع — الإدارة تقرر" }, 400);
  }
  if (trade.status !== "PAYMENT_SENT") {
    return c.json({ error: `يجب أن يأكد المشتري الدفع أولاً (الحالة: ${trade.status})` }, 400);
  }

  // Atomic double-release-protected escrow release
  const release = await escrowReleaseToBuyer(c.env, trade.seller, trade.buyer, trade.amount, id);
  if (!release.ok) return c.json({ error: release.reason }, 400);

  await c.env.DB.prepare(
    `UPDATE trades SET status = 'COMPLETED', escrow_status = 'RELEASED', completed_at = datetime('now')
     WHERE id = ? AND status != 'COMPLETED'`
  ).bind(id).run();

  await notify(c.env, trade.buyer, "تم تحرير USDT 🎉",
    `استلمت ${trade.amount} USDT من الصفقة #${id}. يمكنك الآن تقييم البائع.`);
  await notify(c.env, trade.seller, "تم إتمام الصفقة ✅",
    `تم تحرير USDT للمشتري في الصفقة #${id}.`);

  await auditLog(c, username, "user", "ESCROW_RELEASE", `trade:${id}`, `${trade.amount} USDT`);
  return c.json({ ok: true });
});

// ============================================================
// POST /api/trades/:id/cancel — cancel when allowed
// ============================================================
trades.post("/:id/cancel", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade || !isParticipant(username, trade)) return c.json({ error: "غير مصرح" }, 403);
  if (!["PENDING", "PAYMENT_SENT"].includes(trade.status)) {
    return c.json({ error: `لا يمكن إلغاء صفقة بحالة ${trade.status}` }, 400);
  }

  // Refund locked funds to seller if they were locked
  if (trade.escrow_status === "LOCKED") {
    const refund = await escrowRefundSeller(c.env, trade.seller, trade.amount, id);
    if (!refund.ok) return c.json({ error: refund.reason }, 400);
  }

  await c.env.DB.prepare(
    `UPDATE trades SET status = 'CANCELLED', escrow_status = CASE WHEN escrow_status='LOCKED' THEN 'REFUNDED' ELSE 'CANCELLED' END
     WHERE id = ? AND status IN ('PENDING','PAYMENT_SENT')`
  ).bind(id).run();

  // Restore ad amount
  await c.env.DB.prepare(
    "UPDATE ads SET amount = amount + ?, status = 'OPEN' WHERE id = ?"
  ).bind(trade.amount, trade.ad_id).run();

  const other = username === trade.buyer ? trade.seller : trade.buyer;
  await notify(c.env, other, "تم إلغاء الصفقة ⚠️", `قام ${username} بإلغاء الصفقة #${id}.`);
  await auditLog(c, username, "user", "TRADE_CANCEL", `trade:${id}`);
  return c.json({ ok: true });
});

// ============================================================
// POST /api/trades/:id/dispute — open dispute (freezes trade)
// ============================================================
trades.post("/:id/dispute", requireUser, requireCsrf, rateLimit(5, 300), async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade || !isParticipant(username, trade)) return c.json({ error: "غير مصرح" }, 403);
  if (!["PAYMENT_SENT", "PENDING"].includes(trade.status)) {
    return c.json({ error: `لا يمكن فتح نزاع في هذه الحالة (${trade.status})` }, 400);
  }

  const body = await formBody(c);
  const reason = String(body.reason ?? "").trim().slice(0, 500);
  if (reason.length < 10) {
    return c.json({ error: "سبب النزاع مطلوب (10 أحرف على الأقل)" }, 400);
  }

  await c.env.DB.batch([
    c.env.DB.prepare(
      "UPDATE trades SET status = 'DISPUTED', dispute_status = 'OPEN', dispute_reason = ?, dispute_by = ? WHERE id = ?"
    ).bind(reason, username, id),
    c.env.DB.prepare(
      "INSERT INTO disputes (trade_id, opened_by, reason) VALUES (?, ?, ?)"
    ).bind(id, username, reason),
  ]);

  await notify(c.env, trade.buyer === username ? trade.seller : trade.buyer,
    "نزاع على الصفقة ⚠️", `تم فتح نزاع على الصفقة #${id}. ستراجع الإدارة الحالة.`);
  await auditLog(c, username, "user", "DISPUTE_OPEN", `trade:${id}`, reason.slice(0, 120));
  return c.json({ ok: true });
});

export default trades;
