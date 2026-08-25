/**
 * Telegram Bot Webhook handler — FULL IMPLEMENTATION.
 *
 * Architecture:
 *   Telegram API → POST /telegram/webhook  (validated via X-Telegram-Bot-Api-Secret-Token)
 *
 * Supports:
 *   - /start, /start <code>, /help, /menu, /link <code>, /market, /account, /wallet
 *   - Callback queries (buttons)
 *   - URL buttons pointing at the Pages frontend
 *   - Telegram notifications for platform events
 *
 * SECURITY:
 *   - Webhook secret token checked against env.TELEGRAM_WEBHOOK_SECRET.
 *   - Bot token lives ONLY in Workers secrets — never in source.
 */
import type { Context } from "hono";
import type { AppEnv } from "../types";

type TGUpdate = {
  message?: {
    chat: { id: number };
    text?: string;
    from?: { id: number; username?: string; first_name?: string; last_name?: string };
  };
  callback_query?: {
    id: string;
    data?: string;
    from: { id: number; username?: string; first_name?: string };
    message?: { chat: { id: number } };
  };
};

// ============================================================
// Telegram Bot API helpers
// ============================================================

async function tgCall(env: AppEnv["Bindings"], method: string, body: any): Promise<any> {
  if (!env.TELEGRAM_BOT_TOKEN) { console.error("[tg] tgCall: no bot token"); return null; }
  try {
    const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const json: any = await res.json().catch(() => ({}));
    if (!json?.ok) console.error(`[tg] ${method} failed:`, JSON.stringify(json).slice(0, 200));
    return json;
  } catch (e: any) {
    console.error(`[tg] ${method} exception:`, e?.message);
    return null;
  }
}

async function sendMessage(env: AppEnv["Bindings"], chatId: number | string, text: string, replyMarkup?: any) {
  return tgCall(env, "sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    ...({ reply_markup: replyMarkup } as any),
  });
}

async function answerCallback(env: AppEnv["Bindings"], callbackQueryId: string, text?: string) {
  return tgCall(env, "answerCallbackQuery", {
    callback_query_id: callbackQueryId,
    text: text || "",
    show_alert: false,
  });
}

// ============================================================
// Keyboards — use url buttons (NOT web_app which requires Mini App config)
// ============================================================

function mainKeyboard(appUrl: string, tgToken?: string) {
  const auth = tgToken ? `?tg_token=${tgToken}` : "";
  return {
    inline_keyboard: [
      [
        { text: "🛒 السوق", url: `${appUrl}/market.html${auth}` },
        { text: "💰 المحفظة", url: `${appUrl}/wallet.html${auth}` },
      ],
      [
        { text: "📄 صفقاتي", url: `${appUrl}/trades.html${auth}` },
        { text: "👤 حسابي", url: `${appUrl}/profile.html${auth}` },
      ],
      [
        { text: "🌐 فتح المنصة", url: `${appUrl}${auth ? '/' + auth.slice(1) : ''}` },
        { text: "❓ المساعدة", callback_data: "help" },
      ],
    ],
  };
}

function helpKeyboard(appUrl: string) {
  return {
    inline_keyboard: [
      [{ text: "🌐 فتح المنصة", url: `${appUrl}/index.html` }],
      [{ text: "🛒 السوق", callback_data: "open_market" }],
      [{ text: "👤 حسابي", callback_data: "open_profile" }],
      [{ text: "💰 المحفظة", callback_data: "open_wallet" }],
      [{ text: "🔙 رجوع", callback_data: "main_menu" }],
    ],
  };
}

// ============================================================
// Update handler
// ============================================================

/** Handle a validated Telegram update. */
export async function handleTelegramUpdate(c: Context<AppEnv>): Promise<Response> {
  const env = c.env;
  console.log("[tg] webhook hit — method:", c.req.method);

  // Validate the secret token header
  if (!env.TELEGRAM_BOT_TOKEN) {
    console.error("[tg] FATAL: no TELEGRAM_BOT_TOKEN configured");
    return c.json({ ok: false }, 403);
  }
  const secretHeader = c.req.header("X-Telegram-Bot-Api-Secret-Token") || "";
  if (env.TELEGRAM_WEBHOOK_SECRET && secretHeader !== env.TELEGRAM_WEBHOOK_SECRET) {
    console.error("[tg] REJECTED: secret token mismatch");
    return c.json({ ok: false }, 403);
  }
  console.log("[tg] secret OK, parsing update");

  let update: TGUpdate;
  try {
    update = await c.req.json<TGUpdate>();
  } catch (e: any) {
    console.error("[tg] malformed JSON:", e?.message);
    return c.json({ ok: true });
  }

  const appUrl = (env.APP_URL || "https://usdt-p2p-palestine.sameraishi460.workers.dev").replace(/\/$/, "");

  // Diagnostic logging
  const hasMsg = !!update.message;
  const hasCb = !!update.callback_query;
  console.log(`[tg] update parsed: message=${hasMsg} cb=${hasCb} text=${update.message?.text || "(none)"} chat=${update.message?.chat?.id || update.callback_query?.from?.id || "?"}`);

  // ============================================================
  // /start command (with optional deep-link parameter)
  // ============================================================
  if (update.message?.text?.startsWith("/start")) {
    const chatId = update.message.chat.id;
    const tgUser = update.message.from;
    console.log(`[tg] /start detected chatId=${chatId} tgUser=${tgUser?.id} username=${tgUser?.username}`);
    if (!tgUser) { console.log("[tg] no tgUser, acking"); return c.json({ ok: true }); }

    // Parse optional parameter: /start <code>
    const parts = update.message.text.trim().split(/\s+/);
    const param = parts.length > 1 ? parts[1] : null;

    // If parameter is a link code, try to link the Telegram account
    if (param && /^[A-Z0-9]{6}$/i.test(param)) {
      try {
        const codeRow = await env.DB.prepare(
          "SELECT id, telegram_user_id, action, expires_at, used FROM telegram_auth_codes WHERE code = ?"
        ).bind(param.toUpperCase()).first<{ id: number; telegram_user_id: string; action: string; expires_at: string; used: number }>();

        if (codeRow && !codeRow.used && new Date(codeRow.expires_at) > new Date()) {
          if (codeRow.action === "link") {
            const platformUserId = codeRow.telegram_user_id;
            const existing = await env.DB.prepare(
              "SELECT id, username FROM users WHERE telegram_id = ?"
            ).bind(String(tgUser.id)).first<{ id: number; username: string }>();
            if (existing && String(existing.id) !== platformUserId) {
              await sendMessage(env, chatId, "⚠️ هذا الحساب مرتبط بمستخدم آخر في المنصة.");
            } else {
              await env.DB.prepare("UPDATE users SET telegram_id = ? WHERE id = ?")
                .bind(String(tgUser.id), Number(platformUserId)).run();
              await env.DB.prepare("UPDATE telegram_auth_codes SET used = 1 WHERE id = ?")
                .bind(codeRow.id).run();
              const user = await env.DB.prepare("SELECT username FROM users WHERE id = ?")
                .bind(Number(platformUserId)).first<{ username: string }>();
              await sendMessage(env, chatId,
                `✅ تم ربط حسابك بنجاح!\n\nمرحباً <b>${user?.username || "مستخدم"}</b> 👋\nيمكنك الآن استخدام المنصة من تيليجرام.`,
                mainKeyboard(appUrl));
              return c.json({ ok: true });
            }
          } else if (codeRow.action === "login") {
            await env.DB.prepare("UPDATE telegram_auth_codes SET used = 1 WHERE id = ?")
              .bind(codeRow.id).run();
            await sendMessage(env, chatId,
              `✅ تم التحقق من هويتك!\n\nيمكنك فتح المنصة للمتابعة.`,
              mainKeyboard(appUrl));
            return c.json({ ok: true });
          }
        } else {
          await sendMessage(env, chatId, "⚠️ الكود منتهي الصلاحية أو مستخدم بالفعل.\n\nأعد المحاولة من الموقع.");
          return c.json({ ok: true });
        }
      } catch {
        // Fall through to normal /start
      }
    }

    // Normal /start — link telegram_id to existing user if possible
    const existing = await env.DB.prepare(
      "SELECT id, username FROM users WHERE telegram_id = ?"
    ).bind(String(tgUser.id)).first<{ id: number; username: string }>();

    if (!existing && tgUser.username) {
      const byName = await env.DB.prepare(
        "SELECT id, username FROM users WHERE username = ? AND (telegram_id IS NULL OR telegram_id = '')"
      ).bind(tgUser.username).first<{ id: number; username: string }>();
      if (byName) {
        await env.DB.prepare("UPDATE users SET telegram_id = ? WHERE id = ?")
          .bind(String(tgUser.id), byName.id).run();
      }
    }

    const linked = existing ?? (tgUser.username
      ? await env.DB.prepare("SELECT id, username FROM users WHERE username = ?").bind(tgUser.username).first<{ id: number; username: string }>()
      : null);

    if (linked) {
      console.log(`[tg] /start linked user: ${linked.username}, sending welcome to chat ${chatId}`);
      // Generate a one-time deep-link login token so clicking URL buttons creates a web session
      const loginToken = Math.random().toString(36).substring(2) + Math.random().toString(36).substring(2);
      const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString(); // 15 minutes
      try {
        await env.DB.prepare(
          "INSERT INTO telegram_login_tokens (telegram_user_id, username, token, expires_at) VALUES (?, ?, ?, ?)"
        ).bind(String(tgUser.id), linked.username, loginToken, expiresAt).run();
      } catch (e: any) {
        console.error("[tg] failed to create login token:", e?.message);
      }
      // Build URLs with the login token embedded
      const authedUrl = (page: string) => `${appUrl}/${page}?tg_token=${loginToken}`;
      const kb = {
        inline_keyboard: [
          [
            { text: "🛒 السوق", url: authedUrl("market.html") },
            { text: "💰 المحفظة", url: authedUrl("wallet.html") },
          ],
          [
            { text: "📄 صفقاتي", url: authedUrl("trades.html") },
            { text: "👤 حسابي", url: authedUrl("profile.html") },
          ],
          [
            { text: "🌐 فتح المنصة", url: authedUrl("index.html") },
            { text: "❓ المساعدة", callback_data: "help" },
          ],
        ],
      };
      const sendRes = await sendMessage(env, chatId,
        `👋 <b>أهلاً وسهلاً بك في USDT P2P Palestine</b> 🇵🇸\n\nمرحباً <b>${linked.username}</b>\n\nمنصة آمنة وسهلة لشراء وبيع USDT.\nاختر من القائمة للمتابعة:`,
        kb);
      console.log(`[tg] sendMessage result:`, JSON.stringify(sendRes).slice(0, 300));
    } else {
      console.log(`[tg] /start no linked user for chat ${chatId}, sending registration prompt`);
      const sendRes = await sendMessage(env, chatId,
        `👋 <b>أهلاً وسهلاً بك في USDT P2P Palestine</b> 🇵🇸\n\nمنصة آمنة وسهلة لشراء وبيع USDT.\n\nسجّل أولاً من خلال التطبيق ثم عد لربط حسابك.\n\n💡 اسم المستخدم في المنصة يمكن أن يطابق اسمك في تيليجرام.`,
        {
          inline_keyboard: [
            [{ text: "🚀 فتح التطبيق", url: `${appUrl}/register` }],
            [{ text: "🔗 تسجيل الدخول", url: `${appUrl}/login` }],
          ],
        });
      console.log(`[tg] sendMessage result:`, JSON.stringify(sendRes).slice(0, 300));
    }
    return c.json({ ok: true });
  }

  // ============================================================
  // /help command
  // ============================================================
  if (update.message?.text?.startsWith("/help")) {
    const chatId = update.message.chat.id;
    await sendMessage(env, chatId,
      `❓ <b>المساعدة — USDT P2P Palestine</b>\n\n` +
      `📱 <b>الأوامر:</b>\n` +
      `/start — البداية / فتح القائمة\n` +
      `/help — المساعدة\n` +
      `/market — فتح السوق\n` +
      `/account — حسابي\n` +
      `/wallet — المحفظة\n` +
      `/link &lt;code&gt; — ربط حسابك\n\n` +
      `💡 يمكنك استخدام الأزرار أدناه للتنقل السريع.`,
      helpKeyboard(appUrl));
    return c.json({ ok: true });
  }

  // ============================================================
  // /menu command
  // ============================================================
  if (update.message?.text?.startsWith("/menu")) {
    const chatId = update.message.chat.id;
    await sendMessage(env, chatId,
      `📋 <b>القائمة الرئيسية</b>\n\nاختر ما تريد:`,
      mainKeyboard(appUrl));
    return c.json({ ok: true });
  }

  // ============================================================
  // /market command
  // ============================================================
  if (update.message?.text?.startsWith("/market")) {
    const chatId = update.message.chat.id;
    await sendMessage(env, chatId,
      `🛒 <b>السوق</b>\n\nتصفح عروض شراء وبيع USDT:`,
      { inline_keyboard: [[{ text: "🛒 فتح السوق", url: `${appUrl}/market` }]] });
    return c.json({ ok: true });
  }

  // ============================================================
  // /account command
  // ============================================================
  if (update.message?.text?.startsWith("/account")) {
    const chatId = update.message.chat.id;
    const tgUser = update.message.from;
    if (!tgUser) return c.json({ ok: true });

    const user = await env.DB.prepare(
      "SELECT id, username FROM users WHERE telegram_id = ?"
    ).bind(String(tgUser.id)).first<{ id: number; username: string }>();

    if (user) {
      await sendMessage(env, chatId,
        `👤 <b>حسابك</b>\n\nالمستخدم: <b>${user.username}</b>`,
        { inline_keyboard: [[{ text: "👤 فتح الملف", url: `${appUrl}/profile` }]] });
    } else {
      await sendMessage(env, chatId,
        `⚠️ حسابك غير مرتبط بالمنصة.\n\nأرسل /link <code> لربط حسابك.`,
        { inline_keyboard: [[{ text: "🔗 تسجيل الدخول", url: `${appUrl}/login` }]] });
    }
    return c.json({ ok: true });
  }

  // ============================================================
  // /wallet command
  // ============================================================
  if (update.message?.text?.startsWith("/wallet")) {
    const chatId = update.message.chat.id;
    await sendMessage(env, chatId,
      `💰 <b>المحفظة</b>\n\nإدارة رصيدك USDT:`,
      { inline_keyboard: [[{ text: "💰 فتح المحفظة", url: `${appUrl}/wallet` }]] });
    return c.json({ ok: true });
  }

  // ============================================================
  // /link command — link Telegram to platform account
  // ============================================================
  if (update.message?.text?.startsWith("/link")) {
    const chatId = update.message.chat.id;
    const tgUser = update.message.from;
    if (!tgUser) return c.json({ ok: true });

    const parts = update.message.text.trim().split(/\s+/);
    const code = parts.length > 1 ? parts[1].toUpperCase() : null;

    if (!code) {
      await sendMessage(env, chatId,
        `🔗 <b>ربط الحساب</b>\n\n` +
        `لربط حسابك بالمنصة:\n` +
        `1. افتح الموقع وسجل الدخول\n` +
        `2. اذهب إلى حسابي → ربط Telegram\n` +
        `3. انسخ الكود وأرسله هنا:\n\n` +
        `/link &lt;code&gt;\n\n` +
        `مثال: /link ABC123`);
      return c.json({ ok: true });
    }

    // Verify the link code
    try {
      const codeRow = await env.DB.prepare(
        "SELECT id, telegram_user_id, action, expires_at, used FROM telegram_auth_codes WHERE code = ?"
      ).bind(code).first<{ id: number; telegram_user_id: string; action: string; expires_at: string; used: number }>();

      if (!codeRow) {
        await sendMessage(env, chatId, "❌ كود غير صالح.\n\nتأكد من إدخال الكود الصحيح.");
        return c.json({ ok: true });
      }
      if (codeRow.used) {
        await sendMessage(env, chatId, "⚠️ تم استخدام هذا الكود بالفعل.");
        return c.json({ ok: true });
      }
      if (new Date(codeRow.expires_at) < new Date()) {
        await sendMessage(env, chatId, "⏰ انتهت صلاحية الكود.\n\nأعد المحاولة من الموقع.");
        return c.json({ ok: true });
      }

      if (codeRow.action === "link") {
        const platformUserId = codeRow.telegram_user_id;
        const existingTg = await env.DB.prepare(
          "SELECT id, username FROM users WHERE telegram_id = ?"
        ).bind(String(tgUser.id)).first<{ id: number; username: string }>();

        if (existingTg && String(existingTg.id) !== platformUserId) {
          await sendMessage(env, chatId,
            `⚠️ هذا الحساب مرتبط بالفعل بمستخدم <b>${existingTg.username}</b>.\n\nلا يمكن ربطه بحساب آخر.`);
          return c.json({ ok: true });
        }

        await env.DB.prepare("UPDATE users SET telegram_id = ? WHERE id = ?")
          .bind(String(tgUser.id), Number(platformUserId)).run();
        await env.DB.prepare("UPDATE telegram_auth_codes SET used = 1 WHERE id = ?")
          .bind(codeRow.id).run();

        const user = await env.DB.prepare("SELECT username FROM users WHERE id = ?")
          .bind(Number(platformUserId)).first<{ username: string }>();

        await sendMessage(env, chatId,
          `✅ <b>تم ربط الحساب بنجاح!</b>\n\nمرحباً <b>${user?.username || "مستخدم"}</b> 👋\n\nيمكنك الآن استخدام المنصة بالكامل.`,
          mainKeyboard(appUrl));
      } else {
        await sendMessage(env, chatId, "⚠️ نوع كود غير متوقع.\n\nاستخدم /link للاستعلام.");
      }
    } catch (err: any) {
      console.error("[tg] /link error:", err?.message);
      await sendMessage(env, chatId, "❌ حدث خطأ أثناء معالجة الكود.\n\nحاول مرة أخرى.");
    }
    return c.json({ ok: true });
  }

  // ============================================================
  // Callback queries
  // ============================================================
  if (update.callback_query?.data) {
    const cb = update.callback_query;
    const data: string = cb.data ?? "";
    const chatId = cb.message?.chat.id ?? cb.from.id;

    switch (data) {
      case "help":
        await sendMessage(env, chatId,
          `❓ <b>المساعدة</b>\n\nاستخدم الأزرار أو الأوامر:\n/start — القائمة الرئيسية\n/help — المساعدة\n/market — السوق\n/link <code> — ربط الحساب`,
          helpKeyboard(appUrl));
        break;
      case "open_market":
        await sendMessage(env, chatId, "🛒 فتح السوق...", {
          inline_keyboard: [[{ text: "🛒 فتح السوق", url: `${appUrl}/market` }]],
        });
        break;
      case "open_profile":
        await sendMessage(env, chatId, "👤 فتح الملف الشخصي...", {
          inline_keyboard: [[{ text: "👤 فتح الملف", url: `${appUrl}/profile` }]],
        });
        break;
      case "open_wallet":
        await sendMessage(env, chatId, "💰 فتح المحفظة...", {
          inline_keyboard: [[{ text: "💰 فتح المحفظة", url: `${appUrl}/wallet` }]],
        });
        break;
      case "main_menu":
        await sendMessage(env, chatId, "📋 القائمة الرئيسية:", mainKeyboard(appUrl));
        break;
      case "market":
        await sendMessage(env, chatId, "🛒 فتح السوق...", {
          inline_keyboard: [[{ text: "🛒 فتح السوق", url: `${appUrl}/market` }]],
        });
        break;
      case "wallet":
        await sendMessage(env, chatId, "💰 فتح المحفظة...", {
          inline_keyboard: [[{ text: "💰 فتح المحفظة", url: `${appUrl}/wallet` }]],
        });
        break;
      default:
        if (data.startsWith("trade_")) {
          const tradeId = data.slice(6);
          await sendMessage(env, chatId, `📄 الصفقة #${tradeId}`, {
            inline_keyboard: [[{ text: "📄 فتح الصفقة", url: `${appUrl}/trade?id=${tradeId}` }]],
          });
        }
    }
    await answerCallback(env, cb.id);
    return c.json({ ok: true });
  }

  return c.json({ ok: true });
}

// ============================================================
// Notification helpers — called by trade/wallet/dispute routes
// ============================================================

/**
 * Send a trade notification to a user via Telegram.
 * Used by trade routes for payment, release, completion, etc.
 */
export async function sendTradeNotification(
  env: AppEnv["Bindings"], telegramId: string, title: string, message: string, tradeId: number
): Promise<void> {
  if (!telegramId) return;
  const appUrl = (env.APP_URL || "").replace(/\/$/, "");
  const markup = appUrl
    ? { inline_keyboard: [[{ text: "📄 فتح الصفقة", url: `${appUrl}/trade?id=${tradeId}` }]] }
    : undefined;
  await sendMessage(env, telegramId, `<b>${title}</b>\n${message}`, markup);
}

/**
 * Send a generic platform notification via Telegram.
 * Used by wallet, dispute, admin routes.
 */
export async function sendTelegramNotification(
  env: AppEnv["Bindings"], telegramId: string, title: string, message: string
): Promise<void> {
  if (!telegramId) return;
  await sendMessage(env, telegramId, `<b>${title}</b>\n${message}`);
}

/**
 * Look up a user's Telegram ID from the database.
 */
export async function getUserTelegramId(db: D1Database, username: string): Promise<string> {
  const user = await db.prepare("SELECT telegram_id FROM users WHERE username = ?")
    .bind(username).first<{ telegram_id: string }>();
  return user?.telegram_id || "";
}

/**
 * Check if a user has Telegram notifications enabled.
 */
export async function hasTelegramNotificationEnabled(db: D1Database, username: string, type: string): Promise<boolean> {
  try {
    const prefs = await db.prepare("SELECT * FROM telegram_prefs WHERE username = ?")
      .bind(username).first<Record<string, number>>();
    if (!prefs) return true;
    switch (type) {
      case "trades": return !!prefs.notify_trades;
      case "payments": return !!prefs.notify_payments;
      case "disputes": return !!prefs.notify_disputes;
      case "system": return !!prefs.notify_system;
      default: return true;
    }
  } catch {
    return true;
  }
}
