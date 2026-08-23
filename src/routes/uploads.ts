/**
 * R2 secure uploads — payment proofs & dispute evidence.
 *
 * Rules:
 *   - Authenticated users only, rate-limited.
 *   - MIME + extension whitelist (images/PDF), 5MB max.
 *   - Ownership encoded in object key; objects are private (no public bucket).
 *   - Downloads go through /api/uploads/:id with ownership or admin check.
 */
import { Hono } from "hono";
import type { AppEnv } from "../types";
import { requireUser, requireAdmin, requireCsrf, rateLimit } from "../middleware/auth";

const uploads = new Hono<AppEnv>();

const MAX_SIZE = 5 * 1024 * 1024; // 5MB
const ALLOWED_TYPES: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
  "application/pdf": "pdf",
};

function detectRealType(buf: Uint8Array): string | null {
  if (buf.length > 3 && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return "image/jpeg";
  if (buf.length > 8 && buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) return "image/png";
  if (buf.length > 12 && String.fromCharCode(...buf.slice(0, 4)) === "RIFF" &&
      String.fromCharCode(...buf.slice(8, 12)) === "WEBP") return "image/webp";
  if (buf.length > 5 && buf[0] === 0x25 && buf[1] === 0x50 && buf[2] === 0x44 && buf[3] === 0x46) return "application/pdf";
  return null;
}

/**
 * POST /api/uploads/:kind   kind ∈ { payment-proof, evidence }
 * multipart/form-data: file=<binary>
 * Returns { ok, upload_id }
 */
uploads.post("/:kind", requireUser, requireCsrf, rateLimit(10, 60), async (c) => {
  const kind = c.req.param("kind") ?? "";
  if (!["payment-proof", "evidence"].includes(kind)) {
    return c.json({ error: "نوع رفع غير معروف" }, 400);
  }
  const username = c.get("user")!.username;

  let form: FormData;
  try {
    form = await c.req.parseBody() as unknown as FormData;
  } catch {
    return c.json({ error: "صيغة الطلب غير صالحة" }, 400);
  }

  const file = (form as any).file;
  if (!(file instanceof File)) return c.json({ error: "لم يتم إرسال ملف" }, 400);
  if (file.size <= 0 || file.size > MAX_SIZE) return c.json({ error: "حجم الملف يجب أن يكون أقل من 5MB" }, 400);

  const declaredType = file.type;
  if (!ALLOWED_TYPES[declaredType]) return c.json({ error: "صيغة غير مسموح بها (JPG/PNG/WEBP/PDF فقط)" }, 400);

  const bytes = new Uint8Array(await file.arrayBuffer());
  const realType = detectRealType(bytes);
  if (!realType || realType !== declaredType) return c.json({ error: "محتوى الملف لا يطابق صيغته المعلنة" }, 400);

  // Random unguessable key; ownership stored in D1 metadata row.
  const id = crypto.randomUUID().replace(/-/g, "").slice(0, 24);
  const ext = ALLOWED_TYPES[realType];
  const key = `${kind}/${username}/${id}.${ext}`;

  await c.env.R2.put(key, bytes, {
    httpMetadata: { contentType: realType },
    customMetadata: { owner: username ?? "unknown", kind },
  });

  await c.env.DB.prepare(
    "INSERT INTO uploads (id, key, owner, kind, mime, size) VALUES (?, ?, ?, ?, ?, ?)"
  ).bind(id, key, username, kind, realType, file.size).run();

  return c.json({ ok: true, upload_id: id });
});

/**
 * GET /api/uploads/:id — owner or admin only; streams privately from R2.
 */
uploads.get("/:id", async (c) => {
  const id = c.req.param("id");
  const meta = await c.env.DB.prepare(
    "SELECT key, owner, mime FROM uploads WHERE id = ?"
  ).bind(id).first<{ key: string; owner: string; mime: string }>();
  if (!meta) return c.json({ error: "غير موجود" }, 404);

  // Ownership check (manual — no middleware so admins can also view).
  const token = c.req.header("Cookie") || "";
  const sessionCookie = token.split(";").map((s) => s.trim())
    .find((s) => s.startsWith("usdt_session="));
  if (!sessionCookie) return c.json({ error: "غير مصرح" }, 401);
  const { verifySession } = await import("../utils/crypto");
  const session = await verifySession(sessionCookie.split("=")[1], c.env.SECRET_KEY);
  if (!session) return c.json({ error: "انتهت الجلسة" }, 401);

  const isAdmin = session.admin && (await c.env.DB.prepare(
    "SELECT status FROM users WHERE id = ?"
  ).bind(session.sub).first<{ status: string }>())?.status === "ADMIN";

  if (meta.owner !== session.username && !isAdmin) {
    return c.json({ error: "غير مصرح لك بهذا الملف" }, 403);
  }

  const obj = await c.env.R2.get(meta.key);
  if (!obj) return c.json({ error: "الملف غير موجود في التخزين" }, 404);

  return new Response(obj.body, {
    headers: {
      "Content-Type": meta.mime,
      "Content-Disposition": "inline",
      "Cache-Control": "private, max-age=300",
    },
  });
});

export default uploads;
