#!/bin/bash
# ============================================================
# Quick Cloudflare Worker Deploy
# Uses CLOUDFLARE_API_TOKEN from environment
# ============================================================
set -e
cd "$(dirname "$0")/.."

if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
  echo "ERROR: CLOUDFLARE_API_TOKEN not set"
  echo "Set it with: export CLOUDFLARE_API_TOKEN=your-token"
  exit 1
fi

echo "=== TypeScript Check ==="
npx tsc --noEmit

echo ""
echo "=== Deploy to Cloudflare ==="
npx wrangler deploy --name usdt-p2p-palestine

echo ""
echo "=== Done ==="
echo "Worker: https://usdt-p2p-palestine.sameraishi460.workers.dev"
