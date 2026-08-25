/**
 * Crypto utilities — PBKDF2 password hashing + HMAC session tokens.
 * Workers-native Web Crypto API only (no external deps).
 */

/** Generate a cryptographically random session ID (24 hex chars). */
export function randomSid(): string {
  return [...crypto.getRandomValues(new Uint8Array(12))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

const PBKDF2_ITERATIONS = 100_000;
const HASH_LENGTH = 32; // bytes

function toHex(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function fromHex(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

// ============================================================
// PASSWORD HASHING (PBKDF2-SHA256)
// Format: pbkdf2$<iterations>$<salt-hex>$<hash-hex>
// ============================================================

export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const keyMaterial = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: PBKDF2_ITERATIONS, hash: "SHA-256" },
    keyMaterial, HASH_LENGTH * 8
  );
  return `pbkdf2$${PBKDF2_ITERATIONS}$${toHex(salt.buffer)}$${toHex(bits)}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  try {
    const [scheme, iterStr, saltHex, hashHex] = stored.split("$");
    if (scheme !== "pbkdf2") return false;
    const iterations = parseInt(iterStr, 10);
    const keyMaterial = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]
    );
    const bits = await crypto.subtle.deriveBits(
      { name: "PBKDF2", salt: fromHex(saltHex), iterations, hash: "SHA-256" },
      keyMaterial, HASH_LENGTH * 8
    );
    // Constant-time comparison
    const a = new Uint8Array(bits);
    const b = fromHex(hashHex);
    if (a.length !== b.length) return false;
    let diff = 0;
    for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
    return diff === 0;
  } catch {
    return false;
  }
}

// ============================================================
// SESSION TOKENS (HMAC-SHA256 signed, stateless)
// Format: base64url(payload).base64url(hmac)
// Payload: { sub, username, admin, iat, exp }
// ============================================================

function b64urlEncode(data: Uint8Array | string): string {
  const bytes = typeof data === "string" ? new TextEncoder().encode(data) : data;
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(str: string): string {
  const b64 = str.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
  return [...bin].map((c) => String.fromCharCode(c.charCodeAt(0))).join("");
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]
  );
}

export type SessionPayload = {
  sub: number;
  username: string;
  admin: boolean;
  /** Server-side session id — lets us revoke sessions (logout, password change). */
  sid?: string;
  iat: number;
  exp: number;
};

export async function signSession(
  payload: Omit<SessionPayload, "iat" | "exp">,
  secret: string,
  ttlSeconds = 30 * 24 * 3600
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const full: SessionPayload = { ...payload, iat: now, exp: now + ttlSeconds };
  const body = b64urlEncode(JSON.stringify(full));
  const key = await hmacKey(secret);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  return `${body}.${b64urlEncode(new Uint8Array(sig))}`;
}

export async function verifySession(token: string, secret: string): Promise<SessionPayload | null> {
  try {
    const [body, sigB64] = token.split(".");
    if (!body || !sigB64) return null;
    const key = await hmacKey(secret);
    const sigBytes = fromHex("");
    void sigBytes;
    const sig = Uint8Array.from(b64urlDecode(sigB64), (c) => c.charCodeAt(0));
    const valid = await crypto.subtle.verify(
      "HMAC", key, sig, new TextEncoder().encode(body)
    );
    if (!valid) return null;
    const payload: SessionPayload = JSON.parse(b64urlDecode(body));
    if (payload.exp < Math.floor(Date.now() / 1000)) return null; // expired
    return payload;
  } catch {
    return null;
  }
}

// ============================================================
// TOKENS & HASHING HELPERS
// ============================================================

/** Cryptographically-secure random URL-safe token (default 32 bytes). */
export function randomToken(bytes = 32): string {
  const buf = crypto.getRandomValues(new Uint8Array(bytes));
  return [...buf].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** SHA-256 hex digest — used to store email tokens hashed (never plaintext). */
export async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return toHex(digest);
}

/** Constant-time string comparison. */
export function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// ============================================================
// CSRF TOKENS
// ============================================================

export async function generateCsrfToken(sessionToken: string, secret: string): Promise<string> {
  const key = await hmacKey(secret);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode("csrf:" + sessionToken));
  return b64urlEncode(new Uint8Array(sig)).slice(0, 32);
}

export async function verifyCsrfToken(token: string, sessionToken: string, secret: string): Promise<boolean> {
  const expected = await generateCsrfToken(sessionToken, secret);
  if (token.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < token.length; i++) diff |= token.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

// ============================================================
// TELEGRAM WEBAPP initData VERIFICATION (official algorithm)
// ============================================================

export async function verifyTelegramInitData(
  initData: string,
  botToken: string
): Promise<{ valid: boolean; user?: any; reason?: string }> {
  try {
    const params = new URLSearchParams(initData);
    const hash = params.get("hash");
    if (!hash) return { valid: false, reason: "Missing hash" };
    params.delete("hash");

    // data_check_string = sorted key=value pairs joined by \n
    const pairs: string[] = [];
    const sorted = [...params.entries()].sort(([a], [b]) => a.localeCompare(b));
    for (const [k, v] of sorted) pairs.push(`${k}=${v}`);
    const dataCheckString = pairs.join("\n");

    // secret_key = HMAC_SHA256(key="WebAppData", message=botToken)
    const enc = new TextEncoder();
    const secretKey = await crypto.subtle.importKey(
      "raw", enc.encode("WebAppData"), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
    );
    const secret = await crypto.subtle.sign("HMAC", secretKey, enc.encode(botToken));

    // computed_hash = HMAC_SHA256(key=secret, message=data_check_string)
    const hmacKey2 = await crypto.subtle.importKey(
      "raw", secret, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
    );
    const computed = await crypto.subtle.sign("HMAC", hmacKey2, enc.encode(dataCheckString));
    const computedHex = toHex(computed);

    // Constant-time compare
    if (computedHex.length !== hash.length) return { valid: false, reason: "Hash mismatch" };
    let diff = 0;
    for (let i = 0; i < hash.length; i++) diff |= hash.charCodeAt(i) ^ computedHex.charCodeAt(i);
    if (diff !== 0) return { valid: false, reason: "Telegram verification failed" };

    const user = params.get("user") ? JSON.parse(params.get("user")!) : null;
    return { valid: true, user };
  } catch (e: any) {
    return { valid: false, reason: e?.message || "Telegram auth error" };
  }
}
