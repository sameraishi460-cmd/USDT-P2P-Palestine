/**
 * Auth routes: register (email+password), login (username or email), logout, Telegram WebApp auth, admin login.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import {
  hashPassword, verifyPassword, signSession,
  generateCsrfToken, verifyTelegramInitData,
  randomToken, sha256Hex, randomSid,
} from "../utils/crypto";
import {
  setSessionCookie, clearSessionCookie, SESSION_COOKIE, getCookie, rateLimit,
  requireUser, requireCsrf,
} from "../middleware/auth";
import { formBody } from "../utils/body";
import { ensureWallet, auditLog, notify } from "../utils/db";
import { sendEmail, verificationEmailBody, resetPasswordEmailBody } from "../utils/email";

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
  if (password.length < 8) {
    return c.json({ error: "كلمة المرور يجب أن تكون 8 أحرف على الأقل" }, 400);
  }

  const existing = await c.env.DB.prepare("SELECT id FROM users WHERE username = ?").bind(username).first();
  if (existing) return c.json({ error: "اسم المستخدم موجود بالفعل" }, 409);

  // Check email uniqueness — handle missing email column gracefully
  let existingEmail;
  try {
    existingEmail = await c.env.DB.prepare("SELECT id FROM users WHERE email = ?").bind(email).first();
  } catch {
    // email column might not exist yet — skip uniqueness check
    existingEmail = null;
  }
  if (existingEmail) return c.json({ error: "البريد الإلكتروني مسجل بالفعل" }, 409);

  const hash = await hashPassword(password);
  let result;
  try {
    result = await c.env.DB.prepare(
      "INSERT INTO users (username, password, email) VALUES (?, ?, ?)"
    ).bind(username, hash, email).run();
  } catch (insertErr: any) {
    if (insertErr?.message?.includes("no such column") || insertErr?.message?.includes("SQLITE_ERROR")) {
      // email column missing — try without it, then add column
      try {
        result = await c.env.DB.prepare(
          "INSERT INTO users (username, password) VALUES (?, ?)"
        ).bind(username, hash).run();
      } catch {
        throw insertErr; // both failed, surface original error
      }
      // Now add the email column and set it
      try {
        await c.env.DB.prepare("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''").run();
      } catch { /* already exists */ }
      if (result?.meta?.last_row_id) {
        await c.env.DB.prepare("UPDATE users SET email = ? WHERE id = ?")
          .bind(email, Number(result.meta.last_row_id)).run();
      }
    } else {
      throw insertErr;
    }
  }

  await ensureWallet(c.env, username);

  const sid = randomSid();
  const token = await signSession(
    { sub: Number(result.meta.last_row_id), username, admin: false, sid },
    c.env.SECRET_KEY
  );
  setSessionCookie(c, token);
  // Persist session in DB for revocation support
  try {
    await c.env.DB.prepare(
      "INSERT INTO user_sessions (id, username, user_agent, ip, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
    ).bind(sid, username, c.req.header("User-Agent")?.slice(0, 200) || "", c.req.header("CF-Connecting-IP") || "").run();
  } catch { /* best effort */ }

  await auditLog(c, username, "user", "REGISTER", username);
  await logActivity(c.env, username, "REGISTER", c);
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
    try {
      const byEmail = await c.env.DB.prepare(
        "SELECT id, username, password, status FROM users WHERE email = ?"
      ).bind(identifier.toLowerCase()).first<{ id: number; username: string; password: string; status: string }>();
      if (byEmail) user = byEmail;
    } catch {
      // email column may not exist yet
    }
  }

  if (!user || !(await verifyPassword(password, user.password))) {
    return c.json({ error: "البريد الإلكتروني/اسم المستخدم أو كلمة المرور غير صحيحة" }, 401);
  }
  if (user.status === "BANNED") {
    return c.json({ error: "هذا الحساب محظور" }, 403);
  }

  const sid = randomSid();
  const token = await signSession(
    { sub: user.id, username: user.username, admin: user.status === "ADMIN", sid },
    c.env.SECRET_KEY
  );
  setSessionCookie(c, token);
  // Persist session in DB for revocation support
  try {
    await c.env.DB.prepare(
      "INSERT INTO user_sessions (id, username, user_agent, ip, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
    ).bind(sid, user.username, c.req.header("User-Agent")?.slice(0, 200) || "", c.req.header("CF-Connecting-IP") || "").run();
  } catch { /* best effort */ }
  await ensureWallet(c.env, user.username);
  await auditLog(c, user.username, "user", "LOGIN", user.username);
  await logActivity(c.env, user.username, "LOGIN", c);

  return c.json({ ok: true, csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY) });
});

// POST /api/auth/admin-login
auth.post("/admin-login", rateLimit(5, 300), async (c) => {
  const body = await formBody(c);
  const username = String(body.username ?? "").trim();
  const password = String(body.password ?? "");

  let adminUser: { id: number; username: string } | null = null;

  // Admin login: user must already be ADMIN in DB. Never auto-promote.
  const u = await c.env.DB.prepare(
    "SELECT id, username, password, status FROM users WHERE username = ? AND status = 'ADMIN'"
  ).bind(username).first<{ id: number; username: string; password: string; status: string }>();
  if (u && (await verifyPassword(password, u.password))) {
    adminUser = { id: u.id, username: u.username };
  }

  // First-time bootstrap: if no ADMIN exists yet and ADMIN_PASSWORD matches, allow creation
  if (!adminUser && c.env.ADMIN_PASSWORD && password === c.env.ADMIN_PASSWORD && username) {
    const existingAdminCount = await c.env.DB.prepare(
      "SELECT COUNT(*) AS cnt FROM users WHERE status = 'ADMIN'"
    ).first<{ cnt: number }>();
    if ((existingAdminCount?.cnt ?? 0) === 0) {
      // Bootstrap: create the first admin user
      const hash = await hashPassword(crypto.randomUUID());
      const res = await c.env.DB.prepare(
        "INSERT INTO users (username, password, status) VALUES (?, ?, 'ADMIN')"
      ).bind(username, hash).run();
      adminUser = { id: Number(res.meta.last_row_id), username };
    }
  }

  if (!adminUser) return c.json({ error: "بيانات الدخول غير صحيحة" }, 401);

  const sid = randomSid();
  const token = await signSession({ sub: adminUser.id, username: adminUser.username, admin: true, sid }, c.env.SECRET_KEY);
  setSessionCookie(c, token);
  try {
    await c.env.DB.prepare(
      "INSERT INTO user_sessions (id, username, user_agent, ip, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
    ).bind(sid, adminUser.username, c.req.header("User-Agent")?.slice(0, 200) || "", c.req.header("CF-Connecting-IP") || "").run();
  } catch { /* best effort */ }
  await auditLog(c, adminUser.username, "admin", "ADMIN_LOGIN", adminUser.username);
  await logActivity(c.env, adminUser.username, "ADMIN_LOGIN", c);

  return c.json({ ok: true, csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY) });
});

// POST /api/auth/logout
auth.post("/logout", requireCsrf, async (c) => {
  // Revoke server-side session if it has an SID
  const token = getCookie(c, SESSION_COOKIE);
  if (token) {
    try {
      const session = await (await import("../utils/crypto")).verifySession(token, c.env.SECRET_KEY);
      if (session?.sid) {
        await c.env.DB.prepare(
          "UPDATE user_sessions SET revoked = 1 WHERE id = ?"
        ).bind(session.sid).run();
      }
      await logActivity(c.env, session?.username || "unknown", "LOGOUT", c);
    } catch { /* best effort */ }
  }
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
  const sid = randomSid();
  const token = await signSession({ sub: user.id, username: user.username, admin: user.status === "ADMIN", sid }, c.env.SECRET_KEY);
  setSessionCookie(c, token);
  try {
    await c.env.DB.prepare(
      "INSERT INTO user_sessions (id, username, user_agent, ip, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
    ).bind(sid, user.username, c.req.header("User-Agent")?.slice(0, 200) || "", c.req.header("CF-Connecting-IP") || "").run();
  } catch { /* best effort */ }
  await auditLog(c, user.username, "user", "TELEGRAM_AUTH", `tg:${tgId}`);
  await logActivity(c.env, user.username, "TELEGRAM_LOGIN", c);

  return c.json({ ok: true, csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY) });
});

// GET /api/auth/me — session info
auth.get("/me", async (c) => {
  const token = getCookie(c, SESSION_COOKIE);
  if (!token) return c.json({ authenticated: false });
  const { verifySession } = await import("../utils/crypto");
  const session = await verifySession(token, c.env.SECRET_KEY);
  if (!session) return c.json({ authenticated: false });

  let user;
  try {
    user = await c.env.DB.prepare(
      "SELECT username, email, verified, rating, trades_count, status, first_name, telegram_id, created_at FROM users WHERE id = ?"
    ).bind(session.sub).first<any>();
  } catch {
    // Fallback: query without email column
    user = await c.env.DB.prepare(
      "SELECT username, verified, rating, trades_count, status, first_name, telegram_id, created_at FROM users WHERE id = ?"
    ).bind(session.sub).first<any>();
    if (user) user.email = '';
  }
  if (!user) return c.json({ authenticated: false });

  return c.json({
    authenticated: true,
    username: session.username,
    isAdmin: user.status === "ADMIN",
    ...user,
    csrf_token: await generateCsrfToken(token, c.env.SECRET_KEY),
  });
});

// POST /api/auth/telegram/link — generate a link code for logged-in users
// Returns a code that the user sends to the bot via /link <code>
auth.post("/telegram/link", rateLimit(5, 300), async (c) => {
  const token = getCookie(c, SESSION_COOKIE);
  if (!token) return c.json({ error: "غير مصرح" }, 401);
  const { verifySession } = await import("../utils/crypto");
  const session = await verifySession(token, c.env.SECRET_KEY);
  if (!session) return c.json({ error: "جلسة منتهية" }, 401);

  // Generate a 6-character alphanumeric code
  const code = Math.random().toString(36).substring(2, 8).toUpperCase();
  const expiresAt = new Date(Date.now() + 10 * 60 * 1000).toISOString(); // 10 minutes

  await c.env.DB.prepare(
    "INSERT INTO telegram_auth_codes (code, telegram_user_id, action, expires_at) VALUES (?, ?, 'link', ?)"
  ).bind(code, String(session.sub), expiresAt).run();

  return c.json({ ok: true, code, message: "أرسل هذا الكود للبوت: /link " + code });
});

// POST /api/auth/telegram/link/verify — verify a link code (called by webhook when user sends /link <code>)
auth.post("/telegram/link/verify", rateLimit(10, 60), async (c) => {
  const body = await formBody(c);
  const code = String(body.code ?? "").trim();
  const telegramUserId = String(body.telegram_user_id ?? "").trim();
  const telegramUsername = String(body.telegram_username ?? "").trim();

  if (!code || !telegramUserId) {
    return c.json({ error: "بيانات مفقودة" }, 400);
  }

  // Find the code
  const codeRow = await c.env.DB.prepare(
    "SELECT id, telegram_user_id, action, expires_at, used FROM telegram_auth_codes WHERE code = ?"
  ).bind(code).first<{ id: number; telegram_user_id: string; action: string; expires_at: string; used: number }>();

  if (!codeRow) return c.json({ error: "كود غير صالح" }, 404);
  if (codeRow.used) return c.json({ error: "تم استخدام الكود بالفعل" }, 409);
  if (new Date(codeRow.expires_at) < new Date()) return c.json({ error: "انتهت صلاحية الكود" }, 410);

  if (codeRow.action === "link") {
    const platformUserId = codeRow.telegram_user_id;

    // Check if this Telegram account is already linked to another user
    const existing = await c.env.DB.prepare(
      "SELECT id, username FROM users WHERE telegram_id = ?"
    ).bind(telegramUserId).first<{ id: number; username: string }>();
    if (existing && String(existing.id) !== platformUserId) {
      return c.json({ error: "هذا الحساب مرتبط بمستخدم آخر" }, 409);
    }

    // Link: update the platform user's telegram_id
    await c.env.DB.prepare(
      "UPDATE users SET telegram_id = ? WHERE id = ?"
    ).bind(telegramUserId, Number(platformUserId)).run();

    // Mark code as used
    await c.env.DB.prepare(
      "UPDATE telegram_auth_codes SET used = 1 WHERE id = ?"
    ).bind(codeRow.id).run();

    return c.json({ ok: true, message: "تم ربط الحساب بنجاح" });
  }

  if (codeRow.action === "login") {
    const platformUserId = codeRow.telegram_user_id;
    const user = await c.env.DB.prepare(
      "SELECT id, username, status FROM users WHERE id = ?"
    ).bind(Number(platformUserId)).first<{ id: number; username: string; status: string }>();

    if (!user) return c.json({ error: "المستخدم غير موجود" }, 404);
    if (user.status === "BANNED") return c.json({ error: "الحساب محظور" }, 403);

    await c.env.DB.prepare(
      "UPDATE telegram_auth_codes SET used = 1 WHERE id = ?"
    ).bind(codeRow.id).run();

    return c.json({ ok: true, username: user.username });
  }

  return c.json({ error: "نوع كود غير معروف" }, 400);
});

// ============================================================
// POST /api/auth/change-password — authenticated password change
// ============================================================
auth.post("/change-password", requireUser, requireCsrf, rateLimit(5, 300), async (c) => {
  const username = c.get("user")!.username;
  const body = await formBody(c);
  const currentPassword = String(body.current_password ?? "");
  const newPassword = String(body.new_password ?? "");

  if (!currentPassword || !newPassword) {
    return c.json({ error: "أدخل كلمة المرور الحالية والجديدة" }, 400);
  }
  if (newPassword.length < 8) {
    return c.json({ error: "كلمة المرور الجديدة يجب أن تكون 8 أحرف على الأقل" }, 400);
  }

  const user = await c.env.DB.prepare(
    "SELECT id, username, password FROM users WHERE username = ?"
  ).bind(username).first<{ id: number; username: string; password: string }>();
  if (!user) return c.json({ error: "المستخدم غير موجود" }, 404);

  if (!(await verifyPassword(currentPassword, user.password))) {
    return c.json({ error: "كلمة المرور الحالية غير صحيحة" }, 401);
  }

  const hash = await hashPassword(newPassword);
  await c.env.DB.prepare("UPDATE users SET password = ? WHERE id = ?")
    .bind(hash, user.id).run();

  // Invalidate other sessions (keep current one)
  const token = getCookie(c, SESSION_COOKIE);
  if (token) {
    const { verifySession } = await import("../utils/crypto");
    const session = await verifySession(token, c.env.SECRET_KEY);
    if (session?.sid) {
      await c.env.DB.prepare(
        "UPDATE user_sessions SET revoked = 1 WHERE username = ? AND id != ?"
      ).bind(username, session.sid).run();
    } else {
      await c.env.DB.prepare(
        "UPDATE user_sessions SET revoked = 1 WHERE username = ?"
      ).bind(username).run();
    }
  }

  await logActivity(c.env, username, "PASSWORD_CHANGED", c);
  await auditLog(c, username, "user", "PASSWORD_CHANGED", username);
  return c.json({ ok: true, message: "تم تغيير كلمة المرور بنجاح" });
});

// ============================================================
// POST /api/auth/forgot-password — send reset email
// ============================================================
auth.post("/forgot-password", rateLimit(3, 300), async (c) => {
  const body = await formBody(c);
  const email = String(body.email ?? "").trim().toLowerCase();

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return c.json({ error: "البريد الإلكتروني غير صالح" }, 400);
  }

  // Always return success to prevent user enumeration
  const user = await c.env.DB.prepare(
    "SELECT id, username, email FROM users WHERE email = ?"
  ).bind(email).first<{ id: number; username: string; email: string }>();

  if (user && user.email) {
    // Rate limit: max 3 reset requests per hour
    const recentResets = await c.env.DB.prepare(
      "SELECT COUNT(*) AS cnt FROM auth_tokens WHERE type = 'password_reset' AND username = ? AND created_at > datetime('now', '-1 hour')"
    ).bind(user.username).first<{ cnt: number }>();
    if ((recentResets?.cnt ?? 0) >= 3) {
      // Still return success to prevent enumeration
      return c.json({ ok: true, message: "إذا كان البريد مسجلاً، ستتلقى رسالة." });
    }

    const rawToken = randomToken(32);
    const tokenHash = await sha256Hex(rawToken);
    const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString(); // 1 hour

    await c.env.DB.prepare(
      "INSERT INTO auth_tokens (token_hash, type, username, expires_at) VALUES (?, 'password_reset', ?, ?)"
    ).bind(tokenHash, user.username, expiresAt).run();

    const appUrl = c.env.APP_URL || "https://usdt-p2p-palestine.sameraishi460.workers.dev";
    const resetLink = `${appUrl}/reset_password?token=${rawToken}`;
    await sendEmail(c.env, user.email, "إعادة تعيين كلمة المرور", resetPasswordEmailBody(resetLink));
    await logActivity(c.env, user.username, "PASSWORD_RESET_REQUESTED", c);
  }

  return c.json({ ok: true, message: "إذا كان البريد مسجلاً، ستتلقى رسالة." });
});

// ============================================================
// POST /api/auth/reset-password — apply reset token
// ============================================================
auth.post("/reset-password", rateLimit(5, 300), async (c) => {
  const body = await formBody(c);
  const rawToken = String(body.token ?? "").trim();
  const newPassword = String(body.new_password ?? "");
  const confirmPassword = String(body.confirm_password ?? "");

  if (!rawToken) return c.json({ error: "الرابط غير صالح" }, 400);
  if (newPassword.length < 8) return c.json({ error: "كلمة المرور يجب أن تكون 8 أحرف على الأقل" }, 400);
  if (newPassword !== confirmPassword) return c.json({ error: "كلمتا المرور غير متطابقتين" }, 400);

  const tokenHash = await sha256Hex(rawToken);
  const tokenRow = await c.env.DB.prepare(
    "SELECT id, username, used, expires_at FROM auth_tokens WHERE token_hash = ? AND type = 'password_reset'"
  ).bind(tokenHash).first<{ id: number; username: string; used: number; expires_at: string }>();

  if (!tokenRow) return c.json({ error: "الرابط غير صالح أو منتهي" }, 400);
  if (tokenRow.used) return c.json({ error: "تم استخدام هذا الرابط بالفعل" }, 409);
  if (new Date(tokenRow.expires_at) < new Date()) return c.json({ error: "انتهت صلاحية الرابط" }, 410);

  // Mark token as used + apply new password
  const hash = await hashPassword(newPassword);
  await c.env.DB.batch([
    c.env.DB.prepare("UPDATE auth_tokens SET used = 1 WHERE id = ?").bind(tokenRow.id),
    c.env.DB.prepare("UPDATE users SET password = ? WHERE username = ?").bind(hash, tokenRow.username),
  ]);

  // Invalidate all sessions for this user
  await c.env.DB.prepare("UPDATE user_sessions SET revoked = 1 WHERE username = ?")
    .bind(tokenRow.username).run();

  await logActivity(c.env, tokenRow.username, "PASSWORD_RESET", c);
  await auditLog(c, tokenRow.username, "user", "PASSWORD_RESET", tokenRow.username);
  return c.json({ ok: true, message: "تم إعادة تعيين كلمة المرور بنجاح. سجّل الدخول مرة أخرى." });
});

// ============================================================
// POST /api/auth/send-verification — send email verification
// ============================================================
auth.post("/send-verification", requireUser, rateLimit(3, 600), async (c) => {
  const username = c.get("user")!.username;
  const user = await c.env.DB.prepare(
    "SELECT id, username, email, email_verified FROM users WHERE username = ?"
  ).bind(username).first<{ id: number; username: string; email: string; email_verified: number }>();

  if (!user) return c.json({ error: "المستخدم غير موجود" }, 404);
  if (!user.email) return c.json({ error: "لم تُسجل بريداً إلكترونياً بعد" }, 400);
  if (user.email_verified) return c.json({ ok: true, message: "البريد موثق بالفعل" });

  // Rate limit: max 3 per hour
  const recent = await c.env.DB.prepare(
    "SELECT COUNT(*) AS cnt FROM auth_tokens WHERE type = 'email_verify' AND username = ? AND created_at > datetime('now', '-1 hour')"
  ).bind(username).first<{ cnt: number }>();
  if ((recent?.cnt ?? 0) >= 3) {
    return c.json({ error: "انتظر ساعة قبل إعادة الإرسال" }, 429);
  }

  const rawToken = randomToken(32);
  const tokenHash = await sha256Hex(rawToken);
  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(); // 24 hours

  await c.env.DB.prepare(
    "INSERT INTO auth_tokens (token_hash, type, username, expires_at) VALUES (?, 'email_verify', ?, ?)"
  ).bind(tokenHash, username, expiresAt).run();

  const appUrl = c.env.APP_URL || "https://usdt-p2p-palestine.sameraishi460.workers.dev";
  const verifyLink = `${appUrl}/verify_email?token=${rawToken}`;
  const result = await sendEmail(c.env, user.email, "توثيق البريد الإلكتروني", verificationEmailBody(verifyLink));

  if (!result.sent) {
    return c.json({ error: "البريد غير مهيأ في الخادم. تواصل مع الإدارة." }, 503);
  }

  await logActivity(c.env, username, "EMAIL_VERIFY_SENT", c);
  return c.json({ ok: true, message: "تم إرسال رسالة التوثيق" });
});

// ============================================================
// POST /api/auth/verify-email — apply email verification token
// ============================================================
auth.post("/verify-email", rateLimit(5, 300), async (c) => {
  const body = await formBody(c);
  const rawToken = String(body.token ?? "").trim();

  if (!rawToken) return c.json({ error: "الرابط غير صالح" }, 400);

  const tokenHash = await sha256Hex(rawToken);
  const tokenRow = await c.env.DB.prepare(
    "SELECT id, username, used, expires_at FROM auth_tokens WHERE token_hash = ? AND type = 'email_verify'"
  ).bind(tokenHash).first<{ id: number; username: string; used: number; expires_at: string }>();

  if (!tokenRow) return c.json({ error: "الرابط غير صالح أو منتهي" }, 400);
  if (tokenRow.used) return c.json({ error: "تم استخدام هذا الرابط بالفعل" }, 409);
  if (new Date(tokenRow.expires_at) < new Date()) return c.json({ error: "انتهت صلاحية الرابط" }, 410);

  await c.env.DB.batch([
    c.env.DB.prepare("UPDATE auth_tokens SET used = 1 WHERE id = ?").bind(tokenRow.id),
    c.env.DB.prepare("UPDATE users SET email_verified = 1 WHERE username = ?").bind(tokenRow.username),
  ]);

  await logActivity(c.env, tokenRow.username, "EMAIL_VERIFIED", c);
  await auditLog(c, tokenRow.username, "user", "EMAIL_VERIFIED", tokenRow.username);
  return c.json({ ok: true, message: "تم توثيق البريد الإلكتروني بنجاح" });
});

// ============================================================
// POST /api/auth/telegram-login — deep-link login for Telegram bot users
// The bot generates a one-time token and includes it in URL buttons.
// The frontend detects ?tg_token=XXX, calls this endpoint, and gets a session.
// ============================================================
auth.post("/telegram-login", rateLimit(10, 60), async (c) => {
  const body = await formBody(c);
  const token = String(body.token ?? "").trim();

  if (!token || token.length < 10) {
    return c.json({ error: "رمز غير صالح" }, 400);
  }

  // Look up the token
  const tokenRow = await c.env.DB.prepare(
    "SELECT id, telegram_user_id, username, used, expires_at FROM telegram_login_tokens WHERE token = ?"
  ).bind(token).first<{ id: number; telegram_user_id: string; username: string; used: number; expires_at: string }>();

  if (!tokenRow) {
    return c.json({ error: "رمز غير صالح" }, 401);
  }
  if (tokenRow.used) {
    return c.json({ error: "تم استخدام هذا الرمز بالفعل" }, 409);
  }
  if (new Date(tokenRow.expires_at) < new Date()) {
    return c.json({ error: "انتهت صلاحية الرمز" }, 410);
  }

  // Look up user
  const user = await c.env.DB.prepare(
    "SELECT id, username, status FROM users WHERE username = ?"
  ).bind(tokenRow.username).first<{ id: number; username: string; status: string }>();

  if (!user) {
    return c.json({ error: "المستخدم غير موجود" }, 404);
  }
  if (user.status === "BANNED") {
    return c.json({ error: "الحساب محظور" }, 403);
  }

  // Mark token as used (one-time only)
  await c.env.DB.prepare(
    "UPDATE telegram_login_tokens SET used = 1 WHERE id = ?"
  ).bind(tokenRow.id).run();

  // Create a web session (same as normal login)
  await ensureWallet(c.env, user.username);
  const sid = randomSid();
  const sessionToken = await signSession(
    { sub: user.id, username: user.username, admin: user.status === "ADMIN", sid },
    c.env.SECRET_KEY
  );
  setSessionCookie(c, sessionToken);
  try {
    await c.env.DB.prepare(
      "INSERT INTO user_sessions (id, username, user_agent, ip, created_at) VALUES (?, ?, ?, ?, datetime('now'))"
    ).bind(sid, user.username, c.req.header("User-Agent")?.slice(0, 200) || "", c.req.header("CF-Connecting-IP") || "").run();
  } catch { /* best effort */ }

  await auditLog(c, user.username, "user", "TELEGRAM_DEEPLINK_LOGIN", `tg:${tokenRow.telegram_user_id}`);
  await logActivity(c.env, user.username, "TELEGRAM_DEEPLINK_LOGIN", c);

  return c.json({
    ok: true,
    csrf_token: await generateCsrfToken(sessionToken, c.env.SECRET_KEY),
    username: user.username,
    isAdmin: user.status === "ADMIN",
  });
});

// ============================================================
// Helper: log activity
// ============================================================
async function logActivity(env: AppEnv["Bindings"], username: string, action: string, c: any): Promise<void> {
  try {
    const ip = c.req?.header?.("CF-Connecting-IP") || "";
    const ua = c.req?.header?.("User-Agent") || "";
    await env.DB.prepare(
      "INSERT INTO login_activity (username, action, ip, user_agent) VALUES (?, ?, ?, ?)"
    ).bind(username, action, ip, ua.slice(0, 200)).run();
  } catch { /* best effort */ }
}

export default auth;
