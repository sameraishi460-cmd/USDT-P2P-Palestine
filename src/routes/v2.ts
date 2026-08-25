/**
 * V2 Advanced Features: Trust, Verification, Fraud, Referrals, VIP, Promo, Featured, Analytics
 *
 * Exports registerV2Routes(app) which adds routes directly to the main Hono app
 * under /api/v2/* — avoids app.route() sub-router catch-all interception.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireUser, requireCsrf, requireAdmin, rateLimit } from "../middleware/auth";
import { auditLog, notify, getConfig, setConfig } from "../utils/db";
import { recalcTrust, getTrust, getVipLevel } from "../utils/trust";
import { formBody } from "../utils/body";

export function registerV2Routes(app: Hono<AppEnv>) {

  // ============================================================
  // TRUST & REPUTATION
  // ============================================================

  app.get("/api/v2/trust/:username", async (c) => {
    const username = c.req.param("username") ?? "";
    const trust = await getTrust(c.env, username);
    const vip = getVipLevel(trust);
    const user = await c.env.DB.prepare(
      "SELECT username, first_name, verified, created_at FROM users WHERE username = ?"
    ).bind(username).first<any>();
    if (!user) return c.json({ error: "المستخدم غير موجود" }, 404);
    return c.json({ ok: true, trust: trust || { trust_score: 50, total_ratings: 0, avg_rating: 0, completed_trades: 0, cancelled_trades: 0, disputed_trades: 0, completion_rate: 0, account_age_days: 0 }, vip, user });
  });

  app.post("/api/v2/reviews/:tradeId", requireUser, requireCsrf, async (c) => {
    const tradeId = Number(c.req.param("tradeId"));
    const from = c.get("user")!.username;

    const trade = await c.env.DB.prepare(
      "SELECT * FROM trades WHERE id = ? AND status = 'COMPLETED'"
    ).bind(tradeId).first<any>();
    if (!trade) return c.json({ error: "الصفقة غير موجودة أو غير مكتملة" }, 404);
    if (trade.buyer !== from && trade.seller !== from) return c.json({ error: "غير مصرح" }, 403);
    const to = trade.buyer === from ? trade.seller : trade.buyer;

    const already = await c.env.DB.prepare(
      "SELECT id FROM reviews WHERE trade_id = ? AND from_user = ?"
    ).bind(tradeId, from).first();
    if (already) return c.json({ error: "قيّمت هذه الصفقة بالفعل" }, 409);

    const body = await formBody(c);
    const rating = parseInt(String(body.rating ?? ""), 10);
    const comment = String(body.comment ?? "").trim().slice(0, 300);
    if (!(rating >= 1 && rating <= 5)) return c.json({ error: "التقييم يجب أن يكون من 1 إلى 5" }, 400);

    await c.env.DB.batch([
      c.env.DB.prepare(
        "INSERT INTO reviews (trade_id, from_user, to_user, rating, comment) VALUES (?, ?, ?, ?, ?)"
      ).bind(tradeId, from, to, rating, comment),
      c.env.DB.prepare(
        `UPDATE users SET rating = (SELECT AVG(rating) FROM reviews WHERE to_user = ?) WHERE username = ?`
      ).bind(to, to),
    ]);

    await recalcTrust(c.env, to);
    await auditLog(c, from, "user", "REVIEW", `trade:${tradeId}`, `${rating}⭐`);
    return c.json({ ok: true });
  });

  // ============================================================
  // VERIFICATION SYSTEM
  // ============================================================

  app.post("/api/v2/verify/request", requireUser, requireCsrf, rateLimit(3, 600), async (c) => {
    const username = c.get("user")!.username;
    const body = await formBody(c);
    const docType = String(body.document_type ?? "").trim();
    const uploadId = String(body.upload_id ?? "").trim();
    const fullName = String(body.full_name ?? "").trim();
    const country = String(body.country ?? "").trim();
    const dob = String(body.dob ?? "").trim();

    // Validate required fields
    if (!docType || !['passport', 'national_id', 'driving_license'].includes(docType)) {
      return c.json({ error: "نوع الوثيقة غير صالح" }, 400);
    }
    if (!uploadId) return c.json({ error: "يجب رفع صورة الوثيقة" }, 400);
    if (!fullName || fullName.length < 3) return c.json({ error: "الاسم الكامل مطلوب" }, 400);
    if (!country) return c.json({ error: "الدولة مطلوبة" }, 400);
    if (!dob) return c.json({ error: "تاريخ الميلاد مطلوب" }, 400);

    // Verify the upload belongs to this user
    const upload = await c.env.DB.prepare(
      "SELECT id, owner, kind FROM uploads WHERE id = ?"
    ).bind(uploadId).first<{ id: string; owner: string; kind: string }>();
    if (!upload || upload.owner !== username) {
      return c.json({ error: "الملف غير صالح" }, 400);
    }
    if (upload.kind !== "kyc-documents") {
      return c.json({ error: "يجب أن يكون الملف وثيقة هوية" }, 400);
    }

    // Check for existing PENDING request
    const existing = await c.env.DB.prepare(
      "SELECT id FROM verification_requests WHERE username = ? AND status = 'PENDING'"
    ).bind(username).first();
    if (existing) return c.json({ error: "لديك طلب توثيق قيد المراجعة بالفعل" }, 409);

    await c.env.DB.prepare(
      `INSERT INTO verification_requests (username, document_type, upload_id, full_name, country, dob, status)
       VALUES (?, ?, ?, ?, ?, ?, 'PENDING')`
    ).bind(username, docType, uploadId, fullName, country, dob).run();

    await auditLog(c, username, "user", "KYC_SUBMITTED", username, `${docType} by ${fullName}`);
    await notify(c.env, username, "تم استلام طلب التوثيق 📋", "سيتم مراجعة وثيقتك من الإدارة.");
    return c.json({ ok: true, message: "تم استلام طلب التوثيق بنجاح" });
  });

  app.get("/api/v2/verify/status", requireUser, async (c) => {
    const username = c.get("user")!.username;
    const req = await c.env.DB.prepare(
      `SELECT id, status, document_type, upload_id, full_name, country, dob,
              admin_note, reviewed_at, created_at
       FROM verification_requests WHERE username = ? ORDER BY id DESC LIMIT 1`
    ).bind(username).first();
    const user = await c.env.DB.prepare("SELECT verified FROM users WHERE username = ?").bind(username).first<any>();
    return c.json({ ok: true, verified: user?.verified || 0, request: req || null });
  });

  // ============================================================
  // REFERRAL SYSTEM
  // ============================================================

  app.get("/api/v2/referral/my", requireUser, async (c) => {
    const username = c.get("user")!.username;
    let code = await c.env.DB.prepare("SELECT * FROM referral_codes WHERE username = ?").bind(username).first();
    if (!code) {
      const newCode = "REF-" + username.toUpperCase().slice(0, 8) + Math.floor(Math.random() * 1000);
      await c.env.DB.prepare("INSERT OR IGNORE INTO referral_codes (code, username) VALUES (?, ?)").bind(newCode, username).run();
      code = await c.env.DB.prepare("SELECT * FROM referral_codes WHERE username = ?").bind(username).first();
    }
    const referred = await c.env.DB.prepare(
      "SELECT referred, status, completed_trades, earnings, created_at FROM referrals WHERE referrer = ? ORDER BY id DESC"
    ).bind(username).all();
    return c.json({ ok: true, code: code?.code, total_referred: code?.total_referred || 0, total_earnings: code?.total_earnings || 0, referrals: referred.results ?? [] });
  });

  app.post("/api/v2/referral/apply", requireUser, requireCsrf, async (c) => {
    const username = c.get("user")!.username;
    const body = await formBody(c);
    const code = String(body.code ?? "").trim().toUpperCase();
    if (!code) return c.json({ error: "كود الإحالة مطلوب" }, 400);

    const codeRow = await c.env.DB.prepare("SELECT * FROM referral_codes WHERE code = ?").bind(code).first<any>();
    if (!codeRow) return c.json({ error: "كود الإحالة غير صالح" }, 404);
    if (codeRow.username === username) return c.json({ error: "لا يمكنك إحالة نفسك" }, 400);

    const existing = await c.env.DB.prepare("SELECT id FROM referrals WHERE referred = ?").bind(username).first();
    if (existing) return c.json({ error: "تم استخدام كود إحالة بالفعل" }, 409);

    await c.env.DB.batch([
      c.env.DB.prepare("INSERT INTO referrals (referrer, referred, referral_code) VALUES (?, ?, ?)").bind(codeRow.username, username, code),
      c.env.DB.prepare("UPDATE referral_codes SET total_referred = total_referred + 1 WHERE code = ?").bind(code),
    ]);

    return c.json({ ok: true });
  });

  // ============================================================
  // PROMO CODES
  // ============================================================

  app.post("/api/v2/promo/validate", requireUser, requireCsrf, async (c) => {
    const body = await formBody(c);
    const code = String(body.code ?? "").trim().toUpperCase();
    const tradeAmount = parseFloat(String(body.amount ?? "0"));

    if (!code) return c.json({ error: "كود الخصم مطلوب" }, 400);

    const promo = await c.env.DB.prepare(
      "SELECT * FROM promo_codes WHERE code = ? AND active = 1"
    ).bind(code).first<any>();
    if (!promo) return c.json({ error: "كود الخصم غير صالح" }, 404);

    if (promo.expires_at && new Date(promo.expires_at) < new Date()) {
      return c.json({ error: "انتهت صلاحية كود الخصم" }, 400);
    }
    if (promo.max_uses > 0 && promo.used_count >= promo.max_uses) {
      return c.json({ error: "تم استخدام الكود بالفعل" }, 400);
    }
    if (tradeAmount < promo.min_trade_amount) {
      return c.json({ error: `الحد الأدنى للمعاملة ${promo.min_trade_amount} USDT` }, 400);
    }

    let discount = 0;
    if (promo.discount_type === "PERCENT") {
      discount = tradeAmount * (promo.discount_value / 100);
      if (promo.max_discount > 0) discount = Math.min(discount, promo.max_discount);
    } else {
      discount = Math.min(promo.discount_value, tradeAmount);
    }

    return c.json({ ok: true, discount: Math.round(discount * 100) / 100, promo_id: promo.id });
  });

  // ============================================================
  // FEATURED ADS
  // ============================================================

  app.get("/api/v2/featured", async (c) => {
    const rows = await c.env.DB.prepare(`
      SELECT a.*, u.verified, u.rating, u.trades_count, fa.featured_by, fa.end_date
      FROM featured_ads fa
      JOIN ads a ON fa.ad_id = a.id
      JOIN users u ON a.user = u.username
      WHERE fa.active = 1 AND a.status = 'OPEN'
      AND (fa.end_date IS NULL OR fa.end_date > datetime('now'))
      ORDER BY fa.created_at DESC LIMIT 20
    `).all();
    return c.json({ ok: true, featured: rows.results ?? [] });
  });

  // ============================================================
  // ADMIN: V2 Management
  // ============================================================

  // ── Admin V2 routes all require verified ADMIN status ──────────
  app.use("/api/v2/admin/*", async (c, next) => {
    const { getCookie, isSessionActive } = await import("../middleware/auth");
    const { verifySession } = await import("../utils/crypto");
    const token = getCookie(c, "usdt_session");
    if (!token) return c.json({ error: "غير مصرح" }, 401);
    const session = await verifySession(token, c.env.SECRET_KEY);
    if (!session) return c.json({ error: "انتهت الجلسة" }, 401);
    // Server-side session revocation check
    if (!(await isSessionActive(c.env.DB, session))) {
      return c.json({ error: "انتهت الجلسة" }, 401);
    }
    const user = await c.env.DB.prepare("SELECT id, username, status FROM users WHERE id = ?")
      .bind(session.sub).first<{ id: number; username: string; status: string }>();
    if (!user || user.status !== "ADMIN") return c.json({ error: "غير مصرح لك بالوصول" }, 403);
    c.set("user", { id: user.id, username: user.username, isAdmin: true });
    await next();
  });

  app.get("/api/v2/admin/verifications", async (c) => {
    const rows = await c.env.DB.prepare(
      `SELECT vr.*, u.email, u.verified AS user_verified
       FROM verification_requests vr
       LEFT JOIN users u ON vr.username = u.username
       ORDER BY vr.id DESC LIMIT 100`
    ).all();
    return c.json({ ok: true, requests: rows.results ?? [] });
  });

  app.post("/api/v2/admin/verify/:id/approve", requireCsrf, async (c) => {
    const id = Number(c.req.param("id"));
    const req = await c.env.DB.prepare("SELECT * FROM verification_requests WHERE id = ?").bind(id).first<any>();
    if (!req) return c.json({ error: "غير موجود" }, 404);
    await c.env.DB.batch([
      c.env.DB.prepare("UPDATE verification_requests SET status='APPROVED', reviewed_by=?, reviewed_at=datetime('now') WHERE id=?").bind(c.get("user")!.username, id),
      c.env.DB.prepare("UPDATE users SET verified=1 WHERE username=?").bind(req.username),
    ]);
    await notify(c.env, req.username, "تم توثيق حسابك ✅", "أصبحت الآن تاجراً موثقاً.");
    await auditLog(c, c.get("user")!.username, "admin", "VERIFY_APPROVE", req.username);
    return c.json({ ok: true });
  });

  app.post("/api/v2/admin/verify/:id/reject", requireCsrf, async (c) => {
    const id = Number(c.req.param("id"));
    const body = await formBody(c);
    const note = String(body.note ?? "").slice(0, 300);
    const req = await c.env.DB.prepare("SELECT * FROM verification_requests WHERE id = ?").bind(id).first<any>();
    if (!req) return c.json({ error: "غير موجود" }, 404);
    await c.env.DB.prepare(
      "UPDATE verification_requests SET status='REJECTED', admin_note=?, reviewed_by=?, reviewed_at=datetime('now') WHERE id=?"
    ).bind(note, c.get("user")!.username, id).run();
    await notify(c.env, req.username, "تم رفض طلب التوثيق ❌", note || "لم يتم تلبية الشروط المطلوبة.");
    await auditLog(c, c.get("user")!.username, "admin", "VERIFY_REJECT", req.username, note);
    return c.json({ ok: true });
  });

  app.get("/api/v2/admin/fraud", async (c) => {
    const rows = await c.env.DB.prepare("SELECT * FROM fraud_log ORDER BY id DESC LIMIT 100").all();
    return c.json({ ok: true, logs: rows.results ?? [] });
  });

  app.get("/api/v2/admin/risks", async (c) => {
    const rows = await c.env.DB.prepare(
      `SELECT ur.*, u.status FROM user_risk ur JOIN users u ON ur.username = u.username
       ORDER BY ur.risk_score DESC LIMIT 100`
    ).all();
    return c.json({ ok: true, risks: rows.results ?? [] });
  });

  app.post("/api/v2/admin/users/:username/freeze", requireCsrf, async (c) => {
    const username = c.req.param("username") ?? "";
    await c.env.DB.prepare("UPDATE users SET status='FROZEN' WHERE username=? AND status != 'ADMIN'").bind(username).run();
    await notify(c.env, username, "تم تجميد حسابك ❄️", "تواصل مع الإدارة لتفعيل حسابك.");
    await auditLog(c, c.get("user")!.username, "admin", "FREEZE_USER", username);
    return c.json({ ok: true });
  });

  app.post("/api/v2/admin/users/:username/unfreeze", requireCsrf, async (c) => {
    const username = c.req.param("username") ?? "";
    await c.env.DB.prepare("UPDATE users SET status='ACTIVE' WHERE username=?").bind(username).run();
    await notify(c.env, username, "تم تفعيل حسابك ✅", "مرحباً بعودتك.");
    await auditLog(c, c.get("user")!.username, "admin", "UNFREEZE_USER", username);
    return c.json({ ok: true });
  });

  app.post("/api/v2/admin/promos", requireCsrf, async (c) => {
    const body = await formBody(c);
    const code = String(body.code ?? "").trim().toUpperCase();
    const discountType = body.discount_type === "FIXED" ? "FIXED" : "PERCENT";
    const discountValue = parseFloat(String(body.discount_value ?? "0"));
    const maxDiscount = parseFloat(String(body.max_discount ?? "0")) || 0;
    const minTrade = parseFloat(String(body.min_trade_amount ?? "0")) || 0;
    const maxUses = parseInt(String(body.max_uses ?? "0"), 10) || 0;
    const expiresAt = String(body.expires_at ?? "").trim() || null;

    if (!code || discountValue <= 0) return c.json({ error: "بيانات غير صحيحة" }, 400);

    try {
      await c.env.DB.prepare(
        `INSERT INTO promo_codes (code, discount_type, discount_value, max_discount, min_trade_amount, max_uses, expires_at, created_by)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(code, discountType, discountValue, maxDiscount, minTrade, maxUses, expiresAt, c.get("user")!.username).run();
    } catch (e: any) {
      if (e?.message?.includes("UNIQUE")) return c.json({ error: "الكود موجود بالفعل" }, 409);
      throw e;
    }

    await auditLog(c, c.get("user")!.username, "admin", "PROMO_CREATE", code);
    return c.json({ ok: true });
  });

  app.post("/api/v2/admin/featured/:adId/toggle", requireCsrf, async (c) => {
    const adId = Number(c.req.param("adId"));
    const body = await formBody(c);
    const endDate = String(body.end_date ?? "").trim() || null;

    const existing = await c.env.DB.prepare("SELECT * FROM featured_ads WHERE ad_id = ? AND active = 1").bind(adId).first();
    if (existing) {
      await c.env.DB.prepare("UPDATE featured_ads SET active = 0 WHERE ad_id = ?").bind(adId).run();
      return c.json({ ok: true, featured: false });
    }

    await c.env.DB.prepare(
      "INSERT INTO featured_ads (ad_id, featured_by, end_date) VALUES (?, ?, ?)"
    ).bind(adId, c.get("user")!.username, endDate).run();
    await auditLog(c, c.get("user")!.username, "admin", "FEATURE_AD", `ad:${adId}`);
    return c.json({ ok: true, featured: true });
  });

  app.get("/api/v2/admin/analytics", async (c) => {
    const db = c.env.DB;
    const period = c.req.query("period") || "all";

    let dateFilter = "";
    if (period === "today") dateFilter = "AND created_at >= date('now')";
    else if (period === "7days") dateFilter = "AND created_at >= date('now', '-7 days')";
    else if (period === "30days") dateFilter = "AND created_at >= date('now', '-30 days')";

    const [newUsers, completedTrades, dailyVolume, platformFees, deposits, withdrawals] = await Promise.all([
      db.prepare(`SELECT COUNT(*) FROM users WHERE 1=1 ${dateFilter.replace("created_at", "created_at")}`).first<number>(),
      db.prepare(`SELECT COUNT(*) FROM trades WHERE status='COMPLETED' ${dateFilter}`).first<number>(),
      db.prepare(`SELECT COALESCE(SUM(amount),0) FROM trades WHERE status='COMPLETED' ${dateFilter}`).first<number>(),
      db.prepare(`SELECT COALESCE(SUM(platform_fee),0) FROM trades WHERE status='COMPLETED' ${dateFilter}`).first<number>(),
      db.prepare(`SELECT COUNT(*) FROM usdt_deposits WHERE status='CONFIRMED' ${dateFilter}`).first<number>(),
      db.prepare(`SELECT COUNT(*) FROM withdraw_requests WHERE status IN ('COMPLETED','PROCESSING') ${dateFilter}`).first<number>(),
    ]);

    return c.json({
      ok: true,
      analytics: { period, new_users: newUsers, completed_trades: completedTrades, daily_volume: dailyVolume, platform_fees: platformFees, deposits, withdrawals },
    });
  });

  app.get("/api/v2/admin/timeline", async (c) => {
    const limit = Math.min(Number(c.req.query("limit") || "50"), 200);
    const rows = await c.env.DB.prepare(
      `SELECT * FROM audit_log ORDER BY id DESC LIMIT ?`
    ).bind(limit).all();
    return c.json({ ok: true, timeline: rows.results ?? [] });
  });

  // ============================================================
  // MARKETPLACE ENHANCED
  // ============================================================

  app.get("/api/v2/market/enhanced", async (c) => {
    const type = c.req.query("type")?.toUpperCase();
    const q = c.req.query("q");
    const sort = c.req.query("sort") || "price";
    const minAmount = parseFloat(c.req.query("min_amount") || "");
    const maxAmount = parseFloat(c.req.query("max_amount") || "");
    const payment = c.req.query("payment");

    let sql = `
      SELECT a.id, a.user, a.title, a.amount, a.price, a.payment, a.type,
             a.min_amount, a.max_amount, a.created,
             u.verified, u.rating, u.trades_count,
             ut.trust_score, ut.completion_rate, ut.avg_rating,
             CASE WHEN fa.id IS NOT NULL THEN 1 ELSE 0 END AS is_featured
      FROM ads a
      JOIN users u ON a.user = u.username
      LEFT JOIN user_trust ut ON a.user = ut.username
      LEFT JOIN featured_ads fa ON a.id = fa.ad_id AND fa.active = 1
      WHERE a.status = 'OPEN'
    `;
    const params: any[] = [];

    if (type === "SELL" || type === "BUY") { sql += " AND a.type = ?"; params.push(type); }
    if (payment) { sql += " AND a.payment LIKE ?"; params.push(`%${payment}%`); }
    if (Number.isFinite(minAmount)) { sql += " AND a.max_amount >= ?"; params.push(minAmount); }
    if (Number.isFinite(maxAmount)) { sql += " AND a.min_amount <= ?"; params.push(maxAmount); }
    if (q) { sql += " AND (a.title LIKE ? OR a.user LIKE ?)"; params.push(`%${q}%`, `%${q}%`); }

    if (sort === "trust") sql += " ORDER BY is_featured DESC, ut.trust_score DESC, a.price ASC";
    else if (sort === "trades") sql += " ORDER BY is_featured DESC, u.trades_count DESC, a.price ASC";
    else if (sort === "newest") sql += " ORDER BY is_featured DESC, a.id DESC";
    else sql += " ORDER BY is_featured DESC, a.price ASC, u.rating DESC";

    const limit = Math.min(Number(c.req.query("limit") || "50"), 100);
    const offset = Math.max(Number(c.req.query("offset") || "0"), 0);
    sql += " LIMIT ? OFFSET ?";
    params.push(limit, offset);

    const ads = await c.env.DB.prepare(sql).bind(...params).all();
    const price = await c.env.DB.prepare("SELECT usd_ils, usdt_ils FROM market_price WHERE id = 1").first();

    const priceStats = await c.env.DB.prepare(
      `SELECT MIN(price) as lowest, MAX(price) as highest, AVG(price) as avg_price
       FROM ads WHERE status = 'OPEN' AND type = 'SELL'`
    ).first<any>();

    return c.json({
      ok: true,
      ads: ads.results ?? [],
      price,
      price_stats: priceStats || {},
      limit, offset,
    });
  });

  // Public trader profile
  app.get("/api/v2/trader/:username", async (c) => {
    const username = c.req.param("username") ?? "";
    const user = await c.env.DB.prepare(
      "SELECT username, first_name, verified, rating, trades_count, created_at FROM users WHERE username = ?"
    ).bind(username).first<any>();
    if (!user) return c.json({ error: "المستخدم غير موجود" }, 404);

    const trust = await getTrust(c.env, username);
    const vip = getVipLevel(trust);
    return c.json({ ok: true, user, trust: trust || { trust_score: 50, total_ratings: 0, avg_rating: 0, completed_trades: 0, completion_rate: 0, account_age_days: 0 }, vip });
  });
}
