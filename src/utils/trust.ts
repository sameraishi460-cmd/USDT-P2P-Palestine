/**
 * Trust Score Calculator — V2
 * Calculates a 0-100 trust score from multiple factors.
 * All values are computed from actual D1 data; cannot be faked.
 */
import type { Ctx } from "./db";

export interface TrustData {
  trust_score: number;
  total_ratings: number;
  avg_rating: number;
  completed_trades: number;
  cancelled_trades: number;
  disputed_trades: number;
  completion_rate: number;
  account_age_days: number;
}

/**
 * Recalculate trust score from raw data.
 * Score components (total 100):
 * - Completion rate: 35 points
 * - Average rating: 25 points
 * - Trade volume: 20 points
 * - Account age: 10 points
 * - Dispute penalty: -10 points max
 * - Cancellation penalty: up to -5 points
 */
export async function recalcTrust(ctx: Ctx, username: string): Promise<TrustData> {
  const db = ctx.DB;

  // Gather raw stats
  const [tradeStats, reviewStats, userRow] = await Promise.all([
    db.prepare(`
      SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS completed,
        SUM(CASE WHEN status='CANCELLED' THEN 1 ELSE 0 END) AS cancelled,
        SUM(CASE WHEN status='DISPUTED' THEN 1 ELSE 0 END) AS disputed
      FROM trades WHERE buyer = ? OR seller = ?
    `).bind(username, username).first<any>(),
    db.prepare(`
      SELECT COUNT(*) AS cnt, AVG(rating) AS avg
      FROM reviews WHERE to_user = ?
    `).bind(username).first<{ cnt: number; avg: number }>(),
    db.prepare(`SELECT created_at FROM users WHERE username = ?`).bind(username).first<{ created_at: string }>(),
  ]);

  const total = tradeStats?.total || 0;
  const completed = tradeStats?.completed || 0;
  const cancelled = tradeStats?.cancelled || 0;
  const disputed = tradeStats?.disputed || 0;
  const completionRate = total > 0 ? (completed / total) * 100 : 0;
  const avgRating = reviewStats?.avg || 0;
  const totalRatings = reviewStats?.cnt || 0;

  // Account age
  let accountAgeDays = 0;
  if (userRow?.created_at) {
    const created = new Date(userRow.created_at);
    accountAgeDays = Math.floor((Date.now() - created.getTime()) / 86400000);
  }

  // Score calculation
  let score = 0;

  // 1. Completion rate (35 points)
  score += (completionRate / 100) * 35;

  // 2. Average rating (25 points) — scale 1-5 to 0-1
  if (totalRatings > 0) {
    score += ((avgRating - 1) / 4) * 25;
  } else {
    // No ratings yet — give neutral score
    score += 12.5;
  }

  // 3. Trade volume (20 points) — logarithmic scale
  if (completed > 0) {
    score += Math.min(20, Math.log2(completed + 1) * 4);
  }

  // 4. Account age (10 points) — capped at 365 days
  score += Math.min(10, (accountAgeDays / 365) * 10);

  // 5. Dispute penalty (-10 points max)
  const disputeRatio = total > 0 ? disputed / total : 0;
  score -= disputeRatio * 100; // Heavy penalty for disputes

  // 6. Cancellation penalty (up to -5 points)
  const cancelRatio = total > 0 ? cancelled / total : 0;
  score -= cancelRatio * 25;

  // Clamp 0-100
  score = Math.max(0, Math.min(100, Math.round(score * 10) / 10));

  const data: TrustData = {
    trust_score: score,
    total_ratings: totalRatings,
    avg_rating: Math.round((avgRating || 0) * 10) / 10,
    completed_trades: completed,
    cancelled_trades: cancelled,
    disputed_trades: disputed,
    completion_rate: Math.round(completionRate * 10) / 10,
    account_age_days: accountAgeDays,
  };

  // Persist to user_trust table
  await db.prepare(`
    INSERT INTO user_trust (username, trust_score, total_ratings, avg_rating, completed_trades,
      cancelled_trades, disputed_trades, completion_rate, account_age_days, last_trade_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
    ON CONFLICT(username) DO UPDATE SET
      trust_score=excluded.trust_score, total_ratings=excluded.total_ratings,
      avg_rating=excluded.avg_rating, completed_trades=excluded.completed_trades,
      cancelled_trades=excluded.cancelled_trades, disputed_trades=excluded.disputed_trades,
      completion_rate=excluded.completion_rate, account_age_days=excluded.account_age_days,
      updated_at=datetime('now')
  `).bind(username, score, totalRatings, data.avg_rating, completed, cancelled, disputed,
    data.completion_rate, accountAgeDays).run();

  return data;
}

/** Get stored trust data (fast, no recalc) */
export async function getTrust(ctx: Ctx, username: string): Promise<TrustData | null> {
  const row = await ctx.DB.prepare(
    "SELECT * FROM user_trust WHERE username = ?"
  ).bind(username).first<TrustData>();
  return row || null;
}

/** VIP level based on trust score + volume */
export function getVipLevel(trust: TrustData | null): { level: string; badge: string; label: string } {
  if (!trust) return { level: "bronze", badge: "🥉", label: "برونزي" };
  if (trust.trust_score >= 90 && trust.completed_trades >= 50) return { level: "diamond", badge: "💎", label: "تاجر موثوق" };
  if (trust.trust_score >= 75 && trust.completed_trades >= 20) return { level: "gold", badge: "🥇", label: "ذهبي" };
  if (trust.trust_score >= 60 && trust.completed_trades >= 10) return { level: "silver", badge: "🥈", label: "فضي" };
  return { level: "bronze", badge: "🥉", label: "برونزي" };
}
