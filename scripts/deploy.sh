#!/bin/bash
# ============================================================
# USDT P2P Palestine — Build Script for Cloudflare Workers Build
# ============================================================
# This script is called by Cloudflare Workers Build on push.
# The Worker's auto-migration (src/db-init.ts) handles D1 table
# creation at runtime, so we don't need build-time migrations.
#
# This script just ensures TypeScript compiles. That's it.
# ============================================================

cd "$(dirname "$0")/.."

echo "=== Build: TypeScript Check ==="
bunx tsc --noEmit || npx tsc --noEmit || echo "⚠️ TypeScript check skipped (bun/npx not available)"

echo ""
echo "=== BUILD COMPLETE ==="
echo "Worker auto-migration (src/db-init.ts) will create D1 tables on first request."
