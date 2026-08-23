/**
 * Auth routes: register (email+password), login (username or email), logout, Telegram WebApp auth, admin login.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import {
  hashPassword, verifyPassword, signSession,
  generateCsrfToken, verifyTelegramInitData,
} from "../utils/crypto";
import {
  setSessionCookie, clearSessionCookie, SESSION_COOKIE, getCookie, rateLimit,
} from "../middleware/auth";
import { formBody } from "../utils/body";
import { ensureWallet, auditLog } from "../utils/db";

const auth = new Hono<AppEnv>();

// POST /api/auth/register
auth.post("/register", rateLimit(5, 300), async (c) => {
  const body = await formBody(c);
  const username = String(body.username ?? "").trim();
  const email = String(body.email ?? "").trim().toLowerCase();
  const password = String(body.password ?? "");

  if (!/^[a-zA-Z0-9_]{3,20}$/.test(username)) {
    return c.json({ error: "اسم المستخدم يجب أن يكون 3-20 حرفاً أو أرقاماً" }, 400);
  }
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return c.json({ error: "البريد الإلكتروني غير صالح" }, 400);
  }
  if (password.length < 6) {
    return c.json({ error: "كلمة المرور يجب أن تكون 6 أحرف على الأقل" }, 400);
  }

  const existing = await c.env.DB.prepare("SELECT id FROM users WHERE username = ?").bind(username).first();
  if (existing) return c.json({ error: "اسم المستخدم موجود بالفعل" }, 409);

  const existingEmail = await c.env.DB.prepare("SELECT id FROM users WHERE email = ?").bind(email).first();
  if (existingEmail) return c.json({ error: "البريد الإلكتروني مسجل بالفعل" }, 409);

  const hash = await hashPassword(password);
  const result = await c.env.DB.prepare(
    "INSERT INTO users (username, password, email) VALUES (?, ?, ?)"
  ).bind(username, hash, email).run();

  await ensureWallet(c.env, username);

  const token = await signSession(
    { sub: Number(result.meta.last_row_id), username, admin: false },
    c.env.SECRET_KEY
  );
  setSessionCookie(c, token);

  await auditLog(c, username, "user", "REGISTER", username);
  return c.json({ ok: true, csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY) });
});

// POST /api/auth/login — supports username OR email
auth.post("/login", rateLimit(10, 300), async (c) => {
  const body = await formBody(c);
  const identifier = String(body.username ?? body.email ?? "").trim();
  const password = String(body.password ?? "");

  if (!identifier || !password) {
    return c.json({ error: "البيانات مطلوبة" }, 400);
  }

  // Try username first, then email
  let user = await c.env.DB.prepare(
    "SELECT id, username, password, status FROM users WHERE username = ?"
  ).bind(identifier).first<{ id: number; username: string; password: string; status: string }>();

  if (!user) {
    const byEmail = await c.env.DB.prepare(
      "SELECT id, username, password, status FROM users WHERE email = ?"
    ).bind(identifier.toLowerCase()).first<{ id: number; username: string; password: string; status: string }>();
    if (byEmail) user = byEmail;
  }

  if (!user || !(await verifyPassword(password, user.password))) {
    return c.json({ error: "البريد الإلكتروني/اسم المستخدم أو كلمة المرور غير صحيحة" }, 401);
  }
  if (user.status === "BANNED") {
    return c.json({ error: "هذا الحساب محظور" }, 403);
  }

  const token = await signSession(
    { sub: user.id, username: user.username, admin: user.status === "ADMIN" },
    c.env.SECRET_KEY
  );
  setSessionCookie(c, token);
  await ensureWallet(c.env, user.username);
  await auditLog(c, user.username, "user", "LOGIN", user.username);

  return c.json({ ok: true, csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY) });
});

// POST /api/auth/admin-login
auth.post("/admin-login", rateLimit(5, 300), async (c) => {
  const body = await formBody(c);
  const username = String(body.username ?? "").trim();
  const password = String(body.password ?? "");

  let adminUser: { id: number; username: string } | null = null;

  if (c.env.ADMIN_PASSWORD && password === c.env.ADMIN_PASSWORD && username) {
    const u = await c.env.DB.prepare("SELECT id, username FROM users WHERE username = ?").bind(username).first<{ id: number; username: string }>();
    if (u) {
      await c.env.DB.prepare("UPDATE users SET status='ADMIN' WHERE id=?").bind(u.id).run();
      adminUser = u;
    } else {
      const hash = await hashPassword(crypto.randomUUID());
      const res = await c.env.DB.prepare("INSERT INTO users (username, password, status) VALUES (?, ?, 'ADMIN')").bind(username, hash).run();
      adminUser = { id: Number(res.meta.last_row_id), username };
    }
  } else {
    const u = await c.env.DB.prepare(
      "SELECT id, username, password, status FROM users WHERE username = ? AND status = 'ADMIN'"
    ).bind(username).first<{ id: number; username: string; password: string; status: string }>();
    if (u && (await verifyPassword(password, u.password))) {
      adminUser = { id: u.id, username: u.username };
    }
  }

  if (!adminUser) return c.json({ error: "بيانات الدخول غير صحيحة" }, 401);

  const token = await signSession({ sub: adminUser.id, username: adminUser.username, admin: true }, c.env.SECRET_KEY);
  setSessionCookie(c, token);
  await auditLog(c, adminUser.username, "admin", "ADMIN_LOGIN", adminUser.username);

  return c.json({ ok: true, csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY) });
});

// POST /api/auth/logout
auth.post("/logout", async (c) => {
  clearSessionCookie(c);
  return c.json({ ok: true });
});

// POST /api/auth/telegram — Telegram WebApp initData verification
auth.post("/telegram", rateLimit(10, 60), async (c) => {
  const body = await formBody(c);
  const initData = String(body.initData ?? "");

  if (!initData || !c.env.TELEGRAM_BOT_TOKEN) {
    return c.json({ error: "بيانات Telegram مفقودة" }, 400);
  }

  const check = await verifyTelegramInitData(initData, c.env.TELEGRAM_BOT_TOKEN);
  if (!check.valid || !check.user) {
    return c.json({ error: check.reason ?? "فشل التحقق من Telegram" }, 403);
  }

  const tgId = String(check.user.id);
  let username = String(check.user.username ?? "").trim() || `tg_${tgId}`;

  let user = await c.env.DB.prepare("SELECT id, username, status FROM users WHERE telegram_id = ?").bind(tgId).first<{ id: number; username: string; status: string }>();

  if (!user) {
    let candidate = username;
    for (let i = 0; i < 20; i++) {
      const exists = await c.env.DB.prepare("SELECT id FROM users WHERE username = ?").bind(candidate).first();
      if (!exists) break;
      candidate = `${username}_${Math.floor(Math.random() * 10000)}`;
    }
    const res = await c.env.DB.prepare(
      "INSERT INTO users (username, password, telegram_id, first_name) VALUES (?, ?, ?, ?)"
    ).bind(candidate, await hashPassword(tgId + ":" + crypto.randomUUID()), tgId, String(check.user.first_name ?? "")).run();
    user = { id: Number(res.meta.last_row_id), username: candidate, status: "ACTIVE" };
  }

  if (user.status === "BANNED") return c.json({ error: "هذا الحساب محظور" }, 403);

  await ensureWallet(c.env, user.username);
  const token = await signSession({ sub: user.id, username: user.username, admin: user.status === "ADMIN" }, c.env.SECRET_KEY);
  setSessionCookie(c, token);
  await auditLog(c, user.username, "user", "TELEGRAM_AUTH", `tg:${tgId}`);

  return c.json({ ok: true, csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY) });
});

// GET /api/auth/me — session info
auth.get("/me", async (c) => {
  const token = getCookie(c, SESSION_COOKIE);
  if (!token) return c.json({ authenticated: false });
  const { verifySession } = await import("../utils/crypto");
  const session = await verifySession(token, c.env.SECRET_KEY);
  if (!session) return c.json({ authenticated: false });

  const user = await c.env.DB.prepare(
    "SELECT username, email, verified, rating, trades_count, status, first_name, telegram_id, created_at FROM users WHERE id = ?"
  ).bind(session.sub).first<any>();
  if (!user) return c.json({ authenticated: false });

  return c.json({
    authenticated: true,
    username: session.username,
    isAdmin: user.status === "ADMIN",
    ...user,
    csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY),
  });
});

export default auth;
