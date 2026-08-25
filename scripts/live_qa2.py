#!/usr/bin/env python3
"""Live QA: register, login, /me, market, create ad, wallet, notifications"""
import json, urllib.request, urllib.error, time

BASE = "https://usdt-p2p-palestine.sameraishi460.workers.dev"
PASS = FAIL = 0

def check(n, c, d=""):
    global PASS, FAIL
    if c: PASS += 1; print(f"  PASS  {n}")
    else: FAIL += 1; print(f"  FAIL  {n} ({d})")

def api(p, m="GET", data=None):
    hdrs = {"Content-Type": "application/json", "User-Agent": "curl/7.68"}
    b = json.dumps(data).encode() if data else None
    r = urllib.request.Request(BASE+p, data=b, headers=hdrs, method=m)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return json.loads(resp.read()), resp.status, resp.headers
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read()), e.code, e.headers
        except: return {}, e.code, {}

ts = str(int(time.time()))
print("=" * 50)
print("LIVE QA - FLOW TESTS")
print("=" * 50)

# 1. /me no auth
print("\n--- /me without auth ---")
r, s, _ = api("/api/auth/me")
check("/me returns auth status", s == 200)
check("/me authenticated=false", r.get("authenticated") == False)

# 2. Register
print("\n--- Register ---")
r, s, h = api("/api/auth/register", "POST", {"username": "qa_seller_" + ts, "password": "TestPass1!", "email": "seller_" + ts + "@t.com"})
check("Register seller 200", s == 200, f"s={s} r={r}")

r, s, h = api("/api/auth/register", "POST", {"username": "qa_buyer_" + ts, "password": "TestPass1!", "email": "buyer_" + ts + "@t.com"})
check("Register buyer 200", s == 200, f"s={s}")

# 3. Login
print("\n--- Login ---")
r, s, h = api("/api/auth/login", "POST", {"username": "qa_seller_" + ts, "password": "TestPass1!"})
check("Login seller 200", s == 200, f"s={s} r={r}")
seller_csrf = r.get("csrf_token", "")

r, s, h = api("/api/auth/login", "POST", {"username": "qa_buyer_" + ts, "password": "TestPass1!"})
check("Login buyer 200", s == 200, f"s={s}")
buyer_csrf = r.get("csrf_token", "")

r, s, _ = api("/api/auth/login", "POST", {"username": "qa_seller_" + ts, "password": "wrong"})
check("Bad password rejected", s in (401, 403), f"s={s}")

# 4. /me with auth (via cookie from login response headers)
# Note: We need the session cookie from Set-Cookie
print("\n--- Market + Price ---")
r, s, _ = api("/api/market")
check("Market 200", s == 200, f"s={s}")
check("Has ads", len(r.get("ads", [])) > 0, f"count={len(r.get('ads',[]))}")

r, s, _ = api("/api/market/price")
check("Price 200", s == 200, f"s={s}")
print(f"  Price: {r.get('price', {}).get('usdt_ils')} ILS/USDT")

# 5. Auth-required endpoints without auth
print("\n--- Auth required ---")
r, s, _ = api("/api/wallet")
check("Wallet requires auth", s == 401, f"s={s}")

r, s, _ = api("/api/notifications")
check("Notifications requires auth", s == 401, f"s={s}")

r, s, _ = api("/api/admin/users")
check("Admin requires auth", s in (401, 403), f"s={s}")

r, s, _ = api("/api/market/ads/create", "POST", {"type": "BUY"})
check("Create ad requires auth", s == 401, f"s={s}")

# 6. Frontend pages
print("\n--- Frontend pages ---")
for p in ["/", "/login", "/register", "/market", "/wallet", "/trades",
          "/create_ad", "/notifications", "/admin", "/admin_login", "/profile"]:
    r, s, _ = api(p)
    check(f"Page {p}", s in (200, 307), f"s={s}")

# 7. V2
print("\n--- V2 endpoints ---")
r, s, _ = api("/api/v2/trust/testuser1")
check("Trust score", s == 200, f"s={s}")
r, s, _ = api("/api/v2/market/enhanced")
check("Enhanced market", s == 200, f"s={s}")
r, s, _ = api("/api/v2/admin/analytics")
check("Admin analytics", s == 200, f"s={s}")
r, s, _ = api("/api/v2/admin/timeline")
check("Admin timeline", s == 200, f"s={s}")

# 8. Telegram webhook
print("\n--- Telegram webhook ---")
r, s, _ = api("/telegram/webhook", "POST", {
    "update_id": 999999, "message": {"message_id": 1, "from": {"id": 1, "first_name": "Q", "username": "q"},
    "chat": {"id": 1, "type": "private"}, "text": "/start", "date": int(time.time())}
}, )
check("Webhook rejects without secret", s == 403, f"s={s}")

# 9. Health
print("\n--- Health ---")
r, s, _ = api("/api/health")
check("Health 200", s == 200, f"s={s}")
for k, v in r.get("checks", {}).items():
    print(f"  {k}: {v}")

# 10. 404
print("\n--- 404 ---")
r, s, _ = api("/api/nonexistent")
check("API 404", s == 404, f"s={s}")

print(f"\n{'=' * 50}")
print(f"RESULTS: {PASS}/{PASS+FAIL} PASSED, {FAIL}/{PASS+FAIL} FAILED")
print("=" * 50)
