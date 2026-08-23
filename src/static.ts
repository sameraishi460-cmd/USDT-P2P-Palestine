/**
 * Static file serving for the frontend.
 *
 * Uses Cloudflare Workers' native ASSETS binding (configured in wrangler.toml)
 * to serve files from the frontend/ directory. The ASSETS binding is a
 * Fetcher that handles static file resolution, MIME types, and caching.
 */

/**
 * Serve a static file by delegating to the Cloudflare ASSETS binding.
 * Returns the asset Response, or null if no matching asset exists.
 */
export async function serveStaticFile(
  assets: Fetcher,
  pathname: string,
): Promise<Response | null> {
  try {
    const url = new URL(pathname, "https://static.local");
    const resp = await assets.fetch(url.toString());
    // ASSETS returns a 404 Response when no file matches — treat as miss.
    if (resp.status === 404) return null;
    return resp;
  } catch {
    return null;
  }
}
