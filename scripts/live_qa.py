#!/usr/bin/env python3
import json, urllib.request, urllib.error, time, sys

BASE = "https://usdt-p2p-palestine.sameraishi460.workers.dev"
PASS = FAIL = 0
RESULTS = []

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} ({detail})")
    RESULTS.append((name, "PASS" if condition else "FAIL", detail))

def api(path, method="GET", data=None, headers=None):
    url = BASE + path
    hdrs = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    if headers:
        hdrs.update(headers)
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw), resp.status
            except:
                return {"raw": raw[:200]}, resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return json.loads(raw), e.code
        except:
            return {"raw": raw[:200]}, e.code

print("=" * 60)
print("  LIVE PRODUCTION QA")
print("=" * 60)

# 1. HEALTH
print("\n--- 1. HEALTH ---")
r, s = api("/api/health")
check("Health 200", s == 200, f"status={s}")
checks = r.get("checks", {})
check("DB up", checks.get("database") == "up")
check("Telegram configured", checks.get("telegram") == "configured")
check("Config loaded", checks.get("config", "").startswith("loaded"))
check("Secret key set", checks.get("secret_key") == "configured")
check("BSC RPC up", checks.get("bsc_rpc") == "up")
print(f"  Checks: {json.dumps(checks)}")

# 2. MARKET
print("\n--- 2. MARKETPLACE ---")
r, s = api("/api/market")
check("Market 200", s == 200)
check("Has ads", "ads" in r and len(r["ads"]) > 0, f"count={len(r.get('ads',[]))}")
for ad in r.get("ads", [])[:3]:
    print(f"    #{ad['id']} {ad['type']} {ad['amount']}@{ad['price']} by {ad['user']}")
r, s = api("/api/market/price")
check("Price 200", s == 200)
check("Price value", r.get("price", {}).get("usdt_ils") is not None)

# 3. AUTH FLOWS
print("\n--- 3. REGISTRATION ---")
ts = str(int(time.time()))
seller = "qas" + ts
buyer = "qab" + ts

r, s = api("/api/auth/register", "POST", {"username": seller, "password": "Test1234", "email": seller + "@t.com"})
check("Register seller 200", s == 200, f"s={s} r={r}")
r, s = api("/api/auth/register", "POST", {"username": buyer, "password": "Test1234", "email": buyer + "@t.com"})
check("Register buyer 200", s == 200, f"s={s} r={r}")

r, s = api("/api/auth/register", "POST", {"username": seller, "password": "Test1234", "email": seller + "@t.com"})
check("Dup register rejected", s in (400, 409), f"s={s}")

print("\n--- 4. LOGIN ---")
r, s = api("/api/auth/login", "POST", {"username": seller, "password": "Test1234"})
check("Login seller 200", s == 200, f"s={s}")
scsrf = r.get("csrf_token", "")

r, s = api("/api/auth/login", "POST", {"username": buyer, "password": "Test1234"})
check("Login buyer 200", s == 200, f"s={s}")
bcsrf = r.get("csrf_token", "")

r, s = api("/api/auth/login", "POST", {"username": seller, "password": "wrong"})
check("Bad password rejected", s in (401, 403), f"s={s}")

print("\n--- 5. /me ---")
r, s = api("/api/auth/me")
check("/me no auth = 401", s == 401, f"s={s}")

print("\n--- 6. WALLET ---")
r, s = api("/api/wallet")
check("Wallet no auth = 401", s == 401, f"s={s}")

print("\n--- 7. CREATE AD ---")
r, s = api("/api/market/ads/create", "POST", {"type": "BUY", "price_per_usdt": 3.70, "usdt_amount": 50, "min_order": 10, "payment_method": "cash"})
check("Create ad no auth = 401", s == 401, f"s={s}")

print("\n--- 8. ADMIN ---")
r, s = api("/api/admin/users")
check("Admin no auth = 401", s in (401, 403), f"s={s}")
r, s = api("/api/v2/admin/analytics")
check("V2 admin no auth = 401", s in (401, 403), f"s={s}")

print("\n--- 9. FRONTEND PAGES ---")
pages = ["/", "/login", "/register", "/market", "/wallet", "/trades",
         "/create_ad", "/notifications", "/admin", "/admin_login", "/profile",
         "/trader", "/disputes"]
for p in pages:
    r, s = api(p)
    check(f"Page {p}", s in (200, 307), f"s={s}")

print("\n--- 10. V2 ENDPOINTS ---")
r, s = api("/api/v2/trust/testuser1")
check("Trust score", s == 200, f"s={s}")
r, s = api("/api/v2/market/enhanced")
check("Enhanced market", s == 200, f"s={s}")
r, s = api("/api/v2/admin/analytics")
check("Admin analytics", s == 200, f"s={s}")
r, s = api("/api/v2/admin/timeline")
check("Admin timeline", s == 200, f"s={s}")

print("\n--- 11. TELEGRAM WEBHOOK ---")
r, s = api("/telegram/webhook", "POST", {
    "update_id": 999099,
    "message": {"message_id": 999, "from": {"id": 12345, "first_name": "QA", "username": "qa_test"},
                "chat": {"id": 12345, "type": "private"}, "text": "/start", "date": int(time.time())}
}, {"X-Telegram-Bot-Api-Secret-Token": "test"})
check("Webhook reachable", s in (200, 403), f"s={s}")
check("Webhook validates secret", s == 403, f"s={s}")

print("\n--- 12. NOTIFICATIONS ---")
r, s = api("/api/notifications")
check("Notifications no auth = 401", s == 401, f"s={s}")

print("\n--- 13. ERROR HANDLING ---")
r, s = api("/api/nonexistent")
check("API 404", s == 404, f"s={s}")

# SUMMARY
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"  RESULTS: {PASS}/{total} PASSED, {FAIL}/{total} FAILED")
print("=" * 60)

if FAIL > 0:
    print("\n  FAILURES:")
    for name, status, detail in RESULTS:
        if status == "FAIL":
            print(f"    {name}: {detail}")

sys.exit(0 if FAIL == 0 else 1)
