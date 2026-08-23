/**
 * Admin routes. ALL protected by requireAdmin middleware which
 * verifies the user's ADMIN status server-side on every request.
 * Every admin financial action is written to the audit log.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireAdmin, requireCsrf } from "../middleware/auth";
import {
  modifyBalance, escrowReleaseToBuyer, escrowRefundSeller,
  notify, auditLog, getConfig, setConfig,
} from "../utils/db";
import { formBody } from "../utils/body";
import { isValidBscAddress, isValidTxHash, checkUsdtTransaction } from "../blockchain/usdt";

const admin = new Hono<AppEnv>();

// All routes below require verified ADMIN status (server-side)
admin.use("*", async (c, next) => {
  // Inline auth to avoid double-import cycles; same logic as requireAdmin
  const { getCookie } = await import("../middleware/auth");
  const { verifySession } = await import("../utils/crypto");
  const token = getCookie(c, "usdt_session");
  if (!token) return c.json({ error: "غير مصرح" }, 401);
  const session = await verifySession(token, c.env.SECRET_KEY);
  if (!session) return c.json({ error: "انتهت الجلسة" }, 401);
  const user = await c.env.DB.prepare("SELECT id, username, status FROM users WHERE id = ?")
    .bind(session.sub).first<{ id: number; username: string; status: string }>();
  if (!user || user.status !== "ADMIN") return c.json({ error: "غير مصرح لك بالوصول" }, 403);
  c.set("user", { id: user.id, username: user.username, isAdmin: true });
  await next();
});

// ============================================================
// GET /api/admin — KPIs
// ============================================================
admin.get("/", async (c) => {
  const db = c.env.DB;
  const [users, activeUsers, trades, completedTrades, activeTrades,
    volume, fees, pendingDeposits, pendingWithdrawals, openDisputes] = await Promise.all([
    db.prepare("SELECT COUNT(*) FROM users").first<number>(),
    db.prepare("SELECT COUNT(*) FROM users WHERE status='ACTIVE'").first<number>(),
    db.prepare("SELECT COUNT(*) FROM trades").first<number>(),
    db.prepare("SELECT COUNT(*) FROM trades WHERE status='COMPLETED'").first<number>(),
    db.prepare("SELECT COUNT(*) FROM trades WHERE status IN ('PENDING','PAYMENT_SENT','DISPUTED')").first<number>(),
    db.prepare("SELECT COALESCE(SUM(amount),0) FROM trades WHERE status='COMPLETED'").first<number>(),
    db.prepare("SELECT COALESCE(SUM(platform_fee),0) FROM trades WHERE status='COMPLETED'").first<number>(),
    db.prepare("SELECT COUNT(*) FROM usdt_deposits WHERE status='PENDING'").first<number>(),
    db.prepare("SELECT COUNT(*) FROM withdraw_requests WHERE status='PENDING'").first<number>(),
    db.prepare("SELECT COUNT(*) FROM trades WHERE status='DISPUTED'").first<number>(),
  ]);

  return c.json({
    ok: true,
    kpis: {
      total_users: users, active_users: activeUsers,
      total_trades: trades, completed_trades: completedTrades,
      active_trades: activeTrades, total_volume: volume,
      platform_fees: fees, pending_deposits: pendingDeposits,
      pending_withdrawals: pendingWithdrawals, open_disputes: openDisputes,
    },
  });
});

// ============================================================
// Users management
// ============================================================
admin.get("/users", async (c) => {
  const rows = await c.env.DB.prepare(
    `SELECT u.id, u.username, u.status, u.verified, u.rating, u.trades_count,
            u.telegram_id, w.balance, w.locked
     FROM users u LEFT JOIN wallets w ON u.username = w.username
     ORDER BY u.id DESC LIMIT 200`
  ).all();
  return c.json({ ok: true, users: rows.results ?? [] });
});

admin.post("/users/:username/ban", requireCsrf, async (c) => {
  const username = c.req.param("username");
  await c.env.DB.prepare("UPDATE users SET status='BANNED' WHERE username=?").bind(username).run();
  await auditLog(c, c.get("user")!.username, "admin", "BAN_USER", username);
  return c.json({ ok: true });
});

admin.post("/users/:username/unban", requireCsrf, async (c) => {
  const username = c.req.param("username");
  await c.env.DB.prepare("UPDATE users SET status='ACTIVE' WHERE username=? AND status != 'ADMIN'").bind(username).run();
  await auditLog(c, c.get("user")!.username, "admin", "UNBAN_USER", username);
  return c.json({ ok: true });
});

admin.post("/users/:username/verify", requireCsrf, async (c) => {
  const username = c.req.param("username") ?? "";
  await c.env.DB.prepare("UPDATE users SET verified=1 WHERE username=?").bind(username).run();
  await notify(c.env, username, "تم توثيق حسابك ✅", "أصبحت الآن تاجراً موثقاً.");
  await auditLog(c, c.get("user")!.username, "admin", "VERIFY_USER", username);
  return c.json({ ok: true });
});

admin.post("/credit", requireCsrf, async (c) => {
  const body = await formBody(c);
  const username = String(body.username ?? "").trim();
  const amount = parseFloat(String(body.amount ?? ""));

  if (!username || !(amount > 0)) return c.json({ error: "بيانات غير صحيحة" }, 400);

  const { ensureWallet } = await import("../utils/db");
  await ensureWallet(c.env, username);
  const res = await modifyBalance(c.env, username, amount, "ADMIN_CREDIT",
    { note: `تعديل إداري بواسطة ${c.get("user")!.username}` });
  if (!res.ok) return c.json({ error: res.reason }, 400);

  await notify(c.env, username, "تم تعديل رصيدك", `تمت إضافة ${amount} USDT من الإدارة.`);
  await auditLog(c, c.get("user")!.username, "admin", "CREDIT_USER", username, String(amount));
  return c.json({ ok: true, new_balance: res.newBalance });
});

// ============================================================
// Deposits (manual confirm/reject for legacy flow)
// ============================================================
admin.get("/deposits", async (c) => {
  const rows = await c.env.DB.prepare(
    "SELECT * FROM usdt_deposits ORDER BY id DESC LIMIT 100"
  ).all();
  return c.json({ ok: true, deposits: rows.results ?? [] });
});

admin.post("/deposits/:id/confirm", requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const dep = await c.env.DB.prepare(
    "SELECT * FROM usdt_deposits WHERE id=? AND status='PENDING'"
  ).bind(id).first<any>();
  if (!dep) return c.json({ error: "الإيداع غير موجود أو تمت معالجته" }, 404);

  const credit = await modifyBalance(c.env, dep.username, dep.amount, "DEPOSIT",
    { refId: id, note: `إيداع مؤكد إدارياً #${id}` });
  if (!credit.ok) return c.json({ error: credit.reason }, 400);

  await c.env.DB.prepare(
    "UPDATE usdt_deposits SET status='CONFIRMED', confirmed_at=datetime('now') WHERE id=?"
  ).bind(id).run();
  await notify(c.env, dep.username, "تم تأكيد الإيداع ✅", `${dep.amount} USDT.`);
  await auditLog(c, c.get("user")!.username, "admin", "DEPOSIT_CONFIRM", `dep:${id}`, String(dep.amount));
  return c.json({ ok: true });
});

admin.post("/deposits/:id/reject", requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const dep = await c.env.DB.prepare(
    "SELECT * FROM usdt_deposits WHERE id=? AND status='PENDING'"
  ).bind(id).first<any>();
  if (!dep) return c.json({ error: "غير موجود أو تمت معالجته" }, 404);

  await c.env.DB.prepare("UPDATE usdt_deposits SET status='REJECTED' WHERE id=?").bind(id).run();
  await notify(c.env, dep.username, "تم رفض الإيداع ❌", `لم يتم التحقق من المعاملة #${dep.tx_hash.slice(0, 16)}…`);
  await auditLog(c, c.get("user")!.username, "admin", "DEPOSIT_REJECT", `dep:${id}`);
  return c.json({ ok: true });
});

// ============================================================
// Withdrawals
// ============================================================
admin.get("/withdrawals", async (c) => {
  const rows = await c.env.DB.prepare(
    "SELECT * FROM withdraw_requests ORDER BY id DESC LIMIT 100"
  ).all();
  return c.json({ ok: true, withdrawals: rows.results ?? [] });
});

admin.post("/withdrawals/:id/approve", requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const body = await formBody(c);
  const txHash = String(body.tx_hash ?? "").trim();

  const req_ = await c.env.DB.prepare(
    "SELECT * FROM withdraw_requests WHERE id=? AND status='PENDING'"
  ).bind(id).first<any>();
  if (!req_) return c.json({ error: "طلب السحب غير موجود أو تمت معالجته" }, 404);

  // Deduct from locked (already locked at request time)
  const walletRow = await c.env.DB.prepare(
    "SELECT locked FROM wallets WHERE username=?"
  ).bind(req_.username).first<{ locked: number }>();
  if ((walletRow?.locked ?? 0) < req_.amount - 0.001) {
    return c.json({ error: "الأموال المقفلة غير كافية" }, 400);
  }

  await c.env.DB.batch([
    c.env.DB.prepare("UPDATE wallets SET locked = MAX(locked - ?, 0) WHERE username=?").bind(req_.amount, req_.username),
    c.env.DB.prepare(
      `INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, reference_id, note)
       SELECT username, 'WITHDRAWAL', ?, locked, locked - ?, ?, 'سحب معتمد إدارياً'
       FROM wallets WHERE username=?`
    ).bind(req_.amount, req_.amount, id, req_.username),
    c.env.DB.prepare(
      "UPDATE withdraw_requests SET status=?, tx_hash=?, processed_at=datetime('now') WHERE id=?"
    ).bind(txHash && isValidTxHash(txHash) ? "COMPLETED" : "PROCESSING",
          isValidTxHash(txHash) ? txHash.toLowerCase() : "", id),
  ]);

  await notify(c.env, req_.username, "تم اعتماد السحب ✅", `${req_.amount} USDT قيد التحويل إلى محفظتك.`);
  await auditLog(c, c.get("user")!.username, "admin", "WITHDRAW_APPROVE", `wd:${id}`, String(req_.amount));
  return c.json({ ok: true });
});

admin.post("/withdrawals/:id/reject", requireCsrf, async (c) => {
  const id = Number(c.req.param("id"));
  const req_ = await c.env.DB.prepare(
    "SELECT * FROM withdraw_requests WHERE id=? AND status='PENDING'"
  ).bind(id).first<any>();
  if (!req_) return c.json({ error: "غير موجود أو تمت معالجته" }, 404);

  // Atomic refund of the locked amount
  const refund = await modifyBalance(c.env, req_.username, req_.amount, "REFUND",
    { refId: id, note: "إرجاع مبلغ سحب مرفوض" });

  await c.env.DB.prepare("UPDATE wallets SET locked = MAX(locked - ?, 0) WHERE username=?")
    .bind(req_.amount, req_.username).run();

  await c.env.DB.prepare("UPDATE withdraw_requests SET status='REJECTED', processed_at=datetime('now') WHERE id=?").bind(id).run();

  if (!refund.ok) return c.json({ error: refund.reason }, 500);
  await notify(c.env, req_.username, "تم رفض طلب السحب ❌", `أُعيد ${req_.amount} USDT إلى رصيدك.`);
  await auditLog(c, c.get("user")!.username, "admin", "WITHDRAW_REJECT", `wd:${id}`, String(req_.amount));
  return c.json({ ok: true });
});

// ============================================================
// Disputes
// ============================================================
admin.get("/disputes", async (c) => {
  const rows = await c.env.DB.prepare(
    `SELECT d.*, t.buyer, t.seller, t.amount, t.status AS trade_status
     FROM disputes d LEFT JOIN trades t ON d.trade_id = t.id
     WHERE d.status IN ('OPEN','UNDER_REVIEW')
     ORDER BY d.id DESC LIMIT 50`
  ).all();
  return c.json({ ok: true, disputes: rows.results ?? [] });
});

admin.post("/disputes/:tradeId/resolve", requireCsrf, async (c) => {
  const tradeId = Number(c.req.param("tradeId"));
  const body = await formBody(c);
  const action = String(body.action ?? ""); // release | refund
  const note = String(body.note ?? "").slice(0, 300);

  const trade = await c.env.DB.prepare("SELECT * FROM trades WHERE id=? AND status='DISPUTED'")
    .bind(tradeId).first<any>();
  if (!trade) return c.json({ error: "الصفقة غير موجودة أو ليست في نزاع" }, 404);

  if (action === "release") {
    const r = await escrowReleaseToBuyer(c.env, trade.seller, trade.buyer, trade.amount, tradeId);
    if (!r.ok) return c.json({ error: r.reason }, 400);
    await c.env.DB.prepare(
      `UPDATE trades SET status='COMPLETED', escrow_status='RELEASED', dispute_status='RESOLVED',
       dispute_by=dispute_by, completed_at=datetime('now') WHERE id=?`
    ).bind(tradeId).run();
    await notify(c.env, trade.buyer, "قرار النزاع ⚖️", `تم تحرير USDT لك (صفقة #${tradeId}).`);
    await notify(c.env, trade.seller, "قرار النزاع ⚖️", `تم تحرير USDT للمشتري (صفقة #${tradeId}).`);
  } else if (action === "refund") {
    const r = await escrowRefundSeller(c.env, trade.seller, trade.amount, tradeId);
    if (!r.ok) return c.json({ error: r.reason }, 400);
    await c.env.DB.prepare(
      `UPDATE trades SET status='CANCELLED', escrow_status='REFUNDED', dispute_status='RESOLVED' WHERE id=?`
    ).bind(tradeId).run();
    await notify(c.env, trade.seller, "قرار النزاع ⚖️", `أُرجع USDT إليك (صفقة #${tradeId}).`);
    await notify(c.env, trade.buyer, "قرار النزاع ⚖️", `تم إلغاء الصفقة وإرجاع الأموال للبائع (#${tradeId}).`);
  } else {
    return c.json({ error: "action يجب أن يكون release أو refund" }, 400);
  }

  await c.env.DB.prepare(
    `UPDATE disputes SET status='RESOLVED', admin_decision=?, admin_note=?, resolved_at=datetime('now')
     WHERE trade_id=? AND status IN ('OPEN','UNDER_REVIEW')`
  ).bind(action.toUpperCase(), note || "-", tradeId).run();

  await auditLog(c, c.get("user")!.username, "admin", "DISPUTE_RESOLVE", `trade:${tradeId}`,
    `${action} ${note.slice(0, 80)}`);
  return c.json({ ok: true });
});

// ============================================================
// Market price + commission config
// ============================================================
admin.get("/price", async (c) => {
  const price = await c.env.DB.prepare("SELECT * FROM market_price WHERE id=1").first();
  return c.json({ ok: true, price });
});

admin.post("/price", requireCsrf, async (c) => {
  const body = await formBody(c);
  const usd = parseFloat(String(body.usd_ils ?? ""));
  const usdt = parseFloat(String(body.usdt_ils ?? ""));
  if (!(usd > 0) || !(usdt > 0)) return c.json({ error: "أسعار غير صالحة" }, 400);

  await c.env.DB.prepare(
    "UPDATE market_price SET usd_ils=?, usdt_ils=?, updated=datetime('now') WHERE id=1"
  ).bind(usd, usdt).run();
  await auditLog(c, c.get("user")!.username, "admin", "PRICE_UPDATE", "market_price", `${usd}/${usdt}`);
  return c.json({ ok: true });
});

admin.get("/commission", async (c) => {
  const cfg = {
    p2p_fee_percent: await getConfig(c.env, "p2p_fee_percent", "1.0"),
    cash_fee_percent: await getConfig(c.env, "cash_fee_percent", "1.0"),
    min_fee: await getConfig(c.env, "min_fee", "0.1"),
    max_fee: await getConfig(c.env, "max_fee", "100.0"),
  };
  const totalFees = await c.env.DB.prepare(
    "SELECT COALESCE(SUM(platform_fee),0) FROM trades WHERE status='COMPLETED'"
  ).first<number>();
  return c.json({ ok: true, config: cfg, total_fees: totalFees });
});

admin.post("/commission", requireCsrf, async (c) => {
  const body = await formBody(c);
  const keys = ["p2p_fee_percent", "cash_fee_percent", "min_fee", "max_fee"];
  for (const key of keys) {
    const val = parseFloat(String(body[key] ?? ""));
    if (!Number.isFinite(val) || val < 0) return c.json({ error: `قيمة غير صالحة: ${key}` }, 400);
    await setConfig(c.env, key, String(val));
  }
  await auditLog(c, c.get("user")!.username, "admin", "COMMISSION_UPDATE", "platform_config");
  return c.json({ ok: true });
});

// ============================================================
// Wallets view + search + cash ads + audit logs
// ============================================================
admin.get("/wallets", async (c) => {
  const rows = await c.env.DB.prepare(
    `SELECT w.*, u.verified FROM wallets w JOIN users u ON w.username=u.username
     ORDER BY w.balance DESC LIMIT 200`
  ).all();
  return c.json({ ok: true, wallets: rows.results ?? [] });
});

admin.post("/search", async (c) => {
  const body = await formBody(c);
  const q = String(body.q ?? "").trim();
  if (!q) return c.json({ ok: true, results: {} });

  const like = `%${q}%`;
  const [users, trades_, deposits] = await Promise.all([
    c.env.DB.prepare("SELECT id, username, status, telegram_id FROM users WHERE username LIKE ? OR telegram_id LIKE ? LIMIT 20").bind(like, like).all(),
    c.env.DB.prepare("SELECT id, buyer, seller, amount, status FROM trades WHERE buyer LIKE ? OR seller LIKE ? LIMIT 20").bind(like, like).all(),
    c.env.DB.prepare("SELECT id, username, amount, tx_hash, status FROM usdt_deposits WHERE username LIKE ? OR tx_hash LIKE ? LIMIT 20").bind(like, like).all(),
  ]);

  return c.json({
    ok: true,
    results: { users: users.results, trades: trades_.results, deposits: deposits.results },
  });
});

admin.get("/cash-ads", async (c) => {
  const rows = await c.env.DB.prepare("SELECT * FROM cash_ads ORDER BY id DESC LIMIT 100").all();
  return c.json({ ok: true, cash_ads: rows.results ?? [] });
});

admin.get("/audit-log", async (c) => {
  const rows = await c.env.DB.prepare(
    "SELECT * FROM audit_log ORDER BY id DESC LIMIT 200"
  ).all();
  return c.json({ ok: true, logs: rows.results ?? [] });
});

export default admin;
