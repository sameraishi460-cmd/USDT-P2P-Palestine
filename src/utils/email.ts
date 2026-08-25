/**
 * Transactional email — Resend HTTP API (plain fetch, Workers-native, no SMTP).
 *
 * SECURITY:
 * - RESEND_API_KEY is a Cloudflare secret; never exposed to the frontend.
 * - Emails NEVER contain passwords or session secrets — only single-use,
 *   expiring links whose tokens are stored hashed in D1.
 *
 * When RESEND_API_KEY is not configured, sendEmail() reports { sent: false }
 * and callers must NOT claim email delivery works.
 */
import type { Bindings, EmailResult } from "../types";

const RESEND_API = "https://api.resend.com/emails";

function baseLayout(title: string, bodyHtml: string, appUrl: string): string {
  return `<!DOCTYPE html>
<html dir="rtl" lang="ar">
<body style="margin:0;padding:0;background:#0a0e18;font-family:Tahoma,Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;padding:32px 16px;">
    <div style="background:#111827;border:1px solid #1f2937;border-radius:16px;padding:32px;text-align:center;">
      <div style="font-size:28px;margin-bottom:12px;">🇵🇸</div>
      <h2 style="color:#22c55e;margin:0 0 16px;font-size:20px;">USDT P2P Palestine</h2>
      <h3 style="color:#f9fafb;margin:0 0 12px;font-size:16px;">${title}</h3>
      <div style="color:#d1d5db;font-size:14px;line-height:1.8;">${bodyHtml}</div>
      <p style="color:#6b7280;font-size:11px;margin-top:28px;">
        إذا لم تطلب هذا البريد، تجاهله — لن يتغير أي شيء في حسابك.<br/>
        <a href="${appUrl}" style="color:#22c55e;">${appUrl}</a>
      </p>
    </div>
  </div>
</body>
</html>`;
}

export async function sendEmail(
  env: Bindings,
  to: string,
  subject: string,
  bodyHtml: string
): Promise<EmailResult> {
  if (!env.RESEND_API_KEY) {
    return { sent: false, error: "email_not_configured" };
  }
  const from = env.EMAIL_FROM || "USDT P2P Palestine <onboarding@resend.dev>";
  try {
    const res = await fetch(RESEND_API, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.RESEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: [to],
        subject,
        html: baseLayout(subject, bodyHtml, env.APP_URL || ""),
      }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      // Never log the API key or full provider payload.
      console.error(`[email] provider error status=${res.status}`);
      return { sent: false, error: `provider_error_${res.status}` };
    }
    return { sent: true };
  } catch (e: any) {
    console.error("[email] send failed:", e?.message?.slice(0, 120));
    return { sent: false, error: "send_failed" };
  }
}

export function verificationEmailBody(link: string): string {
  return `<p>مرحباً 👋</p>
  <p>اضغط على الزر أدناه لتوثيق بريدك الإلكتروني. الرابط صالح لمدة 24 ساعة ويمكن استخدامه مرة واحدة فقط.</p>
  <p style="margin:24px 0;">
    <a href="${link}" style="background:#22c55e;color:#04140a;text-decoration:none;padding:12px 28px;border-radius:10px;font-weight:bold;display:inline-block;">✅ توثيق البريد الإلكتروني</a>
  </p>
  <p style="font-size:12px;color:#9ca3af;word-break:break-all;">إذا لم يعمل الزر، انسخ الرابط:<br/>${link}</p>`;
}

export function resetPasswordEmailBody(link: string): string {
  return `<p>تلقينا طلباً لإعادة تعيين كلمة المرور الخاصة بحسابك.</p>
  <p>الرابط صالح لمدة ساعة واحدة ويمكن استخدامه مرة واحدة فقط.</p>
  <p style="margin:24px 0;">
    <a href="${link}" style="background:#3b82f6;color:#fff;text-decoration:none;padding:12px 28px;border-radius:10px;font-weight:bold;display:inline-block;">🔑 إعادة تعيين كلمة المرور</a>
  </p>
  <p style="font-size:12px;color:#9ca3af;word-break:break-all;">إذا لم يعمل الزر، انسخ الرابط:<br/>${link}</p>`;
}
