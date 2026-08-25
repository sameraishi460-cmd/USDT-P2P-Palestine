/**
 * Cron handler — runs on the Cloudflare Workers Cron Trigger (hourly).
 * Fetches market price from an external source, updates market_price,
 * records price_history, and checks price alerts.
 */
import type { AppEnv } from "./types";

// CoinGecko USDT → USD price (free, no API key needed)
const COINGECKO_URL =
  "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=usd";

// Fallback: Binance USDT/USDC pair (also free, no key)
const BINANCE_URL =
  "https://api.binance.com/api/v3/ticker/price?symbol=USDCUSDT";

interface PriceResult {
  price: number;
  source: string;
  ok: boolean;
}

async function fetchUsdtUsdPrice(): Promise<PriceResult> {
  // Try CoinGecko first
  try {
    const res = await fetch(COINGECKO_URL, {
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) {
      const data = (await res.json()) as any;
      const price = data?.tether?.usd;
      if (typeof price === "number" && price > 0 && price < 10) {
        return { price, source: "coingecko", ok: true };
      }
    }
  } catch { /* fall through */ }

  // Fallback to Binance
  try {
    const res = await fetch(BINANCE_URL, {
      signal: AbortSignal.timeout(8000),
    });
    if (res.ok) {
      const data = (await res.json()) as any;
      const price = parseFloat(data?.price);
      if (Number.isFinite(price) && price > 0 && price < 10) {
        return { price, source: "binance", ok: true };
      }
    }
  } catch { /* fall through */ }

  return { price: 0, source: "none", ok: false };
}

async function fetchUsdIlsRate(): Promise<number> {
  // Use a free exchange rate API
  try {
    const res = await fetch(
      "https://api.exchangerate-api.com/v4/latest/USD",
      { signal: AbortSignal.timeout(8000) }
    );
    if (res.ok) {
      const data = (await res.json()) as any;
      const rate = data?.rates?.ILS;
      if (typeof rate === "number" && rate > 0) return rate;
    }
  } catch { /* fall through */ }
  return 3.70; // fallback
}

async function getConfigValue(
  db: D1Database,
  key: string,
  fallback: string
): Promise<string> {
  const row = await db
    .prepare("SELECT value FROM platform_config WHERE key = ?")
    .bind(key)
    .first<{ value: string }>();
  return row?.value ?? fallback;
}

export async function runScheduledTasks(
  env: AppEnv["Bindings"],
  _cron: string
): Promise<void> {
  const db = env.DB;

  try {
    // 1. Fetch real market prices
    const [usdtUsd, usdIls] = await Promise.all([
      fetchUsdtUsdPrice(),
      fetchUsdIlsRate(),
    ]);

    if (!usdtUsd.ok) {
      console.error("[cron] Failed to fetch USDT/USD price from all sources");
      return;
    }

    // 2. Read admin-configured spread
    const buySpread = parseFloat(
      await getConfigValue(db, "buy_spread", "0.005")
    ); // 0.5%
    const sellSpread = parseFloat(
      await getConfigValue(db, "sell_spread", "0.005")
    ); // 0.5%

    const marketPriceUsd = usdtUsd.price;
    const marketPriceIls = marketPriceUsd * usdIls;

    // Platform prices = market price ± spread
    const buyPriceIls = marketPriceIls * (1 + buySpread);
    const sellPriceIls = marketPriceIls * (1 - sellSpread);

    // 3. Update market_price singleton
    await db
      .prepare(
        `UPDATE market_price SET usd_ils = ?, usdt_ils = ?, updated = datetime('now') WHERE id = 1`
      )
      .bind(usdIls, marketPriceIls)
      .run();

    // 4. Seed if not exists
    await db
      .prepare(
        `INSERT OR IGNORE INTO market_price (id, usd_ils, usdt_ils) VALUES (1, ?, ?)`
      )
      .bind(usdIls, marketPriceIls)
      .run();

    // 5. Store price history snapshot
    await db
      .prepare(
        `INSERT INTO price_history (source, pair, market_price, buy_price, sell_price, created_at)
         VALUES (?, 'USDT/ILS', ?, ?, ?, datetime('now'))`
      )
      .bind(
        usdtUsd.source,
        Math.round(marketPriceIls * 10000) / 10000,
        Math.round(buyPriceIls * 10000) / 10000,
        Math.round(sellPriceIls * 10000) / 10000
      )
      .run();

    // 6. Clean old history (keep last 30 days = ~720 hourly records)
    await db
      .prepare(
        `DELETE FROM price_history WHERE id NOT IN (
           SELECT id FROM price_history ORDER BY created_at DESC LIMIT 720
         )`
      )
      .run();

    // 7. Check price alerts
    const alerts = await db
      .prepare(
        `SELECT pa.*, u.username FROM price_alerts pa
         JOIN users u ON pa.username = u.username
         WHERE pa.active = 1 AND pa.triggered = 0`
      )
      .all<{ id: number; username: string; pair: string; direction: string; target_price: number }>();

    if (alerts.results) {
      for (const alert of alerts.results) {
        const shouldTrigger =
          (alert.direction === "ABOVE" && marketPriceIls >= alert.target_price) ||
          (alert.direction === "BELOW" && marketPriceIls <= alert.target_price);

        if (shouldTrigger) {
          await db
            .prepare(
              `UPDATE price_alerts SET triggered = 1, triggered_at = datetime('now') WHERE id = ?`
            )
            .bind(alert.id)
            .run();

          // Create notification
          const directionText =
            alert.direction === "ABOVE" ? "وصل إلى" : "نزل إلى";
          await db
            .prepare(
              `INSERT INTO notifications (username, title, message, seen, created)
               VALUES (?, ?, ?, 0, datetime('now'))`
            )
            .bind(
              alert.username,
              "تنبيه السعر 🔔",
              `السعر ${directionText} ${alert.target_price.toFixed(2)} ILS. السعر الحالي: ${marketPriceIls.toFixed(2)} ILS`
            )
            .run();
        }
      }
    }

    // 8. Store spread config defaults if missing
    await db
      .prepare(
        `INSERT OR IGNORE INTO platform_config (key, value) VALUES ('buy_spread', ?)`
      )
      .bind(String(buySpread))
      .run();
    await db
      .prepare(
        `INSERT OR IGNORE INTO platform_config (key, value) VALUES ('sell_spread', ?)`
      )
      .bind(String(sellSpread))
      .run();
    await db
      .prepare(
        `INSERT OR IGNORE INTO platform_config (key, value) VALUES ('market_source', ?)`
      )
      .bind(usdtUsd.source)
      .run();

    console.log(
      `[cron] Price updated: USDT/ILS=${marketPriceIls.toFixed(4)} (source=${usdtUsd.source}, USD/ILS=${usdIls.toFixed(4)}, buy=${buyPriceIls.toFixed(4)}, sell=${sellPriceIls.toFixed(4)})`
    );
  } catch (err: any) {
    console.error("[cron] Price update failed:", err?.message || err);
  }

  // === TRADE EXPIRATION CHECK ===
  try {
    const timeoutRow = await db
      .prepare("SELECT value FROM platform_config WHERE key = 'trade_timeout_minutes'")
      .first<{ value: string }>();
    const timeoutMinutes = parseInt(timeoutRow?.value ?? "30", 10) || 30;
    const cutoff = new Date(Date.now() - timeoutMinutes * 60 * 1000).toISOString();

    // Find PENDING trades that have expired (no payment sent within timeout)
    const expiredTrades = await db
      .prepare(
        `SELECT id, buyer, seller, amount, ad_id, escrow_status FROM trades
         WHERE status = 'PENDING' AND created <= ?`
      )
      .bind(cutoff)
      .all<{ id: number; buyer: string; seller: string; amount: number; ad_id: number; escrow_status: string }>();

    if (expiredTrades.results) {
      for (const trade of expiredTrades.results) {
        // ═══ CRITICAL FIX: Atomic conditional cancel prevents cron double-cancel ═══
        // First: atomically attempt to cancel (only succeeds if still PENDING)
        const cancelResult = await db
          .prepare(
            `UPDATE trades SET status = 'CANCELLED', escrow_status = CASE
               WHEN escrow_status = 'LOCKED' THEN 'REFUNDED'
               WHEN escrow_status = 'WAITING' THEN 'WAITING'
               ELSE escrow_status
             END WHERE id = ? AND status = 'PENDING'`
          )
          .bind(trade.id)
          .run();

        // Skip if another cron run or user action already handled this trade
        if (cancelResult.meta.changes === 0) {
          console.log(`[cron] Trade #${trade.id} already handled — skipping`);
          continue;
        }

        // Second: refund locked funds (after status is atomically set to CANCELLED)
        if (trade.escrow_status === "LOCKED") {
          try {
            const { escrowRefundSeller } = await import("./utils/db");
            await escrowRefundSeller({ DB: db } as any, trade.seller, trade.amount, trade.id);

            const { recordEscrowTransaction } = await import("./escrow");
            await recordEscrowTransaction(db, trade.id, "system", trade.amount, "REFUND", {
              reason: `انتهت مهلة الصفقة (${timeoutMinutes} دقيقة) — لم يتم تأكيد الدفع`,
            });
          } catch (e: any) {
            console.error(`[cron] Failed to refund expired trade #${trade.id}:`, e?.message);
          }
        }

        // Third: restore ad amount
        try {
          await db
            .prepare(
              "UPDATE ads SET amount = amount + ?, status = 'OPEN' WHERE id = ?"
            )
            .bind(trade.amount, trade.ad_id)
            .run();
        } catch { /* ad may have been deleted */ }

        // Notify buyer
        try {
          await db
            .prepare(
              "INSERT INTO notifications (username, title, message) VALUES (?, ?, ?)"
            )
            .bind(
              trade.buyer,
              "تم إلغاء الصفقة ⏰",
              `تم إلغاء الصفقة #${trade.id} تلقائياً لانتهاء المهلة. لم يتم تأكيد الدفع.`
            )
            .run();
        } catch { /* best effort */ }

        console.log(`[cron] Expired trade #${trade.id} — refunded ${trade.amount} USDT to ${trade.seller}`);
      }
    }
  } catch (err: any) {
    console.error("[cron] Trade expiration check failed:", err?.message || err);
  }
}
