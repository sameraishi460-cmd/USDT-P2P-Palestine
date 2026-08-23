/**
 * Static file serving for the frontend.
 *
 * Uses Vite/Cloudflare's `import.meta.glob` to bundle all frontend files
 * into the Worker at build time. The `/*` catch-all route in index.ts
 * delegates to `serveStaticFile()` to serve HTML, CSS, and JS.
 */

// Eagerly import all frontend files as raw text.
const files: Record<string, { default: string }> = import.meta.glob(
  "/frontend/**/*",
  { eager: true, as: "raw" },
);

// Build a lookup map: "/index.html" → content, "/assets/app.css" → content, etc.
const fileMap: Record<string, string> = {};
for (const [globPath, mod] of Object.entries(files)) {
  // globPath is like "/frontend/index.html" → strip "/frontend" prefix
  const path = globPath.replace(/^\/frontend/, "") || "/";
  fileMap[path] = mod.default;
}

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".webp": "image/webp",
};

function getMime(path: string): string {
  const ext = path.slice(path.lastIndexOf("."));
  return MIME[ext] || "application/octet-stream";
}

/**
 * Serve a static file by path. Returns a Response or null if not found.
 * Used by the `/*` catch-all route in index.ts.
 */
export function serveStaticFile(path: string): Response | null {
  // Normalize: "/market.html" → "/market.html", "/" → "/index.html"
  const normalized = path === "/" ? "/index.html" : path;

  const content = fileMap[normalized];
  if (content === undefined) return null;

  return new Response(content, {
    headers: {
      "Content-Type": getMime(normalized),
      "Cache-Control": "public, max-age=3600",
    },
  });
}
