/**
 * Wallet routes: balance, wallet address, deposits (BSC-verified),
 * withdrawals (lock → admin approve/reject), history.
 *
 * FINANCIAL SAFETY:
 * - Deposits verified on-chain via Transfer event; UNIQUE(tx_hash) prevents replay.
 * - Withdrawals lock funds atomically at request time.
 * - Every movement writes a ledger entry.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireUser, requireCsrf, rateLimit } from "../middleware/auth";
import {
  ensureWallet, getWallet, modifyBalance, lockForWithdrawal,
  notify, auditLog, getConfig,
} from "../utils/db";
import { checkUsdtTransaction, isValidBscAddress, isValidTxHash } from "../blockchain/usdt";
import { formBody } from "../utils/body";

const wallet = new Hono<AppEnv>();

// ============================================================
// GET /api/wallet — balance + address
// ============================================================
wallet.get("/", requireUser, async (c) => {
  const username = c.get("user")!.username;
  await ensureWallet(c.env, username);
  const w = await getWallet(c.env, username);
  const user = await c.env.DB.prepare(
    "SELECT usdt_wallet FROM users WHERE username = ?"
  ).bind(username).first<{ usdt_wallet: string }>();

  return c.json({
    ok: true,
    balance: w?.balance ?? 0,
    locked: w?.locked ?? 0,
    total: Math.round(((w?.balance ?? 0) + (w?.locked ?? 0)) * 100) / 100,
    usdt_wallet: user?.usdt_wallet ?? "",
    deposit_address: c.env.PLATFORM_WALLET,
    network: "BNB Smart Chain (BEP-20)",
    contract: c.env.USDT_CONTRACT,
  });
});

// ============================================================
// POST /api/wallet/save-address
// ============================================================
wallet.post("/save-address", requireUser, requireCsrf, async (c) => {
  const username = c.get("user")!.username;
  const body = await formBody(c);
  const addr = String(body.wallet ?? "").trim();

  if (!isValidBscAddress(addr)) {
    return c.json({ error: "عنوان محفظة BEP-20 غير صالح" }, 400);
  }
  await c.env.DB.prepare(
    "UPDATE users SET usdt_wallet = ? WHERE username = ?"
  ).bind(addr, username).run();
  await auditLog(c, username, "user", "WALLET_SAVE", username, addr);
  return c.json({ ok: true });
});

// ============================================================
// GET /api/wallet/history
// ============================================================
wallet.get("/history", requireUser, async (c) => {
  const username = c.get("user")!.username;
  const rows = await c.env.DB.prepare(
    "SELECT id, action, amount, balance_before, balance_after, reference_id, note, created FROM wallet_history WHERE username = ? ORDER BY id DESC LIMIT 100"
  ).bind(username).all();
  return c.json({ ok: true, history: rows.results ?? [] });
});

// ============================================================
// GET /api/wallet/deposit-info — deposit page data
// ============================================================
wallet.get("/deposit-info", requireUser, async (c) => {
  const username = c.get("user")!.username;
  const deposits = await c.env.DB.prepare(
    "SELECT id, amount, tx_hash, status, created, confirmed_at FROM usdt_deposits WHERE username = ? ORDER BY id DESC LIMIT 20"
  ).bind(username).all();
  return c.json({
    ok: true,
    deposit_address: c.env.PLATFORM_WALLET,
    network: "BNB Smart Chain (BEP-20)",
    contract: c.env.USDT_CONTRACT,
    deposits: deposits.results ?? [],
  });
});

// ============================================================
// POST /api/wallet/deposit — submit deposit for on-chain verification
// ============================================================
wallet.post("/deposit", requireUser, requireCsrf, rateLimit(5, 600), async (c) => {
  const username = c.get("user")!.username;
  const body = await formBody(c);

  const amount = parseFloat(String(body.amount ?? ""));
  const txHash = String(body.tx_hash ?? "").trim();
  const senderWallet = String(body.sender_wallet ?? "").trim();

  if (!(amount > 0)) return c.json({ error: "المبلغ يجب أن يكون أكبر من صفر" }, 400);
  if (!isValidTxHash(txHash)) return c.json({ error: "Transaction hash غير صالح" }, 400);

  // Replay protection: same tx_hash can never be credited twice
  const existing = await c.env.DB.prepare(
    "SELECT id, status FROM usdt_deposits WHERE tx_hash = ?"
  ).bind(txHash.toLowerCase()).first<any>();
  if (existing) {
    return c.json({
      error: existing.status === "CONFIRMED"
        ? "هذه المعاملة تم استخدامها مسبقاً"
        : "هذه المعاملة قيد المراجعة بالفعل",
    }, 409);
  }

  // On-chain verification (server-side only)
  const check = await checkUsdtTransaction(c.env, txHash, amount);
  if (!check.verified) {
    // Record as rejected for audit trail
    await c.env.DB.prepare(
      `INSERT INTO usdt_deposits (username, amount, tx_hash, status, sender_wallet) VALUES (?, ?, ?, 'REJECTED', ?)`
    ).bind(username, amount, txHash.toLowerCase(), senderWallet).run();
    await auditLog(c, username, "user", "DEPOSIT_REJECTED", txHash.slice(0, 24), check.reason);
    return c.json({ error: `فشل التحقق: ${check.reason}` }, 400);
  }

  // Credit atomically + mark confirmed
  const credit = await modifyBalance(c.env, username, check.actualAmount ?? amount, "DEPOSIT",
    { note: `إيداع مؤكد ${txHash.slice(0, 16)}…` });

  if (!credit.ok) {
    return c.json({ error: credit.reason }, 400);
  }

  await c.env.DB.prepare(
    `INSERT INTO usdt_deposits (username, amount, tx_hash, status, sender_wallet, confirmed_at)
     VALUES (?, ?, ?, 'CONFIRMED', ?, datetime('now'))`
  ).bind(username, check.actualAmount ?? amount, txHash.toLowerCase(), senderWallet || check.sender || "").run();

  await notify(c.env, username, "تم تأكيد الإيداع ✅",
    `تم إضافة ${check.actualAmount ?? amount} USDT إلى محفظتك.`);
  await auditLog(c, username, "user", "DEPOSIT_CONFIRMED", txHash.slice(0, 24), String(check.actualAmount));

  return c.json({ ok: true, credited: check.actualAmount ?? amount, balance: credit.newBalance });
});

// ============================================================
// POST /api/wallet/withdraw — request withdrawal (locks funds)
// ============================================================
wallet.post("/withdraw", requireUser, requireCsrf, rateLimit(5, 600), async (c) => {
  const username = c.get("user")!.username;
  const body = await formBody(c);

  const amount = parseFloat(String(body.amount ?? ""));
  const destWallet = String(body.wallet ?? "").trim();

  if (!(amount > 0)) return c.json({ error: "المبلغ يجب أن يكون أكبر من صفر" }, 400);
  if (!isValidBscAddress(destWallet)) {
    return c.json({ error: "عنوان محفظة BEP-20 غير صالح" }, 400);
  }

  // Check pending withdrawals don't exceed reasonable limits
  const pending = await c.env.DB.prepare(
    "SELECT COUNT(*) AS cnt FROM withdraw_requests WHERE username = ? AND status = 'PENDING'"
  ).bind(username).first<{ cnt: number }>();
  if ((pending?.cnt ?? 0) >= 3) {
    return c.json({ error: "لديك 3 طلبات سحب قيد المعالجة بالفعل" }, 429);
  }

  const res = await c.env.DB.prepare(
    "INSERT INTO withdraw_requests (username, amount, wallet) VALUES (?, ?, ?)"
  ).bind(username, amount, destWallet).run();
  const requestId = Number(res.meta.last_row_id);

  const lock = await lockForWithdrawal(c.env, username, amount, requestId);
  if (!lock.ok) {
    await c.env.DB.prepare("DELETE FROM withdraw_requests WHERE id = ?").bind(requestId).run();
    return c.json({ error: lock.reason }, 400);
  }

  await notify(c.env, username, "تم استلام طلب السحب 📤",
    `${amount} USDT إلى ${destWallet.slice(0, 10)}… بانتظار مراجعة الإدارة.`);
  await auditLog(c, username, "user", "WITHDRAW_REQUEST", `wd:${requestId}`, String(amount));

  return c.json({ ok: true, request_id: requestId });
});

export default wallet;
