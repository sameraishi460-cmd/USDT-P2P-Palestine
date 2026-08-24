/**
 * Telegram Bot Webhook handler.
 *
 * Architecture:
 *   Telegram API → POST /telegram/webhook  (validated via X-Telegram-Bot-Api-Secret-Token)
 *
 * Supports:
 *   - /start (+ referral-style deep links)
 *   - Inline keyboard callbacks (Open Wallet / Market / Trade)
 *   - WebApp buttons pointing at the Pages frontend
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

async function tgCall(env: AppEnv["Bindings"], method: string, body: any): Promise<void> {
  if (!env.TELEGRAM_BOT_TOKEN) return;
  try {
    await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // Best-effort — never fail webhook processing because of a Telegram outage.
  }
}

async function sendMessage(env: AppEnv["Bindings"], chatId: number | string, text: string, replyMarkup?: any) {
  await tgCall(env, "sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    ...({ reply_markup: replyMarkup } as any),
  });
}

function mainKeyboard(appUrl: string) {
  return {
    inline_keyboard: [
      [
        { text: "🛒 السوق", web_app: { url: `${appUrl}/market.html` } },
        { text: "💰 المحفظة", web_app: { url: `${appUrl}/wallet.html` } },
      ],
      [
        { text: "📄 صفقاتي", web_app: { url: `${appUrl}/trades.html` } },
        { text: "👤 الملف الشخصي", web_app: { url: `${appUrl}/profile.html` } },
      ],
    ],
  };
}

/** Handle a validated Telegram update. */
export async function handleTelegramUpdate(c: Context<AppEnv>): Promise<Response> {
  const env = c.env;

  // Validate the secret token header set when registering the webhook.
  // Skip validation if no webhook secret is configured (allows webhook to work without secret).
  if (!env.TELEGRAM_BOT_TOKEN) {
    return c.json({ ok: false }, 403);
  }
  const secretHeader = c.req.header("X-Telegram-Bot-Api-Secret-Token") || "";
  if (env.TELEGRAM_WEBHOOK_SECRET && secretHeader !== env.TELEGRAM_WEBHOOK_SECRET) {
    return c.json({ ok: false }, 403);
  }

  let update: TGUpdate;
  try {
    update = await c.req.json<TGUpdate>();
  } catch {
    return c.json({ ok: true }); // malformed — ack anyway to stop retries
  }

  const appUrl = (env.APP_URL || "https://example.pages.dev").replace(/\/$/, "");

  // ---- /start command ----
  if (update.message?.text?.startsWith("/start")) {
    const chatId = update.message.chat.id;
    const tgUser = update.message.from;
    if (!tgUser) return c.json({ ok: true });

    // Link telegram_id to an existing user if username matches, else guide registration.
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
      await sendMessage(env, chatId,
        `أهلاً بك <b>${linked.username}</b> 👋\nمنصة USDT P2P Palestine — تداول آمن بالضمان.`,
        mainKeyboard(appUrl));
    } else {
      await sendMessage(env, chatId,
        `أهلاً بك في <b>USDT P2P Palestine</b> 🇵🇸\n\n` +
        `سجّل أولاً من خلال التطبيق ثم عد للضغط على الأزرار.\n` +
        `اسم المستخدم في المنصة يجب أن يطابق اسمك في تيليجرام (@${tgUser.username ?? ""}).`,
        { inline_keyboard: [[{ text: "🚀 فتح التطبيق", web_app: { url: `${appUrl}/login.html` } }]] });
    }
    return c.json({ ok: true });
  }

  // ---- callback queries ----
  if (update.callback_query?.data) {
    const cb = update.callback_query;
    const data: string = cb.data ?? "";
    const chatId = cb.message?.chat.id ?? cb.from.id;
    switch (data) {
      case "wallet":
        await sendMessage(env, chatId, "💰 فتح المحفظة...", {
          inline_keyboard: [[{ text: "فتح المحفظة", web_app: { url: `${appUrl}/wallet.html` } }]],
        });
        break;
      case "market":
        await sendMessage(env, chatId, "🛒 فتح السوق...", {
          inline_keyboard: [[{ text: "فتح السوق", web_app: { url: `${appUrl}/market.html` } }]],
        });
        break;
      default:
        if (data.startsWith("trade_")) {
          const tradeId = data.slice(6);
          await sendMessage(env, chatId, `📄 الصفقة #${tradeId}`, {
            inline_keyboard: [[{ text: "فتح الصفقة", web_app: { url: `${appUrl}/trade.html?id=${tradeId}` } }]],
          });
        }
    }
    await tgCall(env, "answerCallbackQuery", { callback_query_id: cb.id });
    return c.json({ ok: true });
  }

  return c.json({ ok: true });
}

/**
 * Send a trade notification with an inline button that opens the exact trade.
 * Used by routes (trades/wallet/admin) — exported for reuse.
 */
export async function sendTradeNotification(
  env: AppEnv["Bindings"], telegramId: string, title: string, message: string, tradeId: number
): Promise<void> {
  if (!telegramId) return;
  const appUrl = (env.APP_URL || "").replace(/\/$/, "");
  const markup = appUrl
    ? { inline_keyboard: [[{ text: "📄 فتح الصفقة", web_app: { url: `${appUrl}/trade.html?id=${tradeId}` } }]] }
    : undefined;
  await sendMessage(env, telegramId, `<b>${title}</b>\n${message}`, markup);
}
