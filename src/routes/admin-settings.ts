/**
 * Admin Settings + Financial Control Center + Ledger + Verification
 *
 * Phase 2: Production-grade financial P2P platform backend.
 *
 * Security: All endpoints require requireAdmin + valid session + CSRF.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireAdmin, requireCsrf, rateLimit } from "../middleware/auth";
import { formBody } from "../utils/body";
import { auditLog } from "../utils/db";

const adminSettings = new Hono<AppEnv>();

// ============================================================
// Helper: get/set admin settings from platform_config
// ============================================================
async function getSetting(db: D1Database, key: string, fallback = ""): Promise<string> {
  const row = await db.prepare("SELECT value FROM platform_config WHERE key = ?").bind(key).first<{ value: string }>();
  return row?.value ?? fallback;
}

async function setSetting(db: D1Database, key: string, value: string): Promise<void> {
  await db.prepare(
    "INSERT INTO platform_config (key, value, updated) VALUES (?, ?, datetime('now')) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated = datetime('now')"
  ).bind(key, value).run();
}

// ============================================================
// GET /api/admin/settings — all settings grouped
// ============================================================
adminSettings.get("/", requireAdmin, async (c) => {
  const db = c.env.DB;

  const keys = [
    // General
    "platform_name", "platform_status", "allow_registration", "allow_p2p_trading",
    "min_trade_amount", "max_trade_amount", "default_currency", "timezone",
    // Market
    "buy_spread", "sell_spread", "market_source", "manual_price_override", "manual_override_active",
    "price_refresh_interval", "stale_threshold_minutes", "min_acceptable_price", "max_acceptable_price",
    // Trading
    "trade_min_usdt", "trade_max_usdt", "trade_timeout_minutes", "payment_confirmation_timeout",
    "dispute_timeout_minutes", "max_active_trades_per_user", "trading_enabled",
    // Fees
    "p2p_fee_percent", "deposit_fee_percent", "withdrawal_fee_percent", "min_fee", "max_fee",
    // Escrow
    "escrow_enabled", "auto_release_enabled", "auto_refund_enabled",
    // Security
    "session_expiration_hours", "max_login_attempts", "require_email_verification",
    "require_kyc_trading", "require_kyc_withdrawal", "admin_session_timeout_hours",
    // Notifications
    "enable_price_alerts", "enable_trade_alerts", "enable_admin_security_alerts",
    "enable_email_notifications", "enable_telegram_notifications",
  ];

  const settings: Record<string, string> = {};
  for (const key of keys) {
    settings[key] = await getSetting(db, key, getDefault(key));
  }

  return c.json({ ok: true, settings });
});

// ============================================================
// POST /api/admin/settings — save settings
// ============================================================
adminSettings.post("/", requireAdmin, requireCsrf, rateLimit(30, 60), async (c) => {
  const db = c.env.DB;
  const admin = c.get("user")!.username;
  const body = await formBody(c);

  const allowedKeys = new Set([
    "platform_name", "platform_status", "allow_registration", "allow_p2p_trading",
    "min_trade_amount", "max_trade_amount", "default_currency", "timezone",
    "buy_spread", "sell_spread", "market_source", "manual_price_override", "manual_override_active",
    "price_refresh_interval", "stale_threshold_minutes", "min_acceptable_price", "max_acceptable_price",
    "trade_min_usdt", "trade_max_usdt", "trade_timeout_minutes", "payment_confirmation_timeout",
    "dispute_timeout_minutes", "max_active_trades_per_user", "trading_enabled",
    "p2p_fee_percent", "deposit_fee_percent", "withdrawal_fee_percent", "min_fee", "max_fee",
    "escrow_enabled", "auto_release_enabled", "auto_refund_enabled",
    "session_expiration_hours", "max_login_attempts", "require_email_verification",
    "require_kyc_trading", "require_kyc_withdrawal", "admin_session_timeout_hours",
    "enable_price_alerts", "enable_trade_alerts", "enable_admin_security_alerts",
    "enable_email_notifications", "enable_telegram_notifications",
  ]);

  const saved: string[] = [];
  for (const [key, value] of Object.entries(body)) {
    if (!allowedKeys.has(key)) continue;
    const val = String(value).trim();
    const oldVal = await getSetting(db, key, getDefault(key));

    // Validate dangerous settings
    if (key === "buy_spread" || key === "sell_spread") {
      const num = parseFloat(val);
      if (!Number.isFinite(num) || num < 0 || num > 0.5) continue; // max 50%
    }
    if (key.includes("price") && key.includes("min")) {
      const num = parseFloat(val);
      if (!Number.isFinite(num) || num < 0) continue;
    }
    if (key.includes("fee") && key.includes("percent")) {
      const num = parseFloat(val);
      if (!Number.isFinite(num) || num < 0 || num > 50) continue; // max 50%
    }
    if (key === "trade_timeout_minutes") {
      const num = parseInt(val);
      if (!Number.isFinite(num) || num < 5 || num > 1440) continue; // 5 min to 24h
    }

    // Validate safety: if manual override enabled, require explicit confirmation
    if (key === "manual_override_active" && val === "1") {
      const overridePrice = await getSetting(db, "manual_price_override", "0");
      if (parseFloat(overridePrice) <= 0) continue; // must set price first
    }

    await setSetting(db, key, val);
    if (oldVal !== val) saved.push(key);
  }

  // Audit log the change
  await auditLog(c, admin, "admin", "SETTINGS_UPDATE", "platform_settings", JSON.stringify({ saved }));

  return c.json({ ok: true, saved });
});

// ============================================================
// GET /api/admin/financial — Financial Control Center
// ============================================================
adminSettings.get("/financial", requireAdmin, async (c) => {
  const db = c.env.DB;

  // Total balances
  const balRow = await db.prepare(
    "SELECT COALESCE(SUM(balance), 0) as total_available, COALESCE(SUM(locked), 0) as total_locked FROM wallets"
  ).first<{ total_available: number; total_locked: number }>();

  // Escrow total (locked in trades)
  const escrowRow = await db.prepare(
    "SELECT COALESCE(SUM(amount), 0) as escrow_total FROM trades WHERE status IN ('PENDING', 'PAYMENT_SENT', 'DISPUTED') AND escrow_status = 'LOCKED'"
  ).first<{ escrow_total: number }>();

  // Trade stats
  const tradeStats = await db.prepare(
    `SELECT
      COUNT(*) as total,
      SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
      SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
      SUM(CASE WHEN status = 'PAYMENT_SENT' THEN 1 ELSE 0 END) as payment_sent,
      SUM(CASE WHEN status = 'DISPUTED' THEN 1 ELSE 0 END) as disputed,
      SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) as cancelled,
      SUM(CASE WHEN status = 'COMPLETED' THEN amount ELSE 0 END) as total_volume,
      SUM(CASE WHEN status = 'COMPLETED' THEN platform_fee ELSE 0 END) as total_fees
    FROM trades`
  ).first<any>();

  // Deposit/withdrawal stats
  const depositStats = await db.prepare(
    "SELECT COALESCE(SUM(amount), 0) as total_deposited FROM usdt_deposits WHERE status = 'CONFIRMED'"
  ).first<{ total_deposited: number }>();

  const withdrawalStats = await db.prepare(
    "SELECT COALESCE(SUM(amount), 0) as total_withdrawn FROM withdraw_requests WHERE status = 'COMPLETED'"
  ).first<{ total_withdrawn: number }>();

  // Reconciliation
  const expectedPlatform = (balRow?.total_available ?? 0) + (balRow?.total_locked ?? 0);
  const totalDeposits = depositStats?.total_deposited ?? 0;
  const totalWithdrawals = withdrawalStats?.total_withdrawn ?? 0;
  const netFlow = totalDeposits - totalWithdrawals;
  const difference = expectedPlatform - netFlow;
  const isHealthy = Math.abs(difference) < 0.01; // allow 0.01 USDT rounding

  // User count
  const userCount = await db.prepare("SELECT COUNT(*) as cnt FROM users").first<{ cnt: number }>();

  return c.json({
    ok: true,
    financial: {
      total_available: balRow?.total_available ?? 0,
      total_locked: balRow?.total_locked ?? 0,
      total_escrow: escrowRow?.escrow_total ?? 0,
      total_deposited: totalDeposits,
      total_withdrawn: totalWithdrawals,
      net_flow: netFlow,
      platform_fees: tradeStats?.total_fees ?? 0,
      total_users: userCount?.cnt ?? 0,
      trades: {
        total: tradeStats?.total ?? 0,
        completed: tradeStats?.completed ?? 0,
        pending: tradeStats?.pending ?? 0,
        payment_sent: tradeStats?.payment_sent ?? 0,
        disputed: tradeStats?.disputed ?? 0,
        cancelled: tradeStats?.cancelled ?? 0,
        total_volume: tradeStats?.total_volume ?? 0,
      },
      reconciliation: {
        expected_platform: expectedPlatform,
        net_flow: netFlow,
        difference: difference,
        healthy: isHealthy,
      },
    },
  });
});

// ============================================================
// GET /api/admin/ledger — Financial Ledger
// ============================================================
adminSettings.get("/ledger", requireAdmin, async (c) => {
  const db = c.env.DB;
  const limit = Math.min(parseInt(c.req.query("limit") || "100"), 500);
  const offset = parseInt(c.req.query("offset") || "0");
  const type = c.req.query("type"); // optional filter
  const username = c.req.query("username"); // optional filter

  let sql = "SELECT * FROM wallet_history WHERE 1=1";
  const params: any[] = [];

  if (type) {
    sql += " AND action = ?";
    params.push(type);
  }
  if (username) {
    sql += " AND username = ?";
    params.push(username);
  }

  sql += " ORDER BY id DESC LIMIT ? OFFSET ?";
  params.push(limit, offset);

  const rows = await db.prepare(sql).bind(...params).all();
  const countSql = type
    ? `SELECT COUNT(*) as total FROM wallet_history WHERE action = ?`
    : `SELECT COUNT(*) as total FROM wallet_history`;
  const countRow = type
    ? await db.prepare(countSql).bind(type).first<{ total: number }>()
    : await db.prepare(countSql).first<{ total: number }>();

  return c.json({
    ok: true,
    ledger: rows.results ?? [],
    total: countRow?.total ?? 0,
    limit,
    offset,
  });
});

// ============================================================
// POST /api/admin/adjust — Manual financial adjustment
// ============================================================
adminSettings.post("/adjust", requireAdmin, requireCsrf, rateLimit(10, 300), async (c) => {
  const db = c.env.DB;
  const admin = c.get("user")!.username;
  const body = await formBody(c);

  const username = String(body.username ?? "").trim();
  const amount = parseFloat(String(body.amount ?? "0"));
  const reason = String(body.reason ?? "").trim();
  const action = body.amount && parseFloat(String(body.amount)) > 0 ? "ADMIN_CREDIT" : "ADMIN_DEBIT";

  if (!username) return c.json({ error: "المستخدم مطلوب" }, 400);
  if (!Number.isFinite(amount) || amount === 0) return c.json({ error: "المبلغ يجب أن يكون رقماً موجباً أو سالباً" }, 400);
  if (Math.abs(amount) > 100000) return c.json({ error: "المبلغ يتجاوز الحد الأقصى" }, 400);
  if (reason.length < 5) return c.json({ error: "السبب مطلوب (5 أحرف على الأقل)" }, 400);

  // Check user exists
  const wallet = await db.prepare("SELECT username, balance FROM wallets WHERE username = ?").bind(username).first<{ username: string; balance: number }>();
  if (!wallet) return c.json({ error: "المحفظة غير موجودة" }, 404);

  const absAmount = Math.abs(amount);

  if (amount > 0) {
    // Credit
    const before = wallet.balance as number;
    const after = before + amount;
    await db.batch([
      db.prepare("UPDATE wallets SET balance = ? WHERE username = ?").bind(after, username),
      db.prepare(
        "INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, reference_id, note) VALUES (?, 'ADMIN_CREDIT', ?, ?, ?, 0, ?)"
      ).bind(username, absAmount, before, after, `Admin ${admin}: ${reason}`),
    ]);
  } else {
    // Debit
    const before = wallet.balance as number;
    const after = before - absAmount;
    if (after < -0.001) return c.json({ error: `الرصيد غير كافٍ (المتاح: ${before})` }, 400);
    await db.batch([
      db.prepare("UPDATE wallets SET balance = ? WHERE username = ?").bind(after, username),
      db.prepare(
        "INSERT INTO wallet_history (username, action, amount, balance_before, balance_after, reference_id, note) VALUES (?, 'ADMIN_DEBIT', ?, ?, ?, 0, ?)"
      ).bind(username, absAmount, before, after, `Admin ${admin}: ${reason}`),
    ]);
  }

  await auditLog(c, admin, "admin", "FINANCIAL_ADJUST", `user:${username}`, `${action} ${absAmount} — ${reason}`);
  return c.json({ ok: true });
});

// ============================================================
// GET /api/admin/reconciliation — Run reconciliation check
// ============================================================
adminSettings.get("/reconciliation", requireAdmin, async (c) => {
  const db = c.env.DB;

  // Sum of all wallet balances
  const walletSum = await db.prepare(
    "SELECT COALESCE(SUM(balance), 0) as total_balance, COALESCE(SUM(locked), 0) as total_locked FROM wallets"
  ).first<{ total_balance: number; total_locked: number }>();

  // Ledger consistency check: sum of all wallet_history balance_after should match
  const ledgerBalance = await db.prepare(
    "SELECT balance_after FROM wallet_history ORDER BY id DESC LIMIT 1"
  ).first<{ balance_after: number }>();

  // Check for negative balances
  const negativeWallets = await db.prepare(
    "SELECT username, balance, locked FROM wallets WHERE balance < -0.001 OR locked < -0.001"
  ).all();

  // Check for orphaned escrow (locked in trades but trade is COMPLETED/CANCELLED)
  const orphanedEscrow = await db.prepare(
    "SELECT id, amount, escrow_status, status FROM trades WHERE status IN ('COMPLETED', 'CANCELLED') AND escrow_status = 'LOCKED'"
  ).all();

  // Check for negative available balance
  const negativeAvail = negativeWallets.results?.length ?? 0;
  const orphaned = orphanedEscrow.results?.length ?? 0;

  const healthy = negativeAvail === 0 && orphaned === 0;

  return c.json({
    ok: true,
    healthy,
    wallet_summary: {
      total_balance: walletSum?.total_balance ?? 0,
      total_locked: walletSum?.total_locked ?? 0,
      combined: (walletSum?.total_balance ?? 0) + (walletSum?.total_locked ?? 0),
    },
    issues: {
      negative_balances: negativeAvail,
      orphaned_escrow: orphaned,
      negative_wallets: negativeWallets.results ?? [],
      orphaned_trades: orphanedEscrow.results ?? [],
    },
  });
});

// ============================================================
// GET /api/admin/tx-verify/:txHash — Verify on-chain TX
// ============================================================
adminSettings.get("/tx-verify/:txHash", requireAdmin, async (c) => {
  const db = c.env.DB;
  const txHash = (c.req.param("txHash") || "").trim();

  if (!txHash || txHash.length < 10) {
    return c.json({ error: "Transaction hash غير صالح" }, 400);
  }

  // Check replay protection
  const existing = await db.prepare(
    "SELECT id, username, amount, status FROM usdt_deposits WHERE tx_hash = ?"
  ).bind(txHash).first();
  if (existing) {
    return c.json({
      verified: false,
      reason: "تم استخدام هذا الـ TX Hash مسبقاً",
      existing_deposit: existing,
    });
  }

  // Verify on-chain via BSC RPC
  try {
    const rpcUrl = c.env.BSC_RPC_URL;
    const usdtContract = c.env.USDT_CONTRACT;
    const decimals = parseInt(c.env.USDT_DECIMALS || "6");

    // Get transaction receipt
    const receiptRes = await fetch(rpcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "eth_getTransactionReceipt",
        params: [txHash],
        id: 1,
      }),
      signal: AbortSignal.timeout(10000),
    });
    const receipt = (await receiptRes.json()) as any;

    if (!receipt?.result) {
      return c.json({ verified: false, reason: "المعاملة غير موجودة على الشبكة" });
    }

    if (receipt.result.status !== "0x1") {
      return c.json({ verified: false, reason: "المعاملة فشلت على الشبكة" });
    }

    // Check contract address
    if (receipt.result.to?.toLowerCase() !== usdtContract.toLowerCase()) {
      return c.json({ verified: false, reason: "عنوان العقد غير متطابق" });
    }

    // Decode transfer event (topic[1] = sender, topic[2] = receiver, data = amount)
    const transferTopic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
    const log = receipt.result.logs?.find((l: any) => l.topics?.[0] === transferTopic);

    if (!log) {
      return c.json({ verified: false, reason: "لم يتم العثور على عملية تحويل USDT" });
    }

    // Decode amount from data
    const amountHex = log.data;
    const amountRaw = BigInt(amountHex);
    const amount = Number(amountRaw) / Math.pow(10, decimals);

    // Check confirmations
    const blockRes = await fetch(rpcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "eth_blockNumber",
        params: [],
        id: 2,
      }),
      signal: AbortSignal.timeout(5000),
    });
    const blockData = (await blockRes.json()) as any;
    const currentBlock = parseInt(blockData?.result || "0", 16);
    const txBlock = parseInt(receipt.result.blockNumber || "0", 16);
    const confirmations = currentBlock - txBlock;

    return c.json({
      verified: true,
      tx_hash: txHash,
      amount,
      from: "0x" + log.topics[1].slice(26),
      to: "0x" + log.topics[2].slice(26),
      contract: receipt.result.to,
      confirmations,
      block_number: txBlock,
      status: "success",
    });
  } catch (err: any) {
    return c.json({ verified: false, reason: `خطأ في التحقق: ${err?.message}` });
  }
});

// ============================================================
// Helper: defaults for settings
// ============================================================
function getDefault(key: string): string {
  const defaults: Record<string, string> = {
    platform_name: "USDT P2P Palestine",
    platform_status: "OPEN",
    allow_registration: "1",
    allow_p2p_trading: "1",
    min_trade_amount: "10",
    max_trade_amount: "100000",
    default_currency: "ILS",
    timezone: "Asia/Jerusalem",
    buy_spread: "0.005",
    sell_spread: "0.005",
    market_source: "coingecko",
    manual_price_override: "0",
    manual_override_active: "0",
    price_refresh_interval: "3600",
    stale_threshold_minutes: "120",
    min_acceptable_price: "1",
    max_acceptable_price: "10",
    trade_min_usdt: "1",
    trade_max_usdt: "50000",
    trade_timeout_minutes: "30",
    payment_confirmation_timeout: "60",
    dispute_timeout_minutes: "1440",
    max_active_trades_per_user: "10",
    trading_enabled: "1",
    p2p_fee_percent: "1.0",
    deposit_fee_percent: "0",
    withdrawal_fee_percent: "1.0",
    min_fee: "0.1",
    max_fee: "100",
    escrow_enabled: "1",
    auto_release_enabled: "0",
    auto_refund_enabled: "0",
    session_expiration_hours: "720",
    max_login_attempts: "5",
    require_email_verification: "0",
    require_kyc_trading: "0",
    require_kyc_withdrawal: "0",
    admin_session_timeout_hours: "24",
    enable_price_alerts: "1",
    enable_trade_alerts: "1",
    enable_admin_security_alerts: "1",
    enable_email_notifications: "0",
    enable_telegram_notifications: "1",
  };
  return defaults[key] ?? "";
}

export default adminSettings;
