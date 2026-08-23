/**
 * D1 helpers — atomic wallet operations with mandatory ledger entries,
 * platform config, notifications, audit logging.
 *
 * FINANCIAL RULES:
 * - Every balance change MUST create a wallet_history ledger entry.
 * - Balance updates are batched atomically in a single D1 batch.
 * - Never silently modify balances.
 */
import type { AppEnv } from "../types";

export type Ctx = AppEnv["Bindings"];

export async function getConfig(ctx: Ctx, key: string, fallback: string): Promise<string> {
  const row = await ctx.DB.prepare(
    "SELECT value FROM platform_config WHERE key = ?"
  ).bind(key).first<{ value: string }>();
  return row?.value ?? fallback;
}

export async function setConfig(ctx: Ctx, key: string, value: string): Promise<void> {
  await ctx.DB.prepare(
    "INSERT INTO platform_config (key, value, updated) VALUES (?, ?, datetime('now')) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated = datetime('now')"
  ).bind(key, value).run();
}

export async function ensureWallet(ctx: Ctx, username: string): Promise<void> {
  await ctx.DB.prepare(
    "INSERT OR IGNORE INTO wallets (username, balance, locked) VALUES (?, 0, 0)"
  ).bind(username).run();
}

export async function getWallet(ctx: Ctx, username: string) {
  return ctx.DB.prepare(
    "SELECT username, balance, locked FROM wallets WHERE username = ?"
  ).bind(username).first<{ username: string; balance: number; locked: number }>();
}

/**
 * Atomic balance mutation + mandatory ledger entry.
 * action: DEPOSIT | WITHDRAWAL | ESCROW_LOCK | ESCROW_RELEASE | REFUND |
 *         PLATFORM_FEE | ADMIN_CREDIT | ADMIN_DEBIT
 */
export async function modifyBalance(
  ctx: Ctx,
  username: string,
  amount: number,
  action: string,
  opts: { refId?: number; note?: string } = {}
): Promise<{ ok: boolean; reason?: string; newBalance?: number }> {
  if (!Number.isFinite(amount) || amount <= 0) {
    return { ok: false, reason: "المبلغ يجب أن يكون رقماً موجباً" };
  }

  const wallet = await getWallet(ctx, username);
  if (!wallet) return { ok: false, reason: "المحفظة غير موجودة" };

  const before = wallet.balance;
  let after = before;

  switch (action) {
    case "DEPOSIT":
    case "ESCROW_RELEASE":
    case "REFUND":
    case "ADMIN_CREDIT":
      after = round2(before + amount);
      break;
    case "WITHDRAWAL":
    case "ADMIN_DEBIT":
    case "PLATFORM_FEE":
      after = round2(before - amount);
      if (after < -0.001) return { ok: false, reason: "الرصيد غير كافٍ" };
      break;
    default:
      return { ok: false, reason: `نوع عملية غير معروف: ${action}` };
  }

  await ctx.DB.batch([
    ctx.DB.prepare("UPDATE wallets SET balance = ? WHERE username = ?").bind(after, username),
    ctx.DB.prepare(
      "INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, reference_id, note) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).bind(username, action, amount, before, after, opts.refId ?? 0, opts.note ?? ""),
  ]);

  return { ok: true, newBalance: after };
}

/** Atomic escrow lock: move from available to locked. */
export async function escrowLock(
  ctx: Ctx, username: string, amount: number, tradeId: number
): Promise<{ ok: boolean; reason?: string }> {
  const wallet = await getWallet(ctx, username);
  if (!wallet) return { ok: false, reason: "المحفظة غير موجودة" };

  const before = round2(wallet.balance);
  const amt = round2(amount);
  if (before < amt) return { ok: false, reason: `رصيد USDT غير كافٍ (المطلوب ${amt}، المتاح ${before})` };

  const after = round2(before - amt);
  await ctx.DB.batch([
    ctx.DB.prepare("UPDATE wallets SET balance = ?, locked = locked + ? WHERE username = ?")
      .bind(after, amt, username),
    ctx.DB.prepare(
      "INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, reference_id, note) VALUES (?, 'ESCROW_LOCK', ?, ?, ?, ?, ?)"
    ).bind(username, amt, before, after, tradeId, "قفل ضمان الصفقة"),
  ]);
  return { ok: true };
}

/** Atomic escrow release: locked → buyer's available. Double-release protected by status check in caller. */
export async function escrowReleaseToBuyer(
  ctx: Ctx, seller: string, buyer: string, amount: number, tradeId: number
): Promise<{ ok: boolean; reason?: string }> {
  const amt = round2(amount);

  // Verify locked funds exist (prevents double-release at DB level)
  const sellerWallet = await getWallet(ctx, seller);
  if (!sellerWallet || sellerWallet.locked < amt - 0.001) {
    return { ok: false, reason: "الأموال المقفلة غير كافية (ربما تم تحريرها مسبقاً)" };
  }

  await ensureWallet(ctx, buyer);
  const buyerWallet = await getWallet(ctx, buyer);
  if (!buyerWallet) return { ok: false, reason: "محفظة المشتري غير موجودة" };

  await ctx.DB.batch([
    ctx.DB.prepare("UPDATE wallets SET locked = MAX(locked - ?, 0) WHERE username = ?").bind(amt, seller),
    ctx.DB.prepare("UPDATE wallets SET balance = balance + ? WHERE username = ?").bind(amt, buyer),
    ctx.DB.prepare(
      "INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, reference_id, note) VALUES (?, 'ESCROW_RELEASE', ?, ?, ?, ?, ?)"
    ).bind(buyer, amt, buyerWallet.balance, round2(buyerWallet.balance + amt), tradeId, "تحرير USDT من الضمان"),
  ]);
  return { ok: true };
}

/** Atomic escrow refund: locked → back to seller's available. */
export async function escrowRefundSeller(
  ctx: Ctx, seller: string, amount: number, tradeId: number
): Promise<{ ok: boolean; reason?: string }> {
  const amt = round2(amount);
  const sellerWallet = await getWallet(ctx, seller);
  if (!sellerWallet || sellerWallet.locked < amt - 0.001) {
    return { ok: false, reason: "الأموال المقفلة غير كافية (ربما تم إرجاعها مسبقاً)" };
  }

  await ctx.DB.batch([
    ctx.DB.prepare("UPDATE wallets SET locked = MAX(locked - ?, 0), balance = balance + ? WHERE username = ?")
      .bind(amt, amt, seller),
    ctx.DB.prepare(
      "INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, reference_id, note) VALUES (?, 'REFUND', ?, ?, ?, ?, ?)"
    ).bind(seller, amt, sellerWallet.balance, round2(sellerWallet.balance + amt), tradeId, "إرجاع USDT من الضمان"),
  ]);
  return { ok: true };
}

/** Lock funds for pending withdrawal (available → locked). */
export async function lockForWithdrawal(
  ctx: Ctx, username: string, amount: number, requestId: number
): Promise<{ ok: boolean; reason?: string }> {
  const wallet = await getWallet(ctx, username);
  if (!wallet) return { ok: false, reason: "المحفظة غير موجودة" };
  const before = round2(wallet.balance);
  const amt = round2(amount);
  if (before < amt) return { ok: false, reason: "الرصيد غير كافٍ" };

  await ctx.DB.batch([
    ctx.DB.prepare("UPDATE wallets SET balance = ?, locked = locked + ? WHERE username = ?")
      .bind(round2(before - amt), amt, username),
    ctx.DB.prepare(
      "INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, reference_id, note) VALUES (?, 'WITHDRAWAL_LOCK', ?, ?, ?, ?, 'قفل مبلغ السحب')"
    ).bind(username, amt, before, round2(before - amt), requestId),
  ]);
  return { ok: true };
}

// ============================================================
// NOTIFICATIONS
// ============================================================

export async function notify(
  ctx: Ctx, username: string, title: string, message: string
): Promise<void> {
  await ctx.DB.prepare(
    "INSERT INTO notifications (username, title, message) VALUES (?, ?, ?)"
  ).bind(username, title, message).run();

  // Telegram notification is fire-and-forget (best effort)
  try {
    const user = await ctx.DB.prepare(
      "SELECT telegram_id FROM users WHERE username = ?"
    ).bind(username).first<{ telegram_id: string | null }>();
    if (user?.telegram_id && ctx.TELEGRAM_BOT_TOKEN) {
      await fetch(`https://api.telegram.org/bot${ctx.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: user.telegram_id, text: `<b>${title}</b>\n${message}`, parse_mode: "HTML" }),
      }).catch(() => {});
    }
  } catch { /* best effort */ }
}

// ============================================================
// AUDIT LOG
// ============================================================

export async function auditLog(
  c: ContextLike, actor: string, role: string, action: string,
  target = "", details = ""
): Promise<void> {
  const ip = c.req?.header?.("CF-Connecting-IP") || "";
  await c.env.DB.prepare(
    "INSERT INTO audit_log (actor, actor_role, action, target, details, ip) VALUES (?, ?, ?, ?, ?, ?)"
  ).bind(actor, role, action, target, details.slice(0, 500), ip).run();
}

// Minimal structural type to avoid importing Hono types here
type ContextLike = {
  req: { header(name: string): string | undefined };
  env: AppEnv["Bindings"];
};

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
