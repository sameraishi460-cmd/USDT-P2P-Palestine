/**
 * Shared type definitions for Cloudflare bindings.
 */

export type Bindings = {
  DB: D1Database;
  R2: R2Bucket;
  RATE_LIMIT: KVNamespace;
  ASSETS: Fetcher;  // Cloudflare static assets binding (frontend/)

  // Secrets (set via `wrangler secret put`)
  SECRET_KEY: string;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_WEBHOOK_SECRET: string;
  ADMIN_PASSWORD: string;

  // Vars
  ENVIRONMENT: string;
  PLATFORM_WALLET: string;
  USDT_CONTRACT: string;
  BSC_RPC_URL: string;
  USDT_DECIMALS: string;
  TELEGRAM_ADMIN_ID: string;
  APP_URL: string; // public Pages frontend URL
};

export type Variables = {
  user?: SessionUser;
};

export type SessionUser = {
  id: number;
  username: string;
  isAdmin: boolean;
};

export type AppEnv = { Bindings: Bindings; Variables: Variables };
