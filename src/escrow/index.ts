/**
 * Escrow State Machine — enforces valid trade state transitions.
 *
 * Trade statuses (trades table):
 *   CREATED → PAYMENT_PENDING → PAYMENT_SENT → PAYMENT_VERIFICATION → COMPLETED
 *   CREATED → CANCELLED
 *   PAYMENT_SENT → DISPUTED → (RELEASED | REFUNDED)
 *
 * Escrow statuses (trades.escrow_status):
 *   WAITING → LOCKED → (RELEASED | REFUNDED | DISPUTED)
 *
 * Rules:
 *   - Only valid transitions are allowed (server-side enforced)
 *   - Every transition is idempotent (re-executing a completed action is a no-op)
 *   - All transitions write to escrow_transactions ledger
 *   - All transitions are audit-logged
 */

import type { AppEnv } from "../types";

export type TradeStatus =
  | "PENDING"
  | "PAYMENT_SENT"
  | "COMPLETED"
  | "CANCELLED"
  | "DISPUTED";

export type EscrowStatus =
  | "WAITING"
  | "LOCKED"
  | "RELEASED"
  | "REFUNDED"
  | "DISPUTED";

export type EscrowAction = "LOCK" | "RELEASE" | "REFUND";

// Valid trade status transitions
const VALID_TRANSITIONS: Record<string, TradeStatus[]> = {
  PENDING: ["PAYMENT_SENT", "CANCELLED"],
  PAYMENT_SENT: ["COMPLETED", "DISPUTED", "CANCELLED"],
  DISPUTED: ["COMPLETED", "CANCELLED"],
  COMPLETED: [],  // terminal
  CANCELLED: [],  // terminal
};

// Valid escrow status transitions
const VALID_ESCROW_TRANSITIONS: Record<string, EscrowStatus[]> = {
  WAITING: ["LOCKED", "REFUNDED"],
  LOCKED: ["RELEASED", "REFUNDED", "DISPUTED"],
  DISPUTED: ["RELEASED", "REFUNDED"],
  RELEASED: [],   // terminal
  REFUNDED: [],   // terminal
};

/**
 * Check if a trade status transition is valid.
 */
export function isValidTransition(current: string, next: string): boolean {
  const allowed = VALID_TRANSITIONS[current];
  if (!allowed) return false;
  return allowed.includes(next as TradeStatus);
}

/**
 * Check if an escrow status transition is valid.
 */
export function isValidEscrowTransition(current: string, next: string): boolean {
  const allowed = VALID_ESCROW_TRANSITIONS[current];
  if (!allowed) return false;
  return allowed.includes(next as EscrowStatus);
}

/**
 * Record an escrow transaction in the ledger.
 * This is the ONLY way to create escrow ledger entries.
 */
export async function recordEscrowTransaction(
  db: D1Database,
  tradeId: number,
  userId: string,
  amount: number,
  action: EscrowAction,
  opts: { reason?: string; adminActor?: string; txHash?: string } = {}
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO escrow_transactions (trade_id, user_id, asset, amount, action, status, reason, admin_actor, tx_hash, created_at, updated_at)
       VALUES (?, ?, 'USDT', ?, ?, 'COMPLETED', ?, ?, ?, datetime('now'), datetime('now'))`
    )
    .bind(
      tradeId,
      userId,
      Math.round(amount * 100) / 100,
      action,
      opts.reason || "",
      opts.adminActor || "",
      opts.txHash || ""
    )
    .run();
}

/**
 * Get all escrow transactions for a trade (for timeline display).
 */
export async function getEscrowTimeline(
  db: D1Database,
  tradeId: number
): Promise<any[]> {
  const rows = await db
    .prepare(
      `SELECT id, trade_id, user_id, asset, amount, action, status, reason, admin_actor, created_at
       FROM escrow_transactions WHERE trade_id = ? ORDER BY id ASC`
    )
    .bind(tradeId)
    .all();
  return rows.results ?? [];
}

/**
 * Check if a specific escrow action has already been performed on this trade.
 * Used for idempotency — prevents double-lock, double-release, double-refund.
 */
export async function hasEscrowAction(
  db: D1Database,
  tradeId: number,
  action: EscrowAction
): Promise<boolean> {
  const row = await db
    .prepare(
      "SELECT COUNT(*) as cnt FROM escrow_transactions WHERE trade_id = ? AND action = ? AND status = 'COMPLETED'"
    )
    .bind(tradeId, action)
    .first<{ cnt: number }>();
  return (row?.cnt ?? 0) > 0;
}

/**
 * Get trade expiration timeout from platform config.
 * Default: 30 minutes.
 */
export async function getTradeTimeoutMinutes(db: D1Database): Promise<number> {
  const row = await db
    .prepare("SELECT value FROM platform_config WHERE key = 'trade_timeout_minutes'")
    .first<{ value: string }>();
  return parseInt(row?.value ?? "30", 10) || 30;
}
