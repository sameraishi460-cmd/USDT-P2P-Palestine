import os
import hmac
import hashlib
import sqlite3
import threading
import traceback
import time
import json

from flask import (
    Flask, render_template, request, redirect,
    session, jsonify, send_from_directory, url_for, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import timedelta, datetime
from urllib.parse import parse_qs, urlparse
from web3 import Web3

import telegram_bot
import price_updater
from trading.bot_engine import TradingBot

# ===============================
# FLASK CONFIG
# ===============================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "USDT_P2P_PALESTINE_SECRET_KEY_DEV")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB upload limit

# Session security
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

os.makedirs("uploads", exist_ok=True)

# ===============================
# TELEGRAM BOT CONFIG
# ===============================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", telegram_bot.TOKEN)
TELEGRAM_WEBAPP_URL = os.environ.get("TELEGRAM_WEBAPP_URL", telegram_bot.WEBAPP_URL)

# ===============================
# DATABASE
# ===============================
DATABASE = "database.db"


def connect():
    con = sqlite3.connect(DATABASE, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


# ===============================
# WEB3 BSC
# ===============================
BSC_RPC = "https://bsc-dataseed.binance.org/"
w3 = Web3(Web3.HTTPProvider(BSC_RPC))

PLATFORM_WALLET = Web3.to_checksum_address(
    "0x659dd7cba24363c903abe3fddfc89eb30ffbf58a"
)
USDT_CONTRACT_ADDR = Web3.to_checksum_address(
    "0x55d398326f99059fF775485246999027B3197955"
)
USDT_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]
usdt_contract = w3.eth.contract(address=USDT_CONTRACT_ADDR, abi=USDT_ABI)


# ===============================
# DATABASE HELPERS
# ===============================
def column_exists(con, table, column):
    result = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in result)


def add_column(con, table, column, datatype):
    if not column_exists(con, table, column):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {datatype}")


# ===============================
# DATABASE SETUP
# ===============================
def setup_database():
    con = connect()

    # USERS
    con.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            phone TEXT DEFAULT '',
            bank TEXT DEFAULT '',
            iban TEXT DEFAULT '',
            payment_method TEXT DEFAULT '',
            usdt_wallet TEXT DEFAULT '',
            rating REAL DEFAULT 5,
            verified INTEGER DEFAULT 0,
            trades_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ACTIVE',
            telegram_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # WALLETS
    con.execute("""
        CREATE TABLE IF NOT EXISTS wallets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            balance REAL DEFAULT 0,
            locked REAL DEFAULT 0
        )
    """)

    # ADS
    con.execute("""
        CREATE TABLE IF NOT EXISTS ads(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            title TEXT,
            amount REAL,
            price REAL,
            payment TEXT,
            status TEXT DEFAULT 'OPEN',
            type TEXT DEFAULT 'SELL',
            min_amount REAL DEFAULT 0,
            max_amount REAL DEFAULT 0,
            created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # TRADES
    con.execute("""
        CREATE TABLE IF NOT EXISTS trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER,
            buyer TEXT,
            seller TEXT,
            amount REAL,
            price REAL,
            fee REAL DEFAULT 0,
            platform_fee REAL DEFAULT 0,
            status TEXT DEFAULT 'PENDING',
            payment_proof TEXT DEFAULT '',
            escrow_status TEXT DEFAULT 'WAITING',
            usdt_tx_hash TEXT DEFAULT '',
            release_tx_hash TEXT DEFAULT '',
            dispute_status TEXT DEFAULT '',
            dispute_reason TEXT DEFAULT '',
            dispute_by TEXT DEFAULT '',
            created DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)

    # CASH ADS
    con.execute("""
        CREATE TABLE IF NOT EXISTS cash_ads(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            title TEXT,
            amount REAL,
            price REAL,
            payment TEXT,
            status TEXT DEFAULT 'OPEN',
            city TEXT DEFAULT '',
            location TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            plan TEXT DEFAULT 'week',
            created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # CASH TRADES
    con.execute("""
        CREATE TABLE IF NOT EXISTS cash_trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER,
            buyer TEXT,
            seller TEXT,
            amount REAL,
            price REAL,
            status TEXT DEFAULT 'PENDING',
            meeting_confirmed INTEGER DEFAULT 0,
            meeting_location TEXT DEFAULT '',
            created DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)

    # MARKET PRICE
    con.execute("""
        CREATE TABLE IF NOT EXISTS market_price(
            id INTEGER PRIMARY KEY,
            usd_ils REAL DEFAULT 3.70,
            usdt_ils REAL DEFAULT 3.70,
            updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # USDT DEPOSITS
    con.execute("""
        CREATE TABLE IF NOT EXISTS usdt_deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            amount REAL,
            tx_hash TEXT UNIQUE,
            sender_wallet TEXT DEFAULT '',
            status TEXT DEFAULT 'PENDING',
            created DATETIME DEFAULT CURRENT_TIMESTAMP,
            confirmed_at DATETIME
        )
    """)

    # WITHDRAW REQUESTS
    con.execute("""
        CREATE TABLE IF NOT EXISTS withdraw_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            amount REAL,
            wallet TEXT,
            status TEXT DEFAULT 'PENDING',
            tx_hash TEXT DEFAULT '',
            created DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        )
    """)

    # NOTIFICATIONS
    con.execute("""
        CREATE TABLE IF NOT EXISTS notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            title TEXT,
            message TEXT,
            seen INTEGER DEFAULT 0,
            created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # MESSAGES (chat)
    con.execute("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            receiver TEXT,
            text TEXT,
            created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # REVIEWS
    con.execute("""
        CREATE TABLE IF NOT EXISTS reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER,
            from_user TEXT,
            to_user TEXT,
            rating INTEGER,
            comment TEXT,
            created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # WALLET HISTORY / LEDGER
    con.execute("""
        CREATE TABLE IF NOT EXISTS wallet_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            amount REAL,
            balance_before REAL DEFAULT 0,
            balance_after REAL DEFAULT 0,
            reference_id INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            created DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # PLATFORM FEES CONFIG
    con.execute("""
        CREATE TABLE IF NOT EXISTS platform_config(
            key TEXT PRIMARY KEY,
            value TEXT,
            updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # DISPUTES
    con.execute("""
        CREATE TABLE IF NOT EXISTS disputes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER,
            trade_type TEXT DEFAULT 'USDT',
            opened_by TEXT,
            reason TEXT,
            evidence TEXT DEFAULT '',
            status TEXT DEFAULT 'OPEN',
            admin_decision TEXT DEFAULT '',
            admin_note TEXT DEFAULT '',
            created DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        )
    """)

    # Migrate old tables
    add_column(con, "cash_ads", "city", "TEXT DEFAULT ''")
    add_column(con, "cash_ads", "location", "TEXT DEFAULT ''")
    add_column(con, "cash_ads", "notes", "TEXT DEFAULT ''")
    add_column(con, "cash_ads", "plan", "TEXT DEFAULT 'week'")
    add_column(con, "ads", "type", "TEXT DEFAULT 'SELL'")
    add_column(con, "ads", "min_amount", "REAL DEFAULT 0")
    add_column(con, "ads", "max_amount", "REAL DEFAULT 0")
    add_column(con, "users", "created_at", "DATETIME DEFAULT ''")
    add_column(con, "trades", "platform_fee", "REAL DEFAULT 0")
    add_column(con, "trades", "dispute_status", "TEXT DEFAULT ''")
    add_column(con, "trades", "dispute_reason", "TEXT DEFAULT ''")
    add_column(con, "trades", "dispute_by", "TEXT DEFAULT ''")
    add_column(con, "trades", "completed_at", "DATETIME")
    add_column(con, "cash_trades", "meeting_confirmed", "INTEGER DEFAULT 0")
    add_column(con, "cash_trades", "meeting_location", "TEXT DEFAULT ''")
    add_column(con, "cash_trades", "completed_at", "DATETIME")
    add_column(con, "withdraw_requests", "tx_hash", "TEXT DEFAULT ''")
    add_column(con, "withdraw_requests", "processed_at", "DATETIME")
    add_column(con, "usdt_deposits", "sender_wallet", "TEXT DEFAULT ''")
    add_column(con, "usdt_deposits", "confirmed_at", "DATETIME")
    # wallet_history columns are created fresh, no migration needed

    # Set default platform config
    defaults = {
        "p2p_fee_percent": "1.0",
        "cash_fee_percent": "1.0",
        "min_fee": "0.1",
        "max_fee": "100.0",
        "platform_name": "USDT P2P Palestine",
        "platform_wallet": PLATFORM_WALLET,
    }
    for key, val in defaults.items():
        existing = con.execute(
            "SELECT 1 FROM platform_config WHERE key=?", (key,)
        ).fetchone()
        if not existing:
            con.execute(
                "INSERT INTO platform_config (key, value) VALUES (?, ?)",
                (key, val)
            )

    # Ensure indexes
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_wallets_user ON wallets(username)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_trades_buyer ON trades(buyer)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_trades_seller ON trades(seller)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ads_user ON ads(user)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(username)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender_receiver ON messages(sender, receiver)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_wallet_history_user ON wallet_history(username)")
    except Exception:
        pass

    # Default market price
    check_price = con.execute(
        "SELECT * FROM market_price WHERE id=1"
    ).fetchone()
    if not check_price:
        con.execute(
            "INSERT INTO market_price (id, usd_ils, usdt_ils) VALUES(1,3.70,3.70)"
        )

    con.commit()
    con.close()


setup_database()
print("DATABASE:", os.path.abspath(DATABASE))


# ===============================
# PLATFORM CONFIG HELPERS
# ===============================
def get_config(key, default="0"):
    con = connect()
    row = con.execute(
        "SELECT value FROM platform_config WHERE key=?", (key,)
    ).fetchone()
    con.close()
    return row["value"] if row else default


def set_config(key, value):
    con = connect()
    con.execute(
        "INSERT OR REPLACE INTO platform_config (key, value, updated) VALUES (?, ?, ?)",
        (key, value, datetime.now())
    )
    con.commit()
    con.close()


# ===============================
# AUTH SYSTEM
# ===============================
def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        return func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect("/admin_login")
        con = connect()
        user = con.execute(
            "SELECT * FROM users WHERE username=?", (session["user"],)
        ).fetchone()
        con.close()
        if not user or user["status"] != "ADMIN":
            return "غير مصرح لك", 403
        return func(*args, **kwargs)
    return wrapper


# ===============================
# WALLET & LEDGER
# ===============================
def create_wallet_if_missing(username):
    con = connect()
    wallet = con.execute(
        "SELECT * FROM wallets WHERE username=?", (username,)
    ).fetchone()
    if not wallet:
        con.execute(
            "INSERT INTO wallets (username, balance, locked) VALUES(?,0,0)",
            (username,)
        )
        con.commit()
    con.close()


def get_balance(username):
    con = connect()
    wallet = con.execute(
        "SELECT * FROM wallets WHERE username=?", (username,)
    ).fetchone()
    con.close()
    if wallet:
        return wallet["balance"], wallet["locked"]
    return 0.0, 0.0


def wallet_log(username, action, amount, ref_id=0, note=""):
    """Record every balance change in the ledger."""
    con = connect()
    wallet = con.execute(
        "SELECT balance FROM wallets WHERE username=?", (username,)
    ).fetchone()
    balance_before = wallet["balance"] if wallet else 0
    balance_after = balance_before + amount if action in (
        "USDT_RECEIVED", "ESCROW_RELEASE", "REFUND", "WITHDRAWAL_REFUND"
    ) else balance_before - amount if action in (
        "ESCROW_LOCK", "PLATFORM_FEE", "WITHDRAWAL"
    ) else balance_before
    # For actions that only affect locked, keep balance_after == balance_before
    if action == "ESCROW_LOCK":
        balance_after = balance_before
    if action == "ESCROW_RELEASE":
        balance_after = balance_before

    con.execute(
        """INSERT INTO wallet_history
        (username, action, amount, balance_before, balance_after, reference_id, note)
        VALUES(?,?,?,?,?,?,?)""",
        (username, action, amount, balance_before, balance_after, ref_id, note)
    )
    con.commit()
    con.close()


def modify_balance(username, amount_delta, action, ref_id=0, note=""):
    """Atomically modify balance with ledger entry."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        wallet = con.execute(
            "SELECT balance, locked FROM wallets WHERE username=?",
            (username,)
        ).fetchone()
        if not wallet:
            con.execute(
                "INSERT INTO wallets (username, balance, locked) VALUES(?,0,0)",
                (username,)
            )
            wallet = {"balance": 0, "locked": 0}

        new_balance = wallet["balance"] + amount_delta
        if new_balance < 0:
            con.execute("ROLLBACK")
            con.close()
            return False

        con.execute(
            "UPDATE wallets SET balance=? WHERE username=?",
            (new_balance, username)
        )
        con.execute(
            """INSERT INTO wallet_history
            (username, action, amount, balance_before, balance_after, reference_id, note)
            VALUES(?,?,?,?,?,?,?)""",
            (username, action, abs(amount_delta),
             wallet["balance"], new_balance, ref_id, note)
        )
        con.commit()
        con.close()
        return True
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        return False


def modify_locked(username, amount_delta):
    """Modify locked balance atomically."""
    con = connect()
    try:
        wallet = con.execute(
            "SELECT locked FROM wallets WHERE username=?", (username,)
        ).fetchone()
        if not wallet:
            con.close()
            return False
        new_locked = wallet["locked"] + amount_delta
        if new_locked < 0:
            con.close()
            return False
        con.execute(
            "UPDATE wallets SET locked=? WHERE username=?",
            (new_locked, username)
        )
        con.commit()
        con.close()
        return True
    except Exception:
        con.close()
        return False


# ===============================
# FEE CALCULATION
# ===============================
def calculate_fee(amount, trade_type="p2p"):
    """Calculate platform fee based on config."""
    if trade_type == "cash":
        fee_percent = float(get_config("cash_fee_percent", "1.0"))
    else:
        fee_percent = float(get_config("p2p_fee_percent", "1.0"))

    min_fee = float(get_config("min_fee", "0.1"))
    max_fee = float(get_config("max_fee", "100.0"))

    fee = round(amount * fee_percent / 100, 2)
    fee = max(fee, min_fee)
    fee = min(fee, max_fee)
    return fee


# ===============================
# NOTIFICATIONS
# ===============================
def notify(username, title, message, send_telegram=False):
    con = connect()
    con.execute(
        "INSERT INTO notifications (username, title, message) VALUES(?,?,?)",
        (username, title, message)
    )
    con.commit()
    con.close()

    if send_telegram:
        try:
            con2 = connect()
            user = con2.execute(
                "SELECT telegram_id FROM users WHERE username=?",
                (username,)
            ).fetchone()
            con2.close()
            if user and user["telegram_id"]:
                telegram_bot.send_message(
                    int(user["telegram_id"]),
                    f"🔔 {title}\n{message}"
                )
        except Exception:
            pass


# ===============================
# CSRF TOKEN
# ===============================
def generate_csrf_token():
    if "_csrf_token" not in session:
        import secrets
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = generate_csrf_token


def validate_csrf():
    token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("_csrf_token"):
        return False
    return True


@app.before_request
def csrf_protect():
    """CSRF protection for state-changing requests."""
    if request.method == "POST":
        # Skip CSRF for telegram auth and payment webhook
        skip_paths = ["/telegram_auth"]
        if request.path not in skip_paths:
            if not validate_csrf():
                flash("خطأ في الأمان، يرجى المحاولة مرة أخرى", "danger")
                return redirect(request.referrer or "/")


# ===============================
# SECURITY HEADERS
# ===============================
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ===============================
# CREATE EXTRA TABLES
# ===============================
def create_extra_tables():
    # Already handled by setup_database
    pass


# ===============================
# CREATE ADMIN
# ===============================
def create_admin_account():
    con = connect()
    admin = con.execute(
        "SELECT * FROM users WHERE username='Admin'"
    ).fetchone()
    if not admin:
        con.execute(
            "INSERT INTO users (username, password, status) VALUES(?,?,?)",
            ("Admin", generate_password_hash(
                os.environ.get("ADMIN_PASSWORD", "SA526614@mer")
            ), "ADMIN")
        )
        con.commit()
        print("ADMIN CREATED")
    con.close()


create_admin_account()


# ===============================
# REGISTER
# ===============================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("بيانات ناقصة", "danger")
            return redirect("/register")

        if len(username) < 3 or len(username) > 30:
            flash("اسم المستخدم يجب أن يكون بين 3 و 30 حرف", "danger")
            return redirect("/register")

        if len(password) < 6:
            flash("كلمة المرور يجب أن تكون 6 أحرف على الأقل", "danger")
            return redirect("/register")

        con = connect()
        try:
            con.execute(
                "INSERT INTO users (username, password) VALUES(?,?)",
                (username, generate_password_hash(password))
            )
            create_wallet_if_missing(username)
            con.commit()
            session["user"] = username
            con.close()
            flash("تم إنشاء الحساب بنجاح", "success")
            return redirect("/dashboard")
        except Exception:
            con.close()
            flash("اسم المستخدم موجود بالفعل", "danger")
            return redirect("/register")

    return render_template("register.html")


# ===============================
# LOGIN
# ===============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        con = connect()
        user = con.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        con.close()

        if user and check_password_hash(user["password"], password):
            if user["status"] == "BANNED":
                flash("الحساب محظور", "danger")
                return redirect("/login")
            session.permanent = True
            session["user"] = username
            return redirect("/dashboard")

        flash("خطأ في بيانات الدخول", "danger")
        return redirect("/login")

    return render_template("login.html")


# ===============================
# TELEGRAM LOGIN (with HMAC verification)
# ===============================
@app.route("/telegram_login")
def telegram_login():
    return render_template("telegram_login.html")


@app.route("/telegram_auth", methods=["POST"])
def telegram_auth():
    telegram_id = request.form.get("telegram_id")
    username = request.form.get("username", "")
    first_name = request.form.get("first_name", "")
    init_data = request.form.get("initData", "")

    # Verify Telegram WebApp initData HMAC
    if init_data:
        try:
            parsed = parse_qs(init_data)
            if "hash" not in parsed:
                return "Invalid Telegram auth", 400

            received_hash = parsed.pop("hash")[0]
            data_check_string = "\n".join(
                f"{k}={v[0]}" for k, v in sorted(parsed.items())
            )
            secret_key = hmac.new(
                b"WebAppData", TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256
            ).digest()
            computed_hash = hmac.new(
                secret_key, data_check_string.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(received_hash, computed_hash):
                return "Telegram verification failed", 403
        except Exception:
            return "Telegram auth error", 400

    if not telegram_id:
        return "Telegram ID missing", 400

    if not username:
        username = "tg_" + str(telegram_id)

    con = connect()
    user = con.execute(
        "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
    ).fetchone()

    if not user:
        con.execute(
            "INSERT INTO users (username, password, telegram_id, first_name) VALUES(?,?,?,?)",
            (username, generate_password_hash(str(telegram_id)),
             telegram_id, first_name)
        )
        create_wallet_if_missing(username)
        con.commit()

    con.close()
    session["user"] = username
    return redirect("/dashboard")


# ===============================
# LOGOUT
# ===============================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ===============================
# ADMIN LOGIN
# ===============================
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        con = connect()
        user = con.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        con.close()

        if (user and user["status"] == "ADMIN"
                and check_password_hash(user["password"], password)):
            session["user"] = username
            return redirect("/admin")

        flash("بيانات الأدمن خاطئة", "danger")
        return redirect("/admin_login")

    return render_template("admin_login.html")


# ===============================
# DASHBOARD
# ===============================
@app.route("/dashboard")
@login_required
def dashboard():
    con = connect()
    user = con.execute(
        "SELECT * FROM users WHERE username=?", (session["user"],)
    ).fetchone()

    if not user:
        con.close()
        session.clear()
        return redirect("/login")

    wallet = con.execute(
        "SELECT * FROM wallets WHERE username=?", (session["user"],)
    ).fetchone()

    trades_count = con.execute(
        "SELECT COUNT(*) FROM trades WHERE buyer=? OR seller=?",
        (session["user"], session["user"])
    ).fetchone()[0]

    recent_trades = con.execute(
        """SELECT * FROM trades WHERE buyer=? OR seller=?
        ORDER BY id DESC LIMIT 5""",
        (session["user"], session["user"])
    ).fetchall()

    recent_notifications = con.execute(
        "SELECT * FROM notifications WHERE username=? ORDER BY id DESC LIMIT 3",
        (session["user"],)
    ).fetchall()

    wallet_balance = wallet["balance"] if wallet else 0
    wallet_locked = wallet["locked"] if wallet else 0

    con.close()

    return render_template(
        "dashboard.html",
        user=user,
        trades=trades_count,
        wallet_balance=wallet_balance,
        wallet_locked=wallet_locked,
        recent_trades=recent_trades,
        recent_notifications=recent_notifications,
    )


# ===============================
# HOME PAGE
# ===============================
@app.route("/")
def home():
    con = connect()
    ads = con.execute(
        "SELECT * FROM ads WHERE status='OPEN' ORDER BY id DESC LIMIT 20"
    ).fetchall()

    cash_ads = con.execute(
        "SELECT * FROM cash_ads WHERE status='OPEN' ORDER BY id DESC LIMIT 10"
    ).fetchall()

    price = con.execute(
        "SELECT * FROM market_price WHERE id=1"
    ).fetchone()

    user = None
    wallet_balance = 0
    if "user" in session:
        user = session["user"]
        wallet = con.execute(
            "SELECT * FROM wallets WHERE username=?", (session["user"],)
        ).fetchone()
        if wallet:
            wallet_balance = wallet["balance"]

    con.close()

    return render_template(
        "index.html", ads=ads, cash_ads=cash_ads,
        price=price, user=user, wallet_balance=wallet_balance
    )


# ===============================
# MARKET
# ===============================
@app.route("/market")
def market():
    con = connect()
    ads = con.execute(
        "SELECT * FROM ads WHERE status='OPEN' ORDER BY id DESC"
    ).fetchall()

    price = con.execute(
        "SELECT * FROM market_price WHERE id=1"
    ).fetchone()

    user = None
    wallet_balance = 0
    if "user" in session:
        wallet = con.execute(
            "SELECT * FROM wallets WHERE username=?", (session["user"],)
        ).fetchone()
        if wallet:
            wallet_balance = wallet["balance"]
        user = session["user"]

    con.close()

    return render_template(
        "market.html", ads=ads, price=price,
        user=user, wallet_balance=wallet_balance
    )


# ===============================
# CREATE USDT AD
# ===============================
@app.route("/create_ad", methods=["GET", "POST"])
@login_required
def create_ad():
    con = connect()
    user = con.execute(
        "SELECT * FROM users WHERE username=?", (session["user"],)
    ).fetchone()
    wallet = con.execute(
        "SELECT * FROM wallets WHERE username=?", (session["user"],)
    ).fetchone()
    wallet_balance = wallet["balance"] if wallet else 0
    price = con.execute(
        "SELECT * FROM market_price WHERE id=1"
    ).fetchone()

    if request.method == "POST":
        if not validate_csrf():
            con.close()
            flash("خطأ في الأمان", "danger")
            return redirect("/create_ad")

        title = request.form.get("title", "").strip()
        amount = float(request.form.get("amount", 0) or 0)
        price_val = float(request.form.get("price", 0) or 0)
        payment = request.form.get("payment", "BANK")
        ad_type = request.form.get("type", "SELL")
        min_amount = float(request.form.get("min_amount", 0) or 0)
        max_amount = float(request.form.get("max_amount", 0) or 0)

        if amount <= 0 or price_val <= 0:
            con.close()
            flash("بيانات غير صحيحة", "danger")
            return redirect("/create_ad")

        # If selling, check balance
        if ad_type == "SELL" and wallet_balance < amount:
            con.close()
            return render_template(
                "create_ad.html", user=user, wallet_balance=wallet_balance,
                price=price, error="insufficient_balance",
                required=amount, available=wallet_balance
            )

        con.execute(
            """INSERT INTO ads (user, title, amount, price, payment, type, min_amount, max_amount)
            VALUES(?,?,?,?,?,?,?,?)""",
            (session["user"], title, amount, price_val, payment,
             ad_type, min_amount, max_amount)
        )
        con.commit()
        con.close()

        flash("تم نشر الإعلان بنجاح", "success")
        return redirect("/market")

    con.close()
    return render_template(
        "create_ad.html", user=user,
        wallet_balance=wallet_balance, price=price
    )


# ===============================
# BUY USDT
# ===============================
@app.route("/buy/<int:id>")
@login_required
def buy(id):
    con = connect()
    ad = con.execute("SELECT * FROM ads WHERE id=?", (id,)).fetchone()

    if not ad:
        con.close()
        flash("الإعلان غير موجود", "danger")
        return redirect("/market")

    if ad["status"] != "OPEN":
        con.close()
        flash("الإعلان مغلق", "danger")
        return redirect("/market")

    if ad["user"] == session["user"]:
        con.close()
        flash("لا يمكنك شراء إعلانك", "danger")
        return redirect("/market")

    seller_wallet = con.execute(
        "SELECT * FROM wallets WHERE username=?", (ad["user"],)
    ).fetchone()

    if not seller_wallet or seller_wallet["balance"] < ad["amount"]:
        con.close()
        flash("البائع لا يملك رصيد USDT كافي", "danger")
        return redirect("/market")

    fee = calculate_fee(ad["price"], "p2p")
    total_cost = ad["price"] + fee

    # Lock seller's USDT
    con.execute(
        "UPDATE wallets SET balance=balance-?, locked=locked+? WHERE username=?",
        (ad["amount"], ad["amount"], ad["user"])
    )
    wallet_log(ad["user"], "ESCROW_LOCK", ad["amount"],
               ref_id=id, note=f"Trade for ad #{id}")

    trade = con.execute(
        """INSERT INTO trades
        (ad_id, buyer, seller, amount, price, fee, platform_fee, status, escrow_status)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (id, session["user"], ad["user"], ad["amount"],
         ad["price"], fee, fee, "PENDING", "LOCKED")
    )
    trade_id = trade.lastrowid

    con.execute("UPDATE ads SET status='SOLD' WHERE id=?", (id,))
    con.commit()
    con.close()

    notify(ad["user"], "تم حجز USDT", f"تم حجز {ad['amount']} USDT للصفقة #{trade_id}")
    notify(session["user"], "تم إنشاء الصفقة", "يمكنك التواصل مع البائع")

    return redirect(f"/trade/{trade_id}")


# ===============================
# TRADE PAGE + CHAT
# ===============================
@app.route("/trade/<int:id>", methods=["GET", "POST"])
@login_required
def trade(id):
    con = connect()
    trade_row = con.execute(
        "SELECT * FROM trades WHERE id=?", (id,)
    ).fetchone()

    if not trade_row:
        con.close()
        flash("الصفقة غير موجودة", "danger")
        return redirect("/dashboard")

    if request.method == "POST":
        text = request.form.get("message", "").strip()
        receiver = request.form.get("receiver", "")

        if text and receiver and len(text) <= 1000:
            con.execute(
                "INSERT INTO messages (sender, receiver, text) VALUES(?,?,?)",
                (session["user"], receiver, text)
            )
            con.commit()

    messages = con.execute(
        """SELECT * FROM messages
        WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
        ORDER BY id ASC""",
        (session["user"], trade_row["seller"],
         trade_row["seller"], session["user"])
    ).fetchall()

    seller_user = con.execute(
        "SELECT * FROM users WHERE username=?", (trade_row["seller"],)
    ).fetchone()
    buyer_user = con.execute(
        "SELECT * FROM users WHERE username=?", (trade_row["buyer"],)
    ).fetchone()

    con.close()

    return render_template(
        "trade.html", trade=trade_row, messages=messages,
        seller_user=seller_user, buyer_user=buyer_user,
        current_user=session["user"]
    )


# ===============================
# CONFIRM PAYMENT BY BUYER
# ===============================
@app.route("/confirm_payment/<int:id>", methods=["POST"])
@login_required
def confirm_payment(id):
    if not validate_csrf():
        return redirect(f"/trade/{id}")

    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade:
        con.close()
        flash("الصفقة غير موجودة", "danger")
        return redirect("/dashboard")

    if trade["buyer"] != session["user"]:
        con.close()
        return "غير مصرح", 403

    if trade["status"] != "PENDING":
        con.close()
        flash("حالة الصفقة لا تسمح بهذا الإجراء", "danger")
        return redirect(f"/trade/{id}")

    con.execute(
        "UPDATE trades SET status='PAYMENT_SENT' WHERE id=?", (id,)
    )
    con.commit()
    con.close()

    notify(trade["seller"], "تم إرسال الدفع",
           f"المشتري أكد إرسال المبلغ للصفقة #{id}", send_telegram=True)

    flash("تم تأكيد إرسال الدفع", "success")
    return redirect(f"/trade/{id}")


# ===============================
# UPLOAD PAYMENT PROOF
# ===============================
@app.route("/upload_payment/<int:id>", methods=["POST"])
@login_required
def upload_payment(id):
    if "proof" not in request.files:
        flash("لم يتم اختيار ملف", "danger")
        return redirect(f"/trade/{id}")

    file = request.files["proof"]
    if file.filename == "":
        flash("الملف فارغ", "danger")
        return redirect(f"/trade/{id}")

    # Validate file type
    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        flash("نوع الملف غير مدعوم", "danger")
        return redirect(f"/trade/{id}")

    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade:
        con.close()
        flash("الصفقة غير موجودة", "danger")
        return redirect("/dashboard")

    if trade["buyer"] != session["user"]:
        con.close()
        return "غير مصرح", 403

    filename = secure_filename(f"payment_{id}_{int(time.time())}{ext}")
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)

    con.execute(
        "UPDATE trades SET payment_proof=? WHERE id=?", (filename, id)
    )
    con.commit()
    con.close()

    notify(trade["seller"], "إثبات دفع", "تم رفع إثبات الدفع", send_telegram=True)
    flash("تم رفع إثبات الدفع", "success")
    return redirect(f"/trade/{id}")


# ===============================
# SELLER RELEASE ESCROW
# ===============================
@app.route("/seller_confirm/<int:id>", methods=["POST"])
@login_required
def seller_confirm(id):
    if not validate_csrf():
        return redirect(f"/trade/{id}")

    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade:
        con.close()
        flash("الصفقة غير موجودة", "danger")
        return redirect("/dashboard")

    if trade["seller"] != session["user"]:
        con.close()
        return "غير مصرح", 403

    if not trade["payment_proof"]:
        con.close()
        flash("لا يمكن التحرير قبل وجود إثبات الدفع", "danger")
        return redirect(f"/trade/{id}")

    if trade["status"] == "COMPLETED":
        con.close()
        flash("الصفقة مكتملة بالفعل", "info")
        return redirect(f"/trade/{id}")

    try:
        con.execute("BEGIN IMMEDIATE")

        # Release locked USDT to buyer
        con.execute(
            "UPDATE wallets SET locked=locked-? WHERE username=?",
            (trade["amount"], trade["seller"])
        )
        con.execute(
            "UPDATE wallets SET balance=balance+? WHERE username=?",
            (trade["amount"], trade["buyer"])
        )

        # Collect platform fee from buyer
        platform_fee = trade["platform_fee"] or 0
        if platform_fee > 0:
            con.execute(
                "UPDATE wallets SET balance=balance-? WHERE username=?",
                (platform_fee, trade["buyer"])
            )

        # Update trade status
        con.execute(
            """UPDATE trades SET status='COMPLETED', escrow_status='RELEASED',
            completed_at=? WHERE id=?""",
            (datetime.now(), id)
        )

        con.commit()
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        flash("حدث خطأ أثناء تحرير USDT", "danger")
        return redirect(f"/trade/{id}")

    # Ledger entries
    wallet_log(trade["seller"], "ESCROW_RELEASE", trade["amount"],
               ref_id=id, note=f"Trade #{id} completed")
    wallet_log(trade["buyer"], "USDT_RECEIVED", trade["amount"],
               ref_id=id, note=f"Trade #{id} received")
    if platform_fee > 0:
        wallet_log(trade["buyer"], "PLATFORM_FEE", platform_fee,
                   ref_id=id, note=f"Trade #{id} fee")

    # Update seller trade count
    con2 = connect()
    con2.execute(
        "UPDATE users SET trades_count = trades_count + 1 WHERE username=?",
        (trade["seller"],)
    )
    con2.execute(
        "UPDATE users SET trades_count = trades_count + 1 WHERE username=?",
        (trade["buyer"],)
    )
    con2.commit()
    con2.close()

    con.close()

    notify(trade["buyer"], "تم استلام USDT",
           f"تم تحويل {trade['amount']} USDT لمحفظتك", send_telegram=True)
    notify(trade["seller"], "تم إنهاء الصفقة",
           "تم تحرير USDT بنجاح")

    flash("تم تحرير USDT بنجاح", "success")
    return redirect(f"/trade/{id}")


# ===============================
# DISPUTE SYSTEM
# ===============================
@app.route("/open_dispute/<int:id>", methods=["POST"])
@login_required
def open_dispute(id):
    if not validate_csrf():
        return redirect(f"/trade/{id}")

    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("يجب إدخال سبب النزاع", "danger")
        return redirect(f"/trade/{id}")

    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade:
        con.close()
        flash("الصفقة غير موجودة", "danger")
        return redirect("/dashboard")

    if session["user"] not in (trade["buyer"], trade["seller"]):
        con.close()
        return "غير مصرح", 403

    if trade["status"] in ("COMPLETED", "CANCELLED", "DISPUTED"):
        con.close()
        flash("لا يمكن فتح نزاع على هذه الصفقة", "danger")
        return redirect(f"/trade/{id}")

    con.execute(
        "UPDATE trades SET status='DISPUTED', dispute_status='OPEN', dispute_reason=?, dispute_by=? WHERE id=?",
        (reason, session["user"], id)
    )
    con.execute(
        """INSERT INTO disputes (trade_id, trade_type, opened_by, reason)
        VALUES(?,?,?,?)""",
        (id, "USDT", session["user"], reason)
    )
    con.commit()
    con.close()

    # Notify both parties and admin
    other = trade["seller"] if session["user"] == trade["buyer"] else trade["buyer"]
    notify(other, "تم فتح نزاع", f"تم فتح نزاع على الصفقة #{id}")
    notify("Admin", "نزاع جديد", f"نزاع على الصفقة #{id}: {reason}")

    flash("تم فتح النزاع بنجاح", "warning")
    return redirect(f"/trade/{id}")


# ===============================
# CANCEL TRADE
# ===============================
@app.route("/cancel_trade/<int:id>", methods=["POST"])
@login_required
def cancel_trade(id):
    if not validate_csrf():
        return redirect(f"/trade/{id}")

    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade:
        con.close()
        flash("الصفقة غير موجودة", "danger")
        return redirect("/dashboard")

    if trade["buyer"] != session["user"]:
        con.close()
        return "غير مصرح", 403

    if trade["status"] not in ("PENDING", "PAYMENT_SENT"):
        con.close()
        flash("لا يمكن إلغاء الصفقة في هذه الحالة", "danger")
        return redirect(f"/trade/{id}")

    try:
        con.execute("BEGIN IMMEDIATE")

        # Unlock seller's USDT
        con.execute(
            "UPDATE wallets SET locked=locked-?, balance=balance+? WHERE username=?",
            (trade["amount"], trade["amount"], trade["seller"])
        )
        con.execute(
            "UPDATE trades SET status='CANCELLED', escrow_status='REFUNDED' WHERE id=?",
            (id,)
        )
        # Re-open the ad
        con.execute(
            "UPDATE ads SET status='OPEN' WHERE id=?", (trade["ad_id"],)
        )
        con.commit()
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        flash("حدث خطأ أثناء الإلغاء", "danger")
        return redirect(f"/trade/{id}")

    wallet_log(trade["seller"], "REFUND", trade["amount"],
               ref_id=id, note=f"Trade #{id} cancelled")

    con.close()

    notify(trade["seller"], "تم إلغاء الصفقة", "تم إلغاء الصفقة وتحرير USDT")

    flash("تم إلغاء الصفقة", "warning")
    return redirect(f"/trade/{id}")


# ===============================
# WALLET PAGE
# ===============================
@app.route("/wallet")
@login_required
def wallet():
    con = connect()
    wallet_row = con.execute(
        "SELECT * FROM wallets WHERE username=?", (session["user"],)
    ).fetchone()
    user = con.execute(
        "SELECT * FROM users WHERE username=?", (session["user"],)
    ).fetchone()

    history = con.execute(
        "SELECT * FROM wallet_history WHERE username=? ORDER BY id DESC LIMIT 50",
        (session["user"],)
    ).fetchall()

    con.close()

    return render_template(
        "wallet.html", wallet=wallet_row, user=user, history=history
    )


# ===============================
# USDT DEPOSIT
# ===============================
@app.route("/usdt_deposit", methods=["GET", "POST"])
@login_required
def usdt_deposit():
    if request.method == "POST":
        if not validate_csrf():
            return redirect("/usdt_deposit")

        amount = float(request.form.get("amount", 0) or 0)
        tx_hash = request.form.get("tx_hash", "").strip()
        sender_wallet = request.form.get("sender_wallet", "").strip()

        if amount <= 0 or not tx_hash:
            flash("بيانات ناقصة", "danger")
            return redirect("/usdt_deposit")

        if len(tx_hash) < 10:
            flash("-hash المعاملة غير صحيح", "danger")
            return redirect("/usdt_deposit")

        con = connect()
        try:
            con.execute(
                """INSERT INTO usdt_deposits (username, amount, tx_hash, sender_wallet)
                VALUES(?,?,?,?)""",
                (session["user"], amount, tx_hash, sender_wallet)
            )
            con.commit()
        except sqlite3.IntegrityError:
            con.close()
            flash("تم إرسال هذا الـ hash من قبل", "danger")
            return redirect("/usdt_deposit")
        con.close()

        try:
            telegram_bot.send_admin(
                f"💰 إيداع USDT جديد\n👤 المستخدم: {session['user']}\n💵 الكمية: {amount} USDT\n🔗 TX: {tx_hash}"
            )
        except Exception:
            pass

        flash("تم إرسال طلب الإيداع — بانتظار المراجعة", "success")
        return redirect("/wallet")

    return render_template(
        "usdt_deposit.html",
        platform_wallet=PLATFORM_WALLET,
        network="BSC",
        token="USDT BEP-20",
        contract=USDT_CONTRACT_ADDR
    )


# ===============================
# CHECK BSC TRANSACTION (improved)
# ===============================
def check_usdt_transaction(tx_hash, expected_amount):
    """Verify a USDT BEP-20 transfer on BSC."""
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if receipt.status != 1:
            return False

        # Check Transfer events to PLATFORM_WALLET
        logs = receipt.logs
        transfer_topic = Web3.keccak(text="Transfer(address,address,uint256)").hex()

        for log in logs:
            topics = [t.hex() if isinstance(t, bytes) else t for t in log.topics]
            if transfer_topic in topics:
                # Check if contract matches
                if log.address.lower() == USDT_CONTRACT_ADDR.lower():
                    # Decode amount from data
                    amount_raw = int(log.data.hex(), 16) if isinstance(log.data, bytes) else int(log.data, 16)
                    amount_usdt = amount_raw / 10**18

                    # Decode recipient
                    to_addr = Web3.to_checksum_address("0x" + topics[2][-40:])

                    if to_addr.lower() == PLATFORM_WALLET.lower():
                        if amount_usdt >= expected_amount:
                            return True

        return False

    except Exception as e:
        print("USDT CHECK ERROR:", e)
        return False


# ===============================
# ADMIN CONFIRM DEPOSIT
# ===============================
@app.route("/admin_confirm_deposit/<int:id>", methods=["POST"])
@admin_required
def admin_confirm_deposit(id):
    if not validate_csrf():
        return redirect("/admin")

    con = connect()
    deposit = con.execute(
        "SELECT * FROM usdt_deposits WHERE id=?", (id,)
    ).fetchone()

    if not deposit:
        con.close()
        flash("الإيداع غير موجود", "danger")
        return redirect("/admin")

    if deposit["status"] == "CONFIRMED":
        con.close()
        flash("تم التأكيد مسبقاً", "info")
        return redirect("/admin")

    verified = check_usdt_transaction(deposit["tx_hash"], deposit["amount"])

    if not verified:
        con.close()
        flash("لم يتم التحقق من المعاملة على الشبكة", "danger")
        return redirect("/admin")

    create_wallet_if_missing(deposit["username"])

    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            "UPDATE wallets SET balance=balance+? WHERE username=?",
            (deposit["amount"], deposit["username"])
        )
        con.execute(
            "UPDATE usdt_deposits SET status='CONFIRMED', confirmed_at=? WHERE id=?",
            (datetime.now(), id)
        )
        con.commit()
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        flash("خطأ أثناء تأكيد الإيداع", "danger")
        return redirect("/admin")

    wallet_log(deposit["username"], "USDT_RECEIVED", deposit["amount"],
               ref_id=id, note=f"Deposit #{id} confirmed")

    con.close()

    notify(deposit["username"], "تم قبول الإيداع",
           f"تم إضافة {deposit['amount']} USDT لمحفظتك", send_telegram=True)

    flash("تم تأكيد الإيداع", "success")
    return redirect("/admin")


# ===============================
# ADMIN REJECT DEPOSIT
# ===============================
@app.route("/admin_reject_deposit/<int:id>", methods=["POST"])
@admin_required
def admin_reject_deposit(id):
    if not validate_csrf():
        return redirect("/admin")

    con = connect()
    con.execute(
        "UPDATE usdt_deposits SET status='REJECTED' WHERE id=?", (id,)
    )
    con.commit()
    con.close()

    flash("تم رفض الإيداع", "warning")
    return redirect("/admin")


# ===============================
# WITHDRAW REQUEST
# ===============================
@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    con = connect()
    wallet_row = con.execute(
        "SELECT * FROM wallets WHERE username=?", (session["user"],)
    ).fetchone()

    if request.method == "POST":
        if not validate_csrf():
            con.close()
            return redirect("/withdraw")

        amount = float(request.form.get("amount", 0) or 0)
        address = request.form.get("wallet", "").strip()

        if amount <= 0:
            con.close()
            flash("كمية غير صحيحة", "danger")
            return redirect("/withdraw")

        if not address or not address.startswith("0x"):
            con.close()
            flash("عنوان المحفظة غير صحيح", "danger")
            return redirect("/withdraw")

        if wallet_row["balance"] < amount:
            con.close()
            flash("الرصيد غير كافي", "danger")
            return redirect("/withdraw")

        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "UPDATE wallets SET balance=balance-? WHERE username=?",
                (amount, session["user"])
            )
            con.execute(
                "INSERT INTO withdraw_requests (username, amount, wallet) VALUES(?,?,?)",
                (session["user"], amount, address)
            )
            con.commit()
        except Exception:
            con.execute("ROLLBACK")
            con.close()
            flash("خطأ في معالجة طلب السحب", "danger")
            return redirect("/withdraw")

        wallet_log(session["user"], "WITHDRAWAL", amount,
                   note=f"Withdrawal to {address[:10]}...")

        con.close()

        try:
            telegram_bot.send_admin(
                f"📤 طلب سحب USDT\n👤 المستخدم: {session['user']}\n💰 الكمية: {amount}\n🏦 العنوان: {address}"
            )
        except Exception:
            pass

        flash("تم إرسال طلب السحب — بانتظار المراجعة", "success")
        return redirect("/wallet")

    con.close()
    return render_template("withdraw.html", wallet=wallet_row)


# ===============================
# ADMIN WITHDRAWAL ACTIONS
# ===============================
@app.route("/admin_approve_withdraw/<int:id>", methods=["POST"])
@admin_required
def admin_approve_withdraw(id):
    if not validate_csrf():
        return redirect("/admin")

    con = connect()
    req = con.execute(
        "SELECT * FROM withdraw_requests WHERE id=?", (id,)
    ).fetchone()

    if not req or req["status"] != "PENDING":
        con.close()
        flash("طلب غير موجود أو تم معالجته", "danger")
        return redirect("/admin")

    con.execute(
        "UPDATE withdraw_requests SET status='APPROVED', processed_at=? WHERE id=?",
        (datetime.now(), id)
    )
    con.commit()
    con.close()

    notify(req["username"], "تم اعتماد السحب",
           f"تم اعتماد طلب سحب {req['amount']} USDT", send_telegram=True)

    flash("تم اعتماد السحب", "success")
    return redirect("/admin")


@app.route("/admin_reject_withdraw/<int:id>", methods=["POST"])
@admin_required
def admin_reject_withdraw(id):
    if not validate_csrf():
        return redirect("/admin")

    con = connect()
    req = con.execute(
        "SELECT * FROM withdraw_requests WHERE id=?", (id,)
    ).fetchone()

    if not req or req["status"] != "PENDING":
        con.close()
        flash("طلب غير موجود", "danger")
        return redirect("/admin")

    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            "UPDATE withdraw_requests SET status='REJECTED', processed_at=? WHERE id=?",
            (datetime.now(), id)
        )
        con.execute(
            "UPDATE wallets SET balance=balance+? WHERE username=?",
            (req["amount"], req["username"])
        )
        con.commit()
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        flash("خطأ أثناء رفض السحب", "danger")
        return redirect("/admin")

    wallet_log(req["username"], "WITHDRAWAL_REFUND", req["amount"],
               ref_id=id, note=f"Withdrawal #{id} rejected")

    con.close()

    notify(req["username"], "تم رفض السحب",
           f"تم رفض طلب سحب {req['amount']} USDT — تم إرجاع الرصيد", send_telegram=True)

    flash("تم رفض السحب وإرجاع الرصيد", "warning")
    return redirect("/admin")


# ===============================
# PROFILE
# ===============================
@app.route("/profile")
@login_required
def profile():
    con = connect()
    user = con.execute(
        "SELECT * FROM users WHERE username=?", (session["user"],)
    ).fetchone()

    completed_trades = con.execute(
        "SELECT COUNT(*) FROM trades WHERE (buyer=? OR seller=?) AND status='COMPLETED'",
        (session["user"], session["user"])
    ).fetchone()[0]

    ads_count = con.execute(
        "SELECT COUNT(*) FROM ads WHERE user=?", (session["user"],)
    ).fetchone()[0]

    con.close()

    return render_template(
        "profile.html", user=user,
        completed_trades=completed_trades, ads_count=ads_count
    )


# ===============================
# EDIT PROFILE
# ===============================
@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    con = connect()

    if request.method == "POST":
        if not validate_csrf():
            con.close()
            return redirect("/edit_profile")

        phone = request.form.get("phone", "").strip()
        bank = request.form.get("bank", "").strip()
        iban = request.form.get("iban", "").strip()
        payment = request.form.get("payment_method", "").strip()
        wallet_addr = request.form.get("usdt_wallet", "").strip()

        con.execute(
            """UPDATE users SET phone=?, bank=?, iban=?, payment_method=?, usdt_wallet=?
            WHERE username=?""",
            (phone, bank, iban, payment, wallet_addr, session["user"])
        )
        con.commit()
        con.close()
        flash("تم حفظ التغييرات", "success")
        return redirect("/profile")

    user = con.execute(
        "SELECT * FROM users WHERE username=?", (session["user"],)
    ).fetchone()
    con.close()

    return render_template("edit_profile.html", user=user)


# ===============================
# SAVE WALLET ADDRESS
# ===============================
@app.route("/save_wallet", methods=["POST"])
@login_required
def save_wallet():
    if not validate_csrf():
        return redirect("/wallet")

    wallet_addr = request.form.get("usdt_wallet", "").strip()
    con = connect()
    con.execute(
        "UPDATE users SET usdt_wallet=? WHERE username=?",
        (wallet_addr, session["user"])
    )
    con.commit()
    con.close()
    flash("تم حفظ عنوان المحفظة", "success")
    return redirect("/wallet")


# ===============================
# REVIEWS
# ===============================
@app.route("/review/<int:id>", methods=["POST"])
@login_required
def review(id):
    rating = int(request.form.get("rating", 5))
    comment = request.form.get("comment", "").strip()[:500]

    rating = max(1, min(5, rating))

    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade or trade["status"] != "COMPLETED":
        con.close()
        flash("لا يمكن التقييم على هذه الصفقة", "danger")
        return redirect("/profile")

    target = (trade["seller"]
              if session["user"] == trade["buyer"] else trade["buyer"])

    # Prevent duplicate reviews
    existing = con.execute(
        "SELECT 1 FROM reviews WHERE trade_id=? AND from_user=?",
        (id, session["user"])
    ).fetchone()
    if existing:
        con.close()
        flash("تم تقييم هذه الصفقة بالفعل", "info")
        return redirect("/profile")

    con.execute(
        "INSERT INTO reviews (trade_id, from_user, to_user, rating, comment) VALUES(?,?,?,?,?)",
        (id, session["user"], target, rating, comment)
    )

    avg = con.execute(
        "SELECT AVG(rating) FROM reviews WHERE to_user=?", (target,)
    ).fetchone()[0]

    if avg:
        con.execute(
            "UPDATE users SET rating=? WHERE username=?",
            (round(avg, 2), target)
        )

    con.commit()
    con.close()

    flash("تم التقييم بنجاح", "success")
    return redirect("/profile")


# ===============================
# NOTIFICATIONS
# ===============================
@app.route("/notifications")
@login_required
def notifications():
    con = connect()
    data = con.execute(
        "SELECT * FROM notifications WHERE username=? ORDER BY id DESC",
        (session["user"],)
    ).fetchall()

    # Mark as seen
    con.execute(
        "UPDATE notifications SET seen=1 WHERE username=?",
        (session["user"],)
    )
    con.commit()
    con.close()

    return render_template("notifications.html", notifications=data)


# ===============================
# CASH ADS
# ===============================
@app.route("/cash_market")
def cash_market():
    con = connect()
    ads = con.execute(
        "SELECT * FROM cash_ads WHERE status='OPEN' ORDER BY id DESC"
    ).fetchall()
    con.close()
    return render_template("cash_market.html", ads=ads)


@app.route("/cash_ad/<int:id>")
def cash_ad(id):
    con = connect()
    ad = con.execute("SELECT * FROM cash_ads WHERE id=?", (id,)).fetchone()
    con.close()

    if not ad:
        flash("الإعلان غير موجود", "danger")
        return redirect("/cash_market")

    return render_template("cash_ad.html", ad=ad)


@app.route("/create_cash_ad", methods=["GET", "POST"])
@login_required
def create_cash_ad():
    con = connect()
    user = con.execute(
        "SELECT * FROM users WHERE username=?", (session["user"],)
    ).fetchone()

    if request.method == "POST":
        if not validate_csrf():
            con.close()
            return redirect("/create_cash_ad")

        amount = float(request.form.get("amount", 0) or 0)
        price = float(request.form.get("price", 0) or 0)
        city = request.form.get("city", "").strip()
        location = request.form.get("location", "").strip()
        notes = request.form.get("notes", "").strip()
        plan = request.form.get("plan", "week")

        if amount <= 0 or price <= 0:
            con.close()
            flash("بيانات غير صحيحة", "danger")
            return redirect("/create_cash_ad")

        title = f"{city} - {location}" if city or location else f"مقابلة {session['user']}"

        con.execute(
            """INSERT INTO cash_ads
            (user, title, amount, price, payment, city, location, notes, plan)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (session["user"], title, amount, price, "CASH",
             city, location, notes, plan)
        )
        con.commit()
        con.close()

        flash("تم نشر إعلان المقابلة بنجاح", "success")
        return redirect("/cash_market")

    wallet = con.execute(
        "SELECT * FROM wallets WHERE username=?", (session["user"],)
    ).fetchone()
    wallet_balance = wallet["balance"] if wallet else 0
    con.close()

    return render_template(
        "create_cash_ad.html", user=user, wallet_balance=wallet_balance
    )


@app.route("/cash_buy/<int:id>")
@login_required
def cash_buy(id):
    con = connect()
    ad = con.execute("SELECT * FROM cash_ads WHERE id=?", (id,)).fetchone()

    if not ad:
        con.close()
        flash("الإعلان غير موجود", "danger")
        return redirect("/cash_market")

    if ad["status"] != "OPEN":
        con.close()
        flash("الإعلان مغلق", "danger")
        return redirect("/cash_market")

    if ad["user"] == session["user"]:
        con.close()
        flash("لا يمكنك شراء إعلانك", "danger")
        return redirect("/cash_market")

    con.execute(
        """INSERT INTO cash_trades (ad_id, buyer, seller, amount, price)
        VALUES(?,?,?,?,?)""",
        (id, session["user"], ad["user"], ad["amount"], ad["price"])
    )
    trade_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.execute("UPDATE cash_ads SET status='SOLD' WHERE id=?", (id,))
    con.commit()
    con.close()

    notify(ad["user"], "طلب شراء كاش",
           "يوجد طلب جديد على إعلانك", send_telegram=True)

    flash("تم إنشاء الصفقة", "success")
    return redirect(f"/cash_trade/{trade_id}")


@app.route("/cash_trade/<int:id>", methods=["GET", "POST"])
@login_required
def cash_trade(id):
    con = connect()
    trade = con.execute(
        "SELECT * FROM cash_trades WHERE id=?", (id,)
    ).fetchone()

    if not trade:
        con.close()
        flash("الصفقة غير موجودة", "danger")
        return redirect("/dashboard")

    if request.method == "POST":
        if not validate_csrf():
            con.close()
            return redirect(f"/cash_trade/{id}")

        action = request.form.get("action", "")

        if action == "confirm_meeting" and trade["seller"] == session["user"]:
            con.execute(
                "UPDATE cash_trades SET meeting_confirmed=1 WHERE id=?", (id,)
            )
            con.commit()
            notify(trade["buyer"], "تم تأكيد المقابلة",
                   "البائع أكد المقابلة")

        elif action == "complete" and trade["buyer"] == session["user"]:
            con.execute(
                "UPDATE cash_trades SET status='COMPLETED', completed_at=? WHERE id=?",
                (datetime.now(), id)
            )
            con.execute(
                "UPDATE cash_ads SET status='COMPLETED' WHERE id=?", (trade["ad_id"],)
            )
            con.commit()
            notify(trade["seller"], "تم إنهاء الصفقة",
                   "المشتري أكمل الصفقة")

        elif action == "cancel":
            con.execute(
                "UPDATE cash_trades SET status='CANCELLED' WHERE id=?", (id,)
            )
            con.execute(
                "UPDATE cash_ads SET status='OPEN' WHERE id=?", (trade["ad_id"],)
            )
            con.commit()
            flash("تم إلغاء الصفقة", "warning")

    # Refresh trade data
    trade = con.execute(
        "SELECT * FROM cash_trades WHERE id=?", (id,)
    ).fetchone()
    ad = con.execute(
        "SELECT * FROM cash_ads WHERE id=?", (trade["ad_id"],)
    ).fetchone() if trade else None
    con.close()

    return render_template(
        "cash_trade.html", trade=trade, ad=ad,
        current_user=session["user"]
    )


# ===============================
# MY ADS
# ===============================
@app.route("/my_ads")
@login_required
def my_ads():
    con = connect()
    ads = con.execute(
        "SELECT * FROM ads WHERE user=? ORDER BY id DESC", (session["user"],)
    ).fetchall()
    cash_ads = con.execute(
        "SELECT * FROM cash_ads WHERE user=? ORDER BY id DESC", (session["user"],)
    ).fetchall()
    con.close()
    return render_template("my_ads.html", ads=ads, cash_ads=cash_ads)


# ===============================
# MY TRADES
# ===============================
@app.route("/my_trades")
@login_required
def my_trades():
    con = connect()
    trades = con.execute(
        "SELECT * FROM trades WHERE buyer=? OR seller=? ORDER BY id DESC",
        (session["user"], session["user"])
    ).fetchall()

    cash_trades = con.execute(
        "SELECT * FROM cash_trades WHERE buyer=? OR seller=? ORDER BY id DESC",
        (session["user"], session["user"])
    ).fetchall()
    con.close()

    return render_template(
        "my_trades.html", trades=trades,
        cash_trades=cash_trades, username=session["user"]
    )


# ===============================
# TRADING BOT
# ===============================
paper_bots = {}


@app.route("/trading_bot")
@login_required
def trading_bot_page():
    username = session.get("user")
    bot = paper_bots.get(username)
    stats = None
    if bot and hasattr(bot, "stats"):
        stats = bot.stats()
    return render_template("trading_bot.html", bot=bot, stats=stats)


@app.route("/trading_bot/start", methods=["POST"])
@login_required
def start_trading_bot():
    if not validate_csrf():
        return redirect("/trading_bot")

    username = session.get("user")
    if username in paper_bots:
        flash("البوت يعمل بالفعل!", "info")
        return redirect("/trading_bot")

    try:
        bot = TradingBot(
            symbol="BTCUSDT", interval="1h",
            capital=2500, risk_percent=0.5,
            stop_loss_percent=1.0, take_profit_percent=1.5
        )
        paper_bots[username] = bot
        thread = threading.Thread(target=bot.start, daemon=True)
        thread.start()
        flash("تم تشغيل بوت التداول التجريبي بنجاح", "success")
    except Exception as e:
        paper_bots.pop(username, None)
        flash(f"حدث خطأ: {str(e)}", "danger")

    return redirect("/trading_bot")


@app.route("/trading_bot/stop", methods=["POST"])
@login_required
def stop_trading_bot():
    if not validate_csrf():
        return redirect("/trading_bot")

    username = session.get("user")
    bot = paper_bots.get(username)
    if bot:
        try:
            bot.stop()
        except Exception:
            pass
        finally:
            paper_bots.pop(username, None)
        flash("تم إيقاف بوت التداول", "warning")
    else:
        flash("لا يوجد بوت نشط", "info")

    return redirect("/trading_bot")


# ===============================
# ADMIN PANEL
# ===============================
@app.route("/admin")
@admin_required
def admin():
    con = connect()

    total_users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active_users = con.execute(
        "SELECT COUNT(*) FROM users WHERE status='ACTIVE'"
    ).fetchone()[0]

    total_trades = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    completed_trades = con.execute(
        "SELECT COUNT(*) FROM trades WHERE status='COMPLETED'"
    ).fetchone()[0]
    active_trades = con.execute(
        "SELECT COUNT(*) FROM trades WHERE status IN ('PENDING','PAYMENT_SENT')"
    ).fetchone()[0]

    total_volume = con.execute(
        "SELECT COALESCE(SUM(amount),0) FROM trades WHERE status='COMPLETED'"
    ).fetchone()[0]

    total_fees = con.execute(
        "SELECT COALESCE(SUM(platform_fee),0) FROM trades WHERE status='COMPLETED'"
    ).fetchone()[0]

    pending_deposits = con.execute(
        "SELECT COUNT(*) FROM usdt_deposits WHERE status='PENDING'"
    ).fetchone()[0]

    pending_withdrawals = con.execute(
        "SELECT COUNT(*) FROM withdraw_requests WHERE status='PENDING'"
    ).fetchone()[0]

    open_disputes = con.execute(
        "SELECT COUNT(*) FROM trades WHERE status='DISPUTED'"
    ).fetchone()[0]

    users = con.execute(
        "SELECT * FROM users ORDER BY id DESC LIMIT 50"
    ).fetchall()

    trades = con.execute(
        "SELECT * FROM trades ORDER BY id DESC LIMIT 30"
    ).fetchall()

    deposits = con.execute(
        "SELECT * FROM usdt_deposits ORDER BY id DESC LIMIT 30"
    ).fetchall()

    withdrawals = con.execute(
        "SELECT * FROM withdraw_requests ORDER BY id DESC LIMIT 30"
    ).fetchall()

    cash_ads_list = con.execute(
        "SELECT * FROM cash_ads ORDER BY id DESC LIMIT 20"
    ).fetchall()

    con.close()

    return render_template(
        "admin.html",
        users=users, trades=trades, deposits=deposits,
        withdrawals=withdrawals, cash_ads=cash_ads_list,
        total_users=total_users, active_users=active_users,
        total_trades=total_trades, completed_trades=completed_trades,
        active_trades=active_trades, total_volume=total_volume,
        total_fees=total_fees, pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals, open_disputes=open_disputes,
    )


# ===============================
# ADMIN: MANAGE USERS
# ===============================
@app.route("/admin_ban_user/<username>", methods=["POST"])
@admin_required
def admin_ban_user(username):
    if not validate_csrf():
        return redirect("/admin")

    con = connect()
    con.execute(
        "UPDATE users SET status='BANNED' WHERE username=?", (username,)
    )
    con.commit()
    con.close()
    flash(f"تم حظر المستخدم {username}", "warning")
    return redirect("/admin")


@app.route("/admin_unban_user/<username>", methods=["POST"])
@admin_required
def admin_unban_user(username):
    if not validate_csrf():
        return redirect("/admin")

    con = connect()
    con.execute(
        "UPDATE users SET status='ACTIVE' WHERE username=?", (username,)
    )
    con.commit()
    con.close()
    flash(f"تم إلغاء حظر {username}", "success")
    return redirect("/admin")


@app.route("/admin_verify_user/<username>", methods=["POST"])
@admin_required
def admin_verify_user(username):
    if not validate_csrf():
        return redirect("/admin")

    con = connect()
    con.execute(
        "UPDATE users SET verified=1 WHERE username=?", (username,)
    )
    con.commit()
    con.close()
    flash(f"تم التحقق من {username}", "success")
    return redirect("/admin")


# ===============================
# ADMIN: RESOLVE DISPUTE
# ===============================
@app.route("/admin_resolve_dispute/<int:trade_id>", methods=["POST"])
@admin_required
def admin_resolve_dispute(trade_id):
    if not validate_csrf():
        return redirect("/admin")

    action = request.form.get("action", "")
    con = connect()
    trade = con.execute(
        "SELECT * FROM trades WHERE id=?", (trade_id,)
    ).fetchone()

    if not trade:
        con.close()
        flash("الصفقة غير موجودة", "danger")
        return redirect("/admin")

    try:
        con.execute("BEGIN IMMEDIATE")

        if action == "release":
            # Release to buyer
            con.execute(
                "UPDATE wallets SET locked=locked-? WHERE username=?",
                (trade["amount"], trade["seller"])
            )
            con.execute(
                "UPDATE wallets SET balance=balance+? WHERE username=?",
                (trade["amount"], trade["buyer"])
            )
            con.execute(
                "UPDATE trades SET status='COMPLETED', escrow_status='RELEASED', dispute_status='RESOLVED', completed_at=?, admin_decision='RELEASED' WHERE id=?",
                (datetime.now(), trade_id)
            )
            wallet_log(trade["seller"], "ESCROW_RELEASE", trade["amount"],
                       ref_id=trade_id, note="Dispute resolved - release to buyer")

        elif action == "refund":
            # Refund to seller
            con.execute(
                "UPDATE wallets SET locked=locked-?, balance=balance+? WHERE username=?",
                (trade["amount"], trade["amount"], trade["seller"])
            )
            con.execute(
                "UPDATE trades SET status='CANCELLED', escrow_status='REFUNDED', dispute_status='RESOLVED', admin_decision='REFUNDED' WHERE id=?",
                (trade_id,)
            )
            wallet_log(trade["seller"], "REFUND", trade["amount"],
                       ref_id=trade_id, note="Dispute resolved - refund to seller")

        con.commit()
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        flash("خطأ أثناء معالجة النزاع", "danger")
        return redirect("/admin")

    # Update dispute record
    con2 = connect()
    con2.execute(
        "UPDATE disputes SET status='RESOLVED', admin_decision=?, resolved_at=? WHERE trade_id=?",
        (action.upper(), datetime.now(), trade_id)
    )
    con2.commit()
    con2.close()

    con.close()

    buyer_notify = "تم تحرير USDT لك" if action == "release" else "تم إلغاء الصفقة"
    seller_notify = "تم إلغاء الصفقة" if action == "release" else "تم إرجاع USDT لك"

    notify(trade["buyer"], "قرار النزاع", buyer_notify, send_telegram=True)
    notify(trade["seller"], "قرار النزاع", seller_notify, send_telegram=True)

    flash("تم حل النزاع", "success")
    return redirect("/admin")


# ===============================
# ADMIN: PRICE CONTROL
# ===============================
@app.route("/admin_price", methods=["GET", "POST"])
@admin_required
def admin_price():
    con = connect()

    if request.method == "POST":
        if not validate_csrf():
            con.close()
            return redirect("/admin_price")

        usd = float(request.form.get("usd_ils", 0) or 0)
        usdt = float(request.form.get("usdt_ils", 0) or 0)
        con.execute(
            "UPDATE market_price SET usd_ils=?, usdt_ils=?, updated=? WHERE id=1",
            (usd, usdt, datetime.now())
        )
        con.commit()

    price = con.execute("SELECT * FROM market_price WHERE id=1").fetchone()
    con.close()
    return render_template("admin_price.html", price=price)


# ===============================
# ADMIN: FEE CONFIGURATION
# ===============================
@app.route("/admin_commission", methods=["GET", "POST"])
@admin_required
def admin_commission():
    con = connect()

    if request.method == "POST":
        if not validate_csrf():
            con.close()
            return redirect("/admin_commission")

        p2p_fee = request.form.get("p2p_fee_percent", "1.0")
        cash_fee = request.form.get("cash_fee_percent", "1.0")
        min_fee = request.form.get("min_fee", "0.1")
        max_fee = request.form.get("max_fee", "100.0")

        set_config("p2p_fee_percent", p2p_fee)
        set_config("cash_fee_percent", cash_fee)
        set_config("min_fee", min_fee)
        set_config("max_fee", max_fee)
        flash("تم حفظ إعدادات العمولة", "success")

    config = {
        "p2p_fee_percent": get_config("p2p_fee_percent", "1.0"),
        "cash_fee_percent": get_config("cash_fee_percent", "1.0"),
        "min_fee": get_config("min_fee", "0.1"),
        "max_fee": get_config("max_fee", "100.0"),
    }

    total_fees = con.execute(
        "SELECT COALESCE(SUM(platform_fee),0) FROM trades WHERE status='COMPLETED'"
    ).fetchone()[0]

    con.close()
    return render_template(
        "admin_commission.html", config=config, total_fees=total_fees
    )


# ===============================
# ADMIN: WALLET VIEW
# ===============================
@app.route("/admin_wallet")
@admin_required
def admin_wallet():
    con = connect()
    wallets = con.execute(
        """SELECT w.*, u.username, u.verified
        FROM wallets w JOIN users u ON w.username=u.username
        ORDER BY w.balance DESC"""
    ).fetchall()
    con.close()
    return render_template("admin_wallet.html", wallets=wallets)


# ===============================
# ADMIN: CASH ADS
# ===============================
@app.route("/admin_cash_ads")
@admin_required
def admin_cash_ads():
    con = connect()
    ads = con.execute(
        "SELECT * FROM cash_ads ORDER BY id DESC"
    ).fetchall()
    con.close()
    return render_template("admin_cash_ads.html", ads=ads)


# ===============================
# ADMIN: SEARCH
# ===============================
@app.route("/admin_search", methods=["GET", "POST"])
@admin_required
def admin_search():
    results = None
    query = ""
    con = connect()

    if request.method == "POST":
        query = request.form.get("q", "").strip()
        if query:
            users = con.execute(
                "SELECT * FROM users WHERE username LIKE ?",
                (f"%{query}%",)
            ).fetchall()
            trades = con.execute(
                "SELECT * FROM trades WHERE buyer LIKE ? OR seller LIKE ?",
                (f"%{query}%", f"%{query}%")
            ).fetchall()
            deposits = con.execute(
                "SELECT * FROM usdt_deposits WHERE username LIKE ?",
                (f"%{query}%",)
            ).fetchall()
            results = {
                "users": users,
                "trades": trades,
                "deposits": deposits
            }

    con.close()
    return render_template(
        "admin_search.html", results=results, query=query
    )


# ===============================
# ADMIN: USDT DEPOSITS
# ===============================
@app.route("/admin_usdt_deposits")
@admin_required
def admin_usdt_deposits():
    con = connect()
    deposits = con.execute(
        "SELECT * FROM usdt_deposits ORDER BY id DESC"
    ).fetchall()
    con.close()
    return render_template("admin_usdt_deposits.html", deposits=deposits)


# ===============================
# ADMIN: ADD USDT TO USER
# ===============================
@app.route("/admin_credit_user", methods=["POST"])
@admin_required
def admin_credit_user():
    if not validate_csrf():
        return redirect("/admin")

    username = request.form.get("username", "").strip()
    amount = float(request.form.get("amount", 0) or 0)

    if amount <= 0 or not username:
        flash("بيانات غير صحيحة", "danger")
        return redirect("/admin")

    create_wallet_if_missing(username)
    success = modify_balance(username, amount, "ADMIN_CREDIT",
                             note=f"Admin credit by {session['user']}")

    if success:
        flash(f"تم إضافة {amount} USDT لـ {username}", "success")
    else:
        flash("خطأ أثناء الإضافة", "danger")

    return redirect("/admin")


# ===============================
# ALL ADS PAGE
# ===============================
@app.route("/all_ads")
def all_ads():
    con = connect()
    ads = con.execute(
        "SELECT * FROM ads WHERE status='OPEN' ORDER BY id DESC"
    ).fetchall()
    price = con.execute("SELECT * FROM market_price WHERE id=1").fetchone()
    con.close()
    return render_template("all_ads.html", ads=ads, price=price)


# ===============================
# PAYMENT SUCCESS
# ===============================
@app.route("/payment_success")
def payment_success():
    return render_template("payment_success.html")


# ===============================
# UPLOADS
# ===============================
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ===============================
# START THREADS
# ===============================
def start_bot():
    try:
        telegram_bot.bot_loop()
    except Exception:
        print(traceback.format_exc())


def update_prices():
    while True:
        try:
            price_updater.update_price()
        except Exception as e:
            print("PRICE ERROR", e)
        time.sleep(3600)


try:
    threading.Thread(target=start_bot, daemon=True).start()
except Exception:
    print(traceback.format_exc())

try:
    threading.Thread(target=update_prices, daemon=True).start()
except Exception:
    print(traceback.format_exc())


# ===============================
# ERROR HANDLER
# ===============================
@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(error):
    return render_template("500.html"), 500


@app.errorhandler(Exception)
def handle_error(error):
    print(traceback.format_exc())
    return render_template("500.html"), 500


# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
