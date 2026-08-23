/**
 * Cloudflare Cron Triggers — replaces the Python background threads.
 *
 * Scheduled jobs (wrangler.toml):
 *   - every 30 min: update market price (with source fallback)
 *   - hourly: expire stale trades / old rate-limit keys are self-expiring in KV
 *
 * RULES:
 *   - A failed price update must NEVER take the site down.
 *   - Last known good price stays in D1 until a fresh one succeeds.
 */
import type { AppEnv } from "../types";

type PriceSource = { name: string; url: string; extract: (j: any) => number | null };

const SOURCES: PriceSource[] = [
  {
    name: "coingecko",
    url: "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=usd",
    extract: (j) => (typeof j?.tether?.usd === "number" ? j.tether.usd : null),
  },
  {
    name: "binance",
    url: "https://api.binance.com/api/v3/ticker/price?symbol=USDTTRY",
    // Not used for USD directly; kept as connectivity probe only.
    extract: () => null,
  },
];

async function fetchUsdtUsd(): Promise<{ usd: number | null; source: string }> {
  for (const src of SOURCES) {
    try {
      const res = await fetch(src.url, {
        signal: AbortSignal.timeout(8000),
        headers: { Accept: "application/json" },
      });
      if (!res.ok) continue;
      const json = await res.json<any>();
      const usd = src.extract(json);
      if (usd && usd > 0.5 && usd < 2) return { usd, source: src.name };
    } catch {
      continue; // try next source
    }
  }
  return { usd: null, source: "none" };
}

/** Update market_price row id=1. Keeps previous values on total failure. */
export async function updateMarketPrice(env: AppEnv["Bindings"]): Promise<void> {
  const { usd, source } = await fetchUsdtUsd();
  if (usd === null) {
    console.log("[cron] all price sources failed — keeping last known price");
    return;
  }

  // USDT/ILS ≈ USD/ILS with a small platform spread; admin can override manually.
  const usdIlsRow = await env.DB.prepare(
    "SELECT usd_ils FROM market_price WHERE id = 1"
  ).first<{ usd_ils: number }>();
  const baseUsdIls = usdIlsRow?.usd_ils && usdIlsRow.usd_ils > 1 ? usdIlsRow.usd_ils : 3.7;

  await env.DB.prepare(
    `UPDATE market_price SET usdt_ils = ?, updated = datetime('now') WHERE id = 1`
  ).bind(Math.round(usd * baseUsdIls * 100) / 100).run();

  console.log(`[cron] price updated from ${source}: USDT=${usd}`);
}

/** Cancel trades stuck in PENDING beyond the configured timeout (default 24h). */
export async function expireStaleTrades(env: AppEnv["Bindings"]): Promise<void> {
  const result = await env.DB.prepare(
    `UPDATE trades SET status = 'CANCELLED', escrow_status = 'REFUNDED'
     WHERE status = 'PENDING'
       AND created < datetime('now', '-24 hours')`
  ).run();

  if ((result.meta?.changes ?? 0) > 0) {
    console.log(`[cron] expired ${result.meta?.changes} stale pending trades`);
  }
}

/** Entry point wired into the Worker's scheduled() handler. */
export async function runScheduledTasks(env: AppEnv["Bindings"], cron: string): Promise<void> {
  try {
    await updateMarketPrice(env);
  } catch (e) {
    console.error("[cron] price update error:", e);
  }
  try {
    await expireStaleTrades(env);
  } catch (e) {
    console.error("[cron] trade expiry error:", e);
  }
}
