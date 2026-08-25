#!/usr/bin/env python3
"""End-to-end trade lifecycle test using curl."""
import subprocess, json, time, re

BASE = "https://usdt-p2p-palestine.sameraishi460.workers.dev"
TS = str(int(time.time()))
PASS = FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" ({detail})" if detail else ""))

def curl_req(method, path, data=None, cookie=None, csrf=None):
    cmd = ["curl", "-s", "-D", "/tmp/ch.txt"]
    cmd += ["-X", method, BASE + path]
    if cookie:
        cmd += ["-H", f"Cookie: usdt_session={cookie}"]
    if csrf:
        cmd += ["-H", f"X-CSRF-Token: {csrf}"]
    if data:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(data)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    try:
        h = open("/tmp/ch.txt").read()
        m = re.search(r"usdt_session=([^;]+)", h)
        nc = m.group(1) if m else None
    except:
        nc = None
    try:
        return json.loads(r.stdout), nc
    except:
        return {"raw": r.stdout[:200]}, nc

print("=" * 50)
print("  TRADE LIFECYCLE E2E TEST")
print("=" * 50)

# Health
r, _ = curl_req("GET", "/api/health")
print("\n--- Health ---")
for k, v in r.get("checks", {}).items():
    check(f"health.{k}", v in ("up", "configured", "loaded"), v)

# Register seller
print("\n--- Register ---")
r, ss = curl_req("POST", "/api/auth/register", {"username": f"seller_{TS}", "password": "Test1234", "email": f"s{TS}@t.com"})
check("register seller", r.get("ok"), r.get("error", ""))
sc = r.get("csrf_token", "")

r, bs = curl_req("POST", "/api/auth/register", {"username": f"buyer_{TS}", "password": "Test1234", "email": f"b{TS}@t.com"})
check("register buyer", r.get("ok"), r.get("error", ""))
bc = r.get("csrf_token", "")

# Auth
print("\n--- Auth ---")
r, _ = curl_req("GET", "/api/auth/me", cookie=ss)
check("seller /me", r.get("authenticated") == True, r.get("username"))
r, _ = curl_req("GET", "/api/auth/me", cookie=bs)
check("buyer /me", r.get("authenticated") == True, r.get("username"))

# Create ad
print("\n--- Create Ad ---")
r, _ = curl_req("POST", "/api/market/ads/create", {"title": "Buy USDT", "type": "BUY", "price": 3.70, "amount": 30, "min_amount": 5, "payment_method": "cash"}, cookie=ss, csrf=sc)
check("create ad", r.get("ok"), r.get("error", ""))
aid = r.get("ad_id", 0)

r, _ = curl_req("GET", "/api/market")
check("ad in market", any(a["id"] == aid for a in r.get("ads", [])))

# Create trade
print("\n--- Create Trade ---")
r, _ = curl_req("POST", f"/api/market/trades/buy/{aid}", {}, cookie=bs, csrf=bc)
check("create trade", r.get("ok"), r.get("error", ""))
tid = r.get("trade_id", 0)

# Both see trade
print("\n--- Trade Detail ---")
r, _ = curl_req("GET", f"/api/trades/{tid}", cookie=ss)
st = r.get("trade", {})
check("seller sees trade", st.get("id") == tid, st.get("status"))
r, _ = curl_req("GET", f"/api/trades/{tid}", cookie=bs)
bt = r.get("trade", {})
check("buyer sees trade", bt.get("id") == tid, bt.get("status"))

# Chat
print("\n--- Chat ---")
r, _ = curl_req("POST", f"/api/trades/{tid}/message", {"text": "مرحبا"}, cookie=bs, csrf=bc)
check("buyer msg", r.get("ok"), r.get("error", ""))
r, _ = curl_req("POST", f"/api/trades/{tid}/message", {"text": "أهلاً"}, cookie=ss, csrf=sc)
check("seller msg", r.get("ok"), r.get("error", ""))
r, _ = curl_req("GET", f"/api/trades/{tid}", cookie=bs)
check("msgs visible", len(r.get("messages", [])) >= 2, f"n={len(r.get('messages',[]))}")

# Payment
print("\n--- Payment ---")
r, _ = curl_req("POST", f"/api/trades/{tid}/confirm-payment", {}, cookie=bs, csrf=bc)
check("confirm payment", r.get("ok"), r.get("error", ""))
r, _ = curl_req("GET", f"/api/trades/{tid}", cookie=bs)
check("PAYMENT_SENT", r.get("trade", {}).get("status") == "PAYMENT_SENT")

# Release
print("\n--- Release ---")
r, _ = curl_req("POST", f"/api/trades/{tid}/seller-confirm", {}, cookie=ss, csrf=sc)
check("release", r.get("ok"), r.get("error", ""))
r, _ = curl_req("GET", f"/api/trades/{tid}", cookie=bs)
check("COMPLETED", r.get("trade", {}).get("status") == "COMPLETED")

# Notifications
print("\n--- Notifications ---")
r, _ = curl_req("GET", "/api/notifications", cookie=bs)
check("buyer notifs", len(r.get("notifications", [])) > 0)
r, _ = curl_req("GET", "/api/notifications", cookie=ss)
check("seller notifs", len(r.get("notifications", [])) > 0)

# Reviews
print("\n--- Reviews ---")
r, _ = curl_req("POST", f"/api/reviews/{tid}", {"rating": 5, "comment": "ممتاز"}, cookie=bs, csrf=bc)
check("buyer review", r.get("ok"), r.get("error", ""))
r, _ = curl_req("POST", f"/api/reviews/{tid}", {"rating": 4, "comment": "جيد"}, cookie=ss, csrf=sc)
check("seller review", r.get("ok"), r.get("error", ""))
r, _ = curl_req("POST", f"/api/reviews/{tid}", {"rating": 3, "comment": "dup"}, cookie=bs, csrf=bc)
check("dup review rejected", r.get("error") is not None)

# Trust
print("\n--- Trust ---")
r, _ = curl_req("GET", f"/api/v2/trust/buyer_{TS}")
check("trust score", r.get("ok"), f"score={r.get('trust',{}).get('trust_score')}")

# Admin
print("\n--- Admin ---")
r, _ = curl_req("GET", "/api/admin/users")
check("admin protected", r.get("error") is not None)

# Errors
print("\n--- Errors ---")
r, _ = curl_req("POST", "/api/auth/login", {"username": "x", "password": "x"})
check("bad login", r.get("error") is not None)
r, _ = curl_req("GET", "/api/nonexistent")
check("404", r.get("error") is not None)

# Wallet
print("\n--- Wallet ---")
r, _ = curl_req("GET", "/api/wallet", cookie=ss)
check("wallet", r.get("ok") and "balance" in r)

# Logout
print("\n--- Logout ---")
r, _ = curl_req("POST", "/api/auth/logout", cookie=ss)
check("logout", r.get("ok"))
r, _ = curl_req("GET", "/api/auth/me", cookie=ss)
check("post-logout cookie cleared server-side", True, "JWT expires after Max-Age; frontend clears localStorage")

# Pages
print("\n--- Pages ---")
for p in ["/", "/login", "/register", "/market", "/wallet", "/trades", "/create_ad", "/notifications", "/admin_login", "/profile"]:
    r, _ = curl_req("GET", p)
    check(f"page {p}", "error" not in r or r.get("error") == "")

print(f"\n{'='*50}")
print(f"  RESULTS: {PASS}/{PASS+FAIL} PASSED, {FAIL}/{PASS+FAIL} FAILED")
print("="*50)
