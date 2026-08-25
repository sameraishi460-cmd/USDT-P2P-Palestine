/**
 * Trade routes — enhanced with formal escrow state machine.
 *
 * Every state transition is:
 *   - Validated against the state machine (server-side only)
 *   - Idempotent (re-executing a completed action is a no-op)
 *   - Ledgered in escrow_transactions
 *   - Audit-logged
 *   - Server-side authorized (never trusts frontend values for amounts/status/user_id)
 *
 * Price is locked at trade creation time and never recalculated.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireUser, requireCsrf, rateLimit } from "../middleware/auth";
import {
  escrowReleaseToBuyer, escrowRefundSeller, notify, auditLog, getWallet,
} from "../utils/db";
import { formBody } from "../utils/body";
import {
  isValidTransition, isValidEscrowTransition,
  recordEscrowTransaction, getEscrowTimeline, hasEscrowAction, getTradeTimeoutMinutes,
} from "../escrow";

const trades = new Hono<AppEnv>();

async function getTrade(c: any, tradeId: number) {
  return c.env.DB.prepare(`
    SELECT t.*, a.title AS ad_title, a.payment AS payment_method
    FROM trades t LEFT JOIN ads a ON t.ad_id = a.id
    WHERE t.id = ?
  `).bind(tradeId).first();
}

function isParticipant(user: string, trade: any): boolean {
  return trade.buyer === user || trade.seller === user;
}

/**
 * Helper: atomically update trade status with state machine validation.
 * Returns { ok, error? } — never partially updates.
 */
async function transitionTradeStatus(
  db: D1Database,
  tradeId: number,
  currentStatus: string,
  newStatus: string,
  escrowNewStatus?: string
): Promise<{ ok: boolean; error?: string }> {
  if (!isValidTransition(currentStatus, newStatus)) {
    return { ok: false, error: `انتقال غير مسموح: ${currentStatus} → ${newStatus}` };
  }

  let sql: string;
  let params: any[];

  if (escrowNewStatus) {
    sql = `UPDATE trades SET status = ?, escrow_status = ?
           WHERE id = ? AND status = ?`;
    params = [newStatus, escrowNewStatus, tradeId, currentStatus];
  } else {
    sql = `UPDATE trades SET status = ?
           WHERE id = ? AND status = ?`;
    params = [newStatus, tradeId, currentStatus];
  }

  const result = await db.prepare(sql).bind(...params).run();
  if (result.meta.changes === 0) {
    return { ok: false, error: "الحالة تغيرت أثناء المعالجة — حاول مرة أخرى" };
  }
  return { ok: true };
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
// GET /api/trades/:id — trade detail with messages + escrow timeline
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

  // Escrow timeline
  const timeline = await getEscrowTimeline(c.env.DB, id);

  // Trade timeout info
  const timeoutMinutes = await getTradeTimeoutMinutes(c.env.DB);
  const createdAt = trade.created ? new Date(trade.created + "Z").getTime() : 0;
  const expiresAt = createdAt ? createdAt + timeoutMinutes * 60 * 1000 : 0;
  const isExpired = expiresAt > 0 && Date.now() > expiresAt;
  const timeRemaining = expiresAt > 0 ? Math.max(0, Math.round((expiresAt - Date.now()) / 1000)) : null;

  return c.json({
    ok: true,
    trade,
    messages: messages.results ?? [],
    timeline,
    timeout: { minutes: timeoutMinutes, expires_at: new Date(expiresAt).toISOString(), is_expired: isExpired, seconds_remaining: timeRemaining },
  });
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

  // Idempotent: if already PAYMENT_SENT, return ok
  if (trade.status === "PAYMENT_SENT") return c.json({ ok: true });
  if (trade.status !== "PENDING") {
    return c.json({ error: `لا يمكن تأكيد الدفع في الحالة الحالية (${trade.status})` }, 400);
  }

  // Atomic transition with state machine validation
  const result = await transitionTradeStatus(c.env.DB, id, "PENDING", "PAYMENT_SENT");
  if (!result.ok) return c.json({ error: result.error }, 400);

  await auditLog(c, username, "user", "PAYMENT_SENT", `trade:${id}`);
  await notify(c.env, trade.seller, "المشتري أبلغ عن الدفع 💳",
    `تحقق من استلام الدفع ثم حرر USDT للصفقة #${id}.`);
  return c.json({ ok: true });
});

// ============================================================
// POST /api/trades/:id/upload-proof — payment proof upload metadata
// ============================================================
trades.post("/:id/upload-proof", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade || !isParticipant(username, trade)) return c.json({ error: "غير مصرح" }, 403);
  if (username !== trade.buyer) return c.json({ error: "المشتري فقط يرفع إثبات الدفع" }, 403);

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
// POST /api/trades/:id/seller-confirm — seller releases USDT
// ============================================================
trades.post("/:id/seller-confirm", requireUser, requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const username = c.get("user")!.username;
  const trade = await getTrade(c, id);
  if (!trade || !isParticipant(username, trade)) return c.json({ error: "غير مصرح" }, 403);
  if (username !== trade.seller) return c.json({ error: "البائع فقط يحرر USDT" }, 403);

  // Idempotent: if already COMPLETED, return ok
  if (trade.status === "COMPLETED") return c.json({ ok: true });

  // State machine: only PAYMENT_SENT → COMPLETED is valid
  if (trade.status === "DISPUTED") {
    return c.json({ error: "الصفقة تحت نزاع — الإدارة تقرر" }, 400);
  }
  if (trade.status !== "PAYMENT_SENT") {
    return c.json({ error: `يجب أن يأكد المشتري الدفع أولاً (الحالة: ${trade.status})` }, 400);
  }

  // Idempotency: check if already released
  const alreadyReleased = await hasEscrowAction(c.env.DB, id, "RELEASE");
  if (alreadyReleased) return c.json({ ok: true });

  // Escrow release
  if (trade.escrow_status === "LOCKED") {
    const release = await escrowReleaseToBuyer(c.env, trade.seller, trade.buyer, trade.amount, id);
    if (!release.ok) return c.json({ error: release.reason }, 400);

    // Record in escrow ledger
    await recordEscrowTransaction(c.env.DB, id, trade.seller, trade.amount, "RELEASE", {
      reason: "تأكيد استلام الدفع من البائع",
    });
  }

  // State machine transition
  const result = await transitionTradeStatus(c.env.DB, id, "PAYMENT_SENT", "COMPLETED",
    trade.escrow_status === "LOCKED" ? "RELEASED" : undefined);
  if (!result.ok) return c.json({ error: result.error }, 400);

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

  // Idempotent: if already CANCELLED, return ok
  if (trade.status === "CANCELLED") return c.json({ ok: true });

  // Only PENDING trades can be cancelled by users
  if (trade.status === "DISPUTED") {
    return c.json({ error: "الصفقة تحت نزاع — لا يمكن الإلغاء" }, 400);
  }
  if (trade.status !== "PENDING") {
    return c.json({ error: "لا يمكن إلغاء صفقة بعد تأكيد الدفع. استخدم فتح نزاع." }, 400);
  }

  // Idempotency: check if already refunded
  const alreadyRefunded = await hasEscrowAction(c.env.DB, id, "REFUND");

  // Refund locked funds if not already done
  if (trade.escrow_status === "LOCKED" && !alreadyRefunded) {
    const refund = await escrowRefundSeller(c.env, trade.seller, trade.amount, id);
    if (!refund.ok) return c.json({ error: refund.reason }, 400);

    // Record in escrow ledger
    await recordEscrowTransaction(c.env.DB, id, trade.seller, trade.amount, "REFUND", {
      reason: "إلغاء الصفقة قبل الدفع",
    });
  }

  // State machine transition
  const result = await transitionTradeStatus(c.env.DB, id, "PENDING", "CANCELLED",
    trade.escrow_status === "LOCKED" ? "REFUNDED" : undefined);
  if (!result.ok) return c.json({ error: result.error }, 400);

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

  // Only PAYMENT_SENT trades can be disputed
  if (trade.status === "DISPUTED") return c.json({ ok: true }); // idempotent
  if (trade.status !== "PAYMENT_SENT") {
    return c.json({ error: `لا يمكن فتح نزاع قبل تأكيد الدفع (الحالة: ${trade.status})` }, 400);
  }

  const body = await formBody(c);
  const reason = String(body.reason ?? "").trim().slice(0, 500);
  if (reason.length < 10) {
    return c.json({ error: "سبب النزاع مطلوب (10 أحرف على الأقل)" }, 400);
  }

  // State machine transition
  const result = await transitionTradeStatus(c.env.DB, id, "PAYMENT_SENT", "DISPUTED", "DISPUTED");
  if (!result.ok) return c.json({ error: result.error }, 400);

  await c.env.DB.prepare(
    "INSERT INTO disputes (trade_id, opened_by, reason) VALUES (?, ?, ?)"
  ).bind(id, username, reason).run();

  await notify(c.env, trade.buyer === username ? trade.seller : trade.buyer,
    "نزاع على الصفقة ⚠️", `تم فتح نزاع على الصفقة #${id}. ستراجع الإدارة الحالة.`);
  await auditLog(c, username, "user", "DISPUTE_OPEN", `trade:${id}`, reason.slice(0, 120));
  return c.json({ ok: true });
});

export default trades;
