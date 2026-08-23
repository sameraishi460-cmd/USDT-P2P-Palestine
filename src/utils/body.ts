/**
 * Typed form-body helper for Hono routes.
 * parseBody() returns a union type; this normalizes it to string fields only.
 */
import type { Context } from "hono";

/** Parse a form/JSON body and keep only string fields. Never throws. */
export async function formBody(c: Context<any>): Promise<Record<string, string>> {
  try {
    const ct = c.req.header("Content-Type") || "";
    if (ct.includes("application/json")) {
      const j = await c.req.json<any>();
      const out: Record<string, string> = {};
      for (const [k, v] of Object.entries(j ?? {})) {
        if (typeof v === "string" || typeof v === "number") out[k] = String(v);
      }
      return out;
    }
    const parsed = await c.req.parseBody();
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v === "string") out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}
