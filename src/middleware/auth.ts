/**
 * Middleware: auth (session + admin), security headers, rate limiting.
 */
import { Context, Next } from "hono";
import type { AppEnv } from "../types";
import { verifySession, verifyCsrfToken } from "../utils/crypto";

export const SESSION_COOKIE = "usdt_session";

// ============================================================
// AUTH MIDDLEWARE
// ============================================================

export async function requireUser(c: Context<AppEnv>, next: Next) {
  const token = getCookie(c, SESSION_COOKIE);
  if (!token) return c.json({ error: "غير مسجل الدخول" }, 401);
  const session = await verifySession(token, c.env.SECRET_KEY);
  if (!session) return c.json({ error: "انتهت الجلسة، سجل الدخول مرة أخرى" }, 401);
  c.set("user", { id: session.sub, username: session.username, isAdmin: session.admin });
  await next();
}

export async function requireAdmin(c: Context<AppEnv>, next: Next) {
  const token = getCookie(c, SESSION_COOKIE);
  if (!token) return c.json({ error: "غير مصرح" }, 401);
  const session = await verifySession(token, c.env.SECRET_KEY);
  if (!session) return c.json({ error: "انتهت الجلسة" }, 401);

  // SERVER-SIDE admin enforcement: verify against DB, not just JWT claim.
  const user = await c.env.DB.prepare(
    "SELECT id, username, status FROM users WHERE id = ?"
  ).bind(session.sub).first<{ id: number; username: string; status: string }>();
  if (!user || user.status !== "ADMIN") {
    return c.json({ error: "غير مصرح لك بالوصول" }, 403);
  }
  c.set("user", { id: user.id, username: user.username, isAdmin: true });
  await next();
}

// CSRF check for state-changing requests (cookie-authenticated)
export async function requireCsrf(c: Context<AppEnv>, next: Next) {
  if (["POST", "PUT", "DELETE"].includes(c.req.method)) {
    // Telegram webhook uses its own secret-token validation; skip cookie CSRF there
    const headerToken = c.req.header("X-CSRF-Token") || "";
    const bodyToken = await tryGetFormCsrf(c);
    const token = headerToken || bodyToken;
    const sessionToken = getCookie(c, SESSION_COOKIE) || "";
    if (!sessionToken || !token) {
      return c.json({ error: "CSRF token missing" }, 403);
    }
    const ok = await verifyCsrfToken(token, sessionToken, c.env.SECRET_KEY);
    if (!ok) return c.json({ error: "CSRF token invalid" }, 403);
  }
  await next();
}

async function tryGetFormCsrf(c: Context<AppEnv>): Promise<string> {
  try {
    const ct = c.req.header("Content-Type") || "";
    if (ct.includes("application/x-www-form-urlencoded")) {
      const form = await c.req.parseBody();
      const v = form["_csrf_token"];
      return typeof v === "string" ? v : "";
    }
  } catch { /* not a form */ }
  return "";
}

// ============================================================
// SECURITY HEADERS
// ============================================================

export async function securityHeaders(c: Context<AppEnv>, next: Next) {
  await next();
  c.header("X-Content-Type-Options", "nosniff");
  c.header("X-Frame-Options", "DENY");
  c.header("Referrer-Policy", "strict-origin-when-cross-origin");
  c.header(
    "Content-Security-Policy",
    "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'"
  );
  c.header("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  if (c.env.ENVIRONMENT === "production") {
    c.header("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  }
}

// ============================================================
// RATE LIMITING (KV-based sliding window)
// ============================================================

export function rateLimit(maxRequests = 10, windowSeconds = 60) {
  return async (c: Context<AppEnv>, next: Next) => {
    const ip = c.req.header("CF-Connecting-IP") || "unknown";
    const route = new URL(c.req.url).pathname;
    const key = `rl:${ip}:${route}:${Math.floor(Date.now() / (windowSeconds * 1000))}`;
    try {
      const countStr = await c.env.RATE_LIMIT.get(key);
      const count = countStr ? parseInt(countStr, 10) : 0;
      if (count >= maxRequests) {
        return c.json({ error: "تم تجاوز الحد المسموح، حاول لاحقاً" }, 429);
      }
      await c.env.RATE_LIMIT.put(key, String(count + 1), { expirationTtl: windowSeconds });
    } catch {
      // KV failure should never block traffic entirely
    }
    await next();
  };
}

// ============================================================
// HELPERS
// ============================================================

export function getCookie(c: Context<AppEnv>, name: string): string {
  const raw = c.req.header("Cookie") || "";
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return "";
}

export function setSessionCookie(c: Context<AppEnv>, token: string) {
  const secure = c.env.ENVIRONMENT === "production";
  c.header(
    "Set-Cookie",
    `${SESSION_COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax${secure ? "; Secure" : ""}; Max-Age=${30 * 24 * 3600}`
  );
}

export function clearSessionCookie(c: Context<AppEnv>) {
  c.header("Set-Cookie", `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`);
}
