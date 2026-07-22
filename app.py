from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import os
import shutil
from datetime import datetime, timedelta
import traceback
import threading
import telegram_bot
import price_updater


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


with app.app_context():
    db.create_all()
app.config["PERMANENT_SESSION_LIFETIME"] = 2592000
app.secret_key = "FINAL_USDT_P2P_PALESTINE_SECRET_KEY"
app.permanent_session_lifetime = timedelta(days=30)

DATABASE = "database.db"
print("DATABASE LOCATION:", os.path.abspath(DATABASE))
PLATFORM_WALLET = "0x659dd7cba24363c903abe3fddfc89eb30ffbf58a"

# =========================
# 1. DATABASE SETUP
# =========================

def connect():
    con = sqlite3.connect(DATABASE)
    con.row_factory = sqlite3.Row
    return con


def column_exists(con, table, column):
    data = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(x["name"] == column for x in data)


def add_column(con, table, column, datatype):
    if not column_exists(con, table, column):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {datatype}")


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
        wallet TEXT DEFAULT '',
        rating REAL DEFAULT 5,
        verified INTEGER DEFAULT 0,
        trades_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ACTIVE'
    )
    """)
    
    add_column(con, "users", "telegram_id", "TEXT")

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
        status TEXT DEFAULT 'PENDING',
        dispute TEXT DEFAULT 'NONE',
        created DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # CASH ADS
    con.execute("""
    CREATE TABLE IF NOT EXISTS cash_ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        amount REAL,
        price REAL,
        city TEXT,
        location TEXT,
        notes TEXT,
        fee REAL DEFAULT 0,
        status TEXT DEFAULT 'OPEN'
    )
    """)

    # CASH AD PAYMENTS
    con.execute("""
    CREATE TABLE IF NOT EXISTS cash_ad_payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        amount REAL,
        plan TEXT,
        days INTEGER,
        wallet TEXT,
        status TEXT DEFAULT 'PENDING',
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
        meeting_time TEXT DEFAULT '',
        status TEXT DEFAULT 'WAITING'
    )
    """)

    # MESSAGES
    con.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        receiver TEXT,
        text TEXT,
        created DATETIME DEFAULT CURRENT_TIMESTAMP
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

    # REVIEWS
    con.execute("""
    CREATE TABLE IF NOT EXISTS reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id INTEGER,
        from_user TEXT,
        to_user TEXT,
        rating INTEGER,
        comment TEXT
    )
    """)

    # COMMISSION
    con.execute("""
    CREATE TABLE IF NOT EXISTS commission(
        id INTEGER PRIMARY KEY,
        trade_fee REAL DEFAULT 1,
        cash_fee REAL DEFAULT 2
    )
    """)

    fee = con.execute("SELECT * FROM commission WHERE id=1").fetchone()
    if not fee:
        con.execute("INSERT INTO commission (id, trade_fee, cash_fee) VALUES(1, 1, 2)")

    # PLATFORM PROFIT
    con.execute("""
    CREATE TABLE IF NOT EXISTS platform_profit(
        id INTEGER PRIMARY KEY,
        total REAL DEFAULT 0
    )
    """)

    profit = con.execute("SELECT * FROM platform_profit WHERE id=1").fetchone()
    if not profit:
        con.execute("INSERT INTO platform_profit (id, total) VALUES(1, 0)")

    # MARKET PRICE
    con.execute("""
    CREATE TABLE IF NOT EXISTS market_price(
        id INTEGER PRIMARY KEY,
        usd_ils REAL DEFAULT 3.70,
        usdt_ils REAL DEFAULT 3.70,
        updated DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    price = con.execute(
        "SELECT * FROM market_price WHERE id=1"
    ).fetchone()

    if not price:
        con.execute(
            """
            INSERT INTO market_price
            (id, usd_ils, usdt_ils)
            VALUES(1, 3.70, 3.70)
            """
        )

    con.commit()
    con.close()


setup_database()

con = connect()
print(con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
con.close()


def create_admin_account():

    con = connect()

    username = "Admin"
    password = "SA526614@mer"

    exists = con.execute(
        "SELECT * FROM users WHERE username=?",
        (username,)
    ).fetchone()

    if not exists:

        con.execute(
            """
            INSERT INTO users
            (username, password, status)
            VALUES (?, ?, ?)
            """,
            (
                username,
                generate_password_hash(password),
                "ADMIN"
            )
        )

        con.commit()
        print("ADMIN CREATED")

    else:
        print("ADMIN EXISTS")

    con.close()


create_admin_account()


# =========================
# 2. AUTH SYSTEM & DECORATORS
# =========================

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
            return redirect("/login")

        con = connect()
        user = con.execute("SELECT * FROM users WHERE username=?", (session["user"],)).fetchone()
        con.close()

        if not user or user["status"] != "ADMIN":
            return "غير مصرح لك بالدخول", 403

        return func(*args, **kwargs)
    return wrapper


def notify(username, title, message):
    con = connect()
    con.execute(
        "INSERT INTO notifications (username, title, message) VALUES(?, ?, ?)",
        (username, title, message)
    )
    con.commit()
    con.close()


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            return "بيانات ناقصة"

        con = connect()
        try:
            con.execute(
                "INSERT INTO users (username, password) VALUES(?, ?)",
                (username, generate_password_hash(password))
            )
            con.commit()
            con.close()
            session.permanent = True
            session["user"] = username
            return redirect("/dashboard")
        except:
            con.close()
            return "المستخدم موجود"

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        remember = request.form.get("remember")

        con = connect()

        user = con.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        con.close()


        if user and check_password_hash(user["password"], password):

            if user["status"] == "BANNED":
                return "الحساب محظور"


            session.permanent = True
            session["user"] = username


            # حفظ الحساب
            if remember:

                session.permanent = True

                app.permanent_session_lifetime = 60 * 60 * 24 * 30
                # 30 يوم


            return redirect("/dashboard")


        return "خطأ في البيانات"


    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/telegram_login")
def telegram_login():
    return render_template("telegram_login.html")


@app.route("/telegram_webapp")
def telegram_webapp():
    return render_template("telegram_webapp.html")


@app.route("/telegram_auth")
def telegram_auth():
    telegram_id = request.args.get("id")
    username = request.args.get("username")

    print("TELEGRAM DATA:", telegram_id, username)

    if not telegram_id:
        return "لا توجد بيانات تلجرام"

    con = connect()

    user = con.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()

    if not user:
        new_username = username if username else f"telegram_{telegram_id}"

        try:
            con.execute(
                """
                INSERT INTO users
                (username, password, telegram_id)
                VALUES(?,?,?)
                """,
                (
                    new_username,
                    generate_password_hash("telegram"),
                    telegram_id
                )
            )

            con.commit()
            session["user"] = new_username

        except Exception as e:
            print("CREATE USER ERROR:", e)
            session["user"] = new_username

    else:
        session["user"] = user["username"]

    con.close()

    return redirect("/dashboard")


# =========================
# 3. HOME & USDT ADS
# =========================

@app.route("/")
def home():

    con = connect()

    ads = con.execute(
        "SELECT * FROM ads WHERE status='OPEN' ORDER BY id DESC"
    ).fetchall()

    cash_ads = con.execute(
        "SELECT * FROM cash_ads WHERE status='OPEN' ORDER BY id DESC"
    ).fetchall()

    price = con.execute(
        "SELECT * FROM market_price WHERE id=1"
    ).fetchone()

    print("USD:", price["usd_ils"])
    print("USDT:", price["usdt_ils"])

    user = None

    if "user" in session:
        user = session["user"]

    con.close()

    return render_template(
        "index.html",
        ads=ads,
        cash_ads=cash_ads,
        price=price,
        user=user
    )


@app.route("/market")
def market():

    con = connect()

    ads = con.execute(
        "SELECT * FROM ads WHERE status='OPEN' ORDER BY id DESC"
    ).fetchall()

    cash_ads = con.execute(
        "SELECT * FROM cash_ads WHERE status='OPEN' ORDER BY id DESC"
    ).fetchall()

    price = con.execute(
        "SELECT * FROM market_price WHERE id=1"
    ).fetchone()

    print("PRICE TEST:", dict(price))

    con.close()

    return render_template(
        "market.html",
        ads=ads,
        cash_ads=cash_ads,
        price=price
    )


@app.route("/create_ad", methods=["GET", "POST"])
@login_required
def create_ad():
    if request.method == "POST":
        title = request.form.get("title")
        amount = float(request.form.get("amount", 0))
        price = float(request.form.get("price", 0))
        payment = request.form.get("payment")

        con = connect()
        con.execute(
            "INSERT INTO ads (user, title, amount, price, payment, status) VALUES(?, ?, ?, ?, ?, ?)",
            (session["user"], title, amount, price, payment, "OPEN")
        )
        con.commit()
        con.close()
        return redirect("/")

    return render_template("create_ad.html")


def get_trade_fee(price):
    con = connect()
    fee = con.execute("SELECT trade_fee FROM commission WHERE id=1").fetchone()
    con.close()
    if not fee:
        return 0
    return price * fee["trade_fee"] / 100


def add_profit(amount):
    con = connect()
    con.execute("UPDATE platform_profit SET total = total + ? WHERE id=1", (amount,))
    con.commit()
    con.close()


@app.route("/buy/<int:id>")
@login_required
def buy(id):
    con = connect()
    ad = con.execute("SELECT * FROM ads WHERE id=?", (id,)).fetchone()

    if not ad:
        con.close()
        return "الإعلان غير موجود"

    if ad["user"] == session["user"]:
        con.close()
        return "لا يمكنك شراء إعلانك"

    fee = get_trade_fee(ad["price"])

    trade = con.execute(
        "INSERT INTO trades (ad_id, buyer, seller, amount, price, fee, status) VALUES(?, ?, ?, ?, ?, ?, ?)",
        (id, session["user"], ad["user"], ad["amount"], ad["price"], fee, "PENDING")
    )
    trade_id = trade.lastrowid

    con.execute("UPDATE ads SET status='SOLD' WHERE id=?", (id,))
    con.commit()
    con.close()

    notify(ad["user"], "صفقة جديدة", "تم إنشاء طلب شراء")
    return redirect("/trade/" + str(trade_id))


# =========================
# 4. TRADES & CHAT SYSTEM
# =========================

@app.route("/trade/<int:id>", methods=["GET", "POST"])
@login_required
def trade(id):
    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade:
        con.close()
        return "الصفقة غير موجودة"

    if request.method == "POST":
        text = request.form.get("message")
        receiver = request.form.get("receiver")

        if text and receiver:
            con.execute(
                "INSERT INTO messages (sender, receiver, text) VALUES(?, ?, ?)",
                (session["user"], receiver, text)
            )
            con.commit()

    messages = con.execute(
        "SELECT * FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) ORDER BY id",
        (session["user"], trade["seller"], trade["seller"], session["user"])
    ).fetchall()

    con.close()
    return render_template("trade.html", trade=trade, messages=messages)


@app.route("/trade_status/<int:id>/<status>")
@login_required
def trade_status(id, status):
    allowed = ["PENDING", "PAYMENT_SENT", "COMPLETED", "CANCELLED", "DISPUTE"]
    if status not in allowed:
        return "حالة غير صحيحة"

    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()
    if not trade:
        con.close()
        return "غير موجود"

    con.execute("UPDATE trades SET status=? WHERE id=?", (status, id))
    con.commit()
    con.close()

    notify(trade["buyer"], "تحديث صفقة", status)
    notify(trade["seller"], "تحديث صفقة", status)

    return redirect("/trade/" + str(id))


@app.route("/finish_trade/<int:id>")
@login_required
def finish_trade(id):
    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade:
        con.close()
        return "غير موجود"

    con.execute("UPDATE trades SET status='COMPLETED' WHERE id=?", (id,))
    con.execute("UPDATE users SET trades_count = trades_count + 1 WHERE username=?", (trade["buyer"],))
    con.execute("UPDATE users SET trades_count = trades_count + 1 WHERE username=?", (trade["seller"],))
    con.commit()
    con.close()

    add_profit(trade["fee"])
    return redirect("/profile")


# =========================
# 5. CASH MARKET SYSTEM
# =========================

@app.route("/cash_market")
def cash_market():
    con = connect()
    ads = con.execute("SELECT * FROM cash_ads WHERE status='OPEN' ORDER BY id DESC").fetchall()
    con.close()
    return render_template("cash_ads.html", ads=ads)


@app.route("/cash_ads")
def cash_ads():
    return redirect("/cash_market")


@app.route("/create_cash_ad", methods=["GET", "POST"])
@login_required
def create_cash_ad():

    if request.method == "POST":

        amount = float(request.form.get("amount", 0))
        price = float(request.form.get("price", 0))
        city = request.form.get("city", "")
        location = request.form.get("location", "")
        notes = request.form.get("notes", "")

        plan = request.form.get("plan", "week")

        if plan == "week":
            fee = 2
            days = 7

        elif plan == "two_weeks":
            fee = 6
            days = 14

        elif plan == "month":
            fee = 15
            days = 30

        else:
            fee = 2
            days = 7

        wallet = "0x659dd7cba24363c903abe3fddfc89eb30ffbf58a"

        return render_template(
            "cash_payment.html",
            fee=fee,
            wallet=wallet,
            days=days,
            amount=amount,
            price=price,
            city=city,
            location=location,
            notes=notes,
            plan=plan
        )

    return render_template("create_cash_ad.html")


@app.route("/cash_ad/<int:id>")
def cash_ad(id):
    con = connect()
    ad = con.execute("SELECT * FROM cash_ads WHERE id=?", (id,)).fetchone()
    con.close()

    if not ad:
        return "الإعلان غير موجود"

    return render_template("cash_ad.html", ad=ad)


@app.route("/cash_buy/<int:id>")
@login_required
def cash_buy(id):
    con = connect()
    ad = con.execute("SELECT * FROM cash_ads WHERE id=?", (id,)).fetchone()

    if not ad:
        con.close()
        return "الإعلان غير موجود"

    if ad["user"] == session["user"]:
        con.close()
        return "لا تستطيع الطلب من إعلانك"

    trade = con.execute(
        "INSERT INTO cash_trades (ad_id, buyer, seller, amount, price, status) VALUES(?, ?, ?, ?, ?, ?)",
        (id, session["user"], ad["user"], ad["amount"], ad["price"], "WAITING_MEETING")
    )
    trade_id = trade.lastrowid

    con.execute("UPDATE cash_ads SET status='CLOSED' WHERE id=?", (id,))
    con.commit()
    con.close()

    notify(ad["user"], "طلب مقابلة شخصية", "يوجد شخص يريد التعامل معك")

    telegram_bot.send_admin(
        f"""
🤝 طلب مقابلة جديد 🤝
👤 المشتري: {session['user']}
👤 البائع: {ad['user']}
💰 الكمية: USDT {ad['amount']}
💵 السعر: {ad['price']}
📍 المدينة: {ad['city']}
📌 المكان: {ad['location']}
🆔 رقم الصفقة: {trade_id}
"""
    )

    return redirect("/cash_trade/" + str(trade_id))


@app.route("/cash_trade/<int:id>", methods=["GET", "POST"])
@login_required
def cash_trade(id):
    con = connect()
    trade = con.execute("SELECT * FROM cash_trades WHERE id=?", (id,)).fetchone()
    con.close()

    if not trade:
        return "المقابلة غير موجودة"

    return render_template("cash_trade.html", trade=trade)


@app.route("/confirm_meeting/<int:id>")
@login_required
def confirm_meeting(id):

    con = connect()

    trade = con.execute(
        "SELECT * FROM cash_trades WHERE id=?",
        (id,)
    ).fetchone()


    if not trade:
        con.close()
        return "الصفقة غير موجودة"


    con.execute(
        "UPDATE cash_trades SET status='MEETING_CONFIRMED' WHERE id=?",
        (id,)
    )


    notify(
        trade["buyer"],
        "تم تأكيد موعد اللقاء",
        "تم تأكيد المقابلة الشخصية مع البائع"
    )


    notify(
        trade["seller"],
        "تم تأكيد موعد اللقاء",
        "تم تأكيد المقابلة الشخصية مع المشتري"
    )


    con.commit()
    con.close()


    return redirect("/cash_trade/" + str(id))


@app.route("/complete_cash/<int:id>")
@login_required
def complete_cash(id):
    con = connect()
    trade = con.execute("SELECT * FROM cash_trades WHERE id=?", (id,)).fetchone()

    if trade:
        con.execute("UPDATE cash_trades SET status='COMPLETED' WHERE id=?", (id,))

        telegram_bot.send_admin(
            f"""
✅ تم إتمام صفقة مقابلة

🆔 رقم الصفقة: {id}

👤 المشتري: {trade['buyer']}

👤 البائع: {trade['seller']}

💰 الكمية: {trade['amount']} USDT

💵 السعر: {trade['price']}

🎉 الحالة: COMPLETED
"""
        )

    con.commit()
    con.close()
    return redirect("/profile")


@app.route("/cash_dispute/<int:id>")
@login_required
def cash_dispute(id):

    con = connect()

    trade = con.execute(
        "SELECT * FROM cash_trades WHERE id=?",
        (id,)
    ).fetchone()


    if not trade:
        con.close()
        return "الصفقة غير موجودة"


    con.execute(
        "UPDATE cash_trades SET status='DISPUTE' WHERE id=?",
        (id,)
    )


    notify(
        trade["buyer"],
        "فتح نزاع",
        "تم فتح نزاع على صفقة المقابلة الشخصية"
    )


    notify(
        trade["seller"],
        "فتح نزاع",
        "تم فتح نزاع على صفقة المقابلة الشخصية"
    )


    con.commit()
    con.close()


    return redirect("/cash_trade/" + str(id))


@app.route("/cash_payment_sent", methods=["POST"])
@login_required
def cash_payment_sent():

    amount = request.form.get("amount")
    price = request.form.get("price")
    city = request.form.get("city")
    location = request.form.get("location")
    notes = request.form.get("notes")
    plan = request.form.get("plan")

    fees = {
        "week": 2,
        "two_weeks": 6,
        "month": 15
    }

    fee = fees.get(plan, 2)

    con = connect()

    con.execute(
        """
        INSERT INTO cash_ads
        (user, amount, price, city, location, notes, fee, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session["user"],
            amount,
            price,
            city,
            location,
            notes,
            fee,
            "PENDING_PAYMENT"
        )
    )

    con.commit()
    con.close()

    telegram_bot.send_admin(
        f"""
🔔 إعلان مقابلة جديد 👤
المستخدم: {session['user']} 👤
الكمية: USDT {amount} 💰
السعر: {price} 💵
المدينة: {city} 📍
المكان: {location} 📌
العمولة: USDT {fee} 💳
الحالة: بانتظار مراجعة الأدمن ⏳
"""
    )

    return """
    <script>
    alert('تم إرسال طلب الإعلان للمراجعة ✅');
    window.location.href='/';
    </script>
    """


# =========================
# 6. PROFILE, DASHBOARD & REVIEWS
# =========================

@app.route("/profile")
@login_required
def profile():
    con = connect()
    user = con.execute("SELECT * FROM users WHERE username=?", (session["user"],)).fetchone()
    trades = con.execute("SELECT * FROM trades WHERE buyer=? OR seller=? ORDER BY id DESC", (session["user"], session["user"])).fetchall()
    cash_trades = con.execute("SELECT * FROM cash_trades WHERE buyer=? OR seller=? ORDER BY id DESC", (session["user"], session["user"])).fetchall()
    ads = con.execute("SELECT * FROM ads WHERE user=? ORDER BY id DESC", (session["user"],)).fetchall()
    con.close()

    return render_template("profile.html", user=user, trades=trades, cash_trades=cash_trades, ads=ads)


@app.route("/dashboard")
@login_required
def dashboard():
    con = connect()
    user = con.execute("SELECT * FROM users WHERE username=?", (session["user"],)).fetchone()
    completed = con.execute("SELECT COUNT(*) FROM trades WHERE (buyer=? OR seller=?) AND status='COMPLETED'", (session["user"], session["user"])).fetchone()[0]
    cash_completed = con.execute("SELECT COUNT(*) FROM cash_trades WHERE (buyer=? OR seller=?) AND status='COMPLETED'", (session["user"], session["user"])).fetchone()[0]
    con.close()

    return render_template("dashboard.html", user=user, completed=completed, cash_completed=cash_completed)


@app.route("/my_ads")
@login_required
def my_ads():

    con = connect()

    ads = con.execute(
        "SELECT * FROM ads WHERE user=? ORDER BY id DESC",
        (session["user"],)
    ).fetchall()

    con.close()

    return render_template(
        "my_ads.html",
        ads=ads
    )


@app.route("/notifications")
@login_required
def notifications():
    con = connect()
    data = con.execute("SELECT * FROM notifications WHERE username=? ORDER BY id DESC", (session["user"],)).fetchall()
    con.close()
    return render_template("notifications.html", notifications=data)


@app.route("/chat/<username>")
@login_required
def chat(username):
    con = connect()
    messages = con.execute(
        "SELECT * FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) ORDER BY id ASC",
        (session["user"], username, username, session["user"])
    ).fetchall()
    con.close()
    return render_template("chat.html", messages=messages, target=username)


@app.route("/send_message", methods=["POST"])
@login_required
def send_message():
    receiver = request.form.get("receiver")
    text = request.form.get("text")

    if not receiver or not text:
        return redirect("/")

    con = connect()
    con.execute("INSERT INTO messages (sender, receiver, text) VALUES(?, ?, ?)", (session["user"], receiver, text))
    con.commit()
    con.close()

    return redirect("/chat/" + receiver)


@app.route("/review/<int:id>", methods=["POST"])
@login_required
def review(id):
    rating = int(request.form.get("rating", 5))
    comment = request.form.get("comment", "")

    con = connect()
    trade = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    if not trade:
        con.close()
        return "الصفقة غير موجودة"

    target = trade["seller"] if session["user"] == trade["buyer"] else trade["buyer"]

    con.execute(
        "INSERT INTO reviews (trade_id, from_user, to_user, rating, comment) VALUES(?, ?, ?, ?, ?)",
        (id, session["user"], target, rating, comment)
    )

    avg = con.execute("SELECT AVG(rating) FROM reviews WHERE to_user=?", (target,)).fetchone()[0]
    if avg:
        con.execute("UPDATE users SET rating=? WHERE username=?", (round(avg, 2), target))

    con.commit()
    con.close()
    return redirect("/profile")


@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    con = connect()

    user = con.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    if request.method == "POST":
        phone = request.form.get("phone", "")
        bank = request.form.get("bank", "")
        wallet = request.form.get("wallet", "")

        con.execute(
            """
            UPDATE users 
            SET phone=?, bank=?, wallet=?
            WHERE username=?
            """,
            (
                phone,
                bank,
                wallet,
                session["user"]
            )
        )

        con.commit()
        con.close()

        return redirect("/profile")

    con.close()

    return render_template(
        "edit_profile.html",
        user=user
    )


# =========================
# 7. ALL ADS ROUTE
# =========================

@app.route("/all_ads")
def all_ads():

    con = connect()

    online = con.execute(
        "SELECT *, 'online' as type FROM ads ORDER BY id DESC"
    ).fetchall()


    cash = con.execute(
        "SELECT *, 'cash' as type FROM cash_ads ORDER BY id DESC"
    ).fetchall()


    ads = list(online) + list(cash)


    con.close()


    return render_template(
        "all_ads.html",
        ads=ads
    )


# =========================
# 8. ADMIN PANEL & BACKUP
# =========================

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        con = connect()
        user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        con.close()

        if user and user["status"] == "ADMIN" and check_password_hash(user["password"], password):
            session["user"] = username
            return redirect("/admin")

        return "بيانات الأدمن غير صحيحة"

    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin():
    con = connect()
    users = con.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    trades = con.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    cash_trades = con.execute("SELECT * FROM cash_trades ORDER BY id DESC").fetchall()
    profit = con.execute("SELECT * FROM platform_profit WHERE id=1").fetchone()
    commission = con.execute("SELECT * FROM commission WHERE id=1").fetchone()
    con.close()

    return render_template("admin.html", users=users, trades=trades, cash_trades=cash_trades, profit=profit, commission=commission)


@app.route("/admin_cash_ads")
@admin_required
def admin_cash_ads():

    con = connect()

    ads = con.execute(
        "SELECT * FROM cash_ads ORDER BY id DESC"
    ).fetchall()

    con.close()

    return render_template(
        "admin_cash_ads.html",
        ads=ads
    )


@app.route("/admin_commission", methods=["POST"])
@admin_required
def admin_commission():
    trade_fee = float(request.form.get("trade_fee", 1))
    cash_fee = float(request.form.get("cash_fee", 2))

    con = connect()
    con.execute("UPDATE commission SET trade_fee=?, cash_fee=? WHERE id=1", (trade_fee, cash_fee))
    con.commit()
    con.close()

    return redirect("/admin")


@app.route("/admin_commission_page")
@admin_required
def admin_commission_page():

    con = connect()

    commission = con.execute(
        "SELECT * FROM commission WHERE id=1"
    ).fetchone()

    con.close()

    return render_template(
        "admin_commission.html",
        commission=commission
    )


@app.route("/admin_verify/<username>")
@admin_required
def admin_verify(username):
    con = connect()
    con.execute("UPDATE users SET verified=1 WHERE username=?", (username,))
    con.commit()
    con.close()
    return redirect("/admin")


@app.route("/admin_ban/<username>")
@admin_required
def admin_ban(username):
    con = connect()
    con.execute("UPDATE users SET status='BANNED' WHERE username=?", (username,))
    con.commit()
    con.close()
    return redirect("/admin")


@app.route("/admin_unban/<username>")
@admin_required
def admin_unban(username):
    con = connect()
    con.execute("UPDATE users SET status='ACTIVE' WHERE username=?", (username,))
    con.commit()
    con.close()
    return redirect("/admin")


@app.route("/admin_search")
@admin_required
def admin_search():
    q = request.args.get("q", "")
    con = connect()
    results = con.execute(
        "SELECT * FROM trades WHERE buyer LIKE ? OR seller LIKE ? OR status LIKE ? ORDER BY id DESC",
        ("%" + q + "%", "%" + q + "%", "%" + q + "%")
    ).fetchall()
    con.close()
    return render_template("admin_search.html", trades=results)


@app.route("/admin_stats")
@admin_required
def admin_stats():
    con = connect()
    users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    trades = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    completed = con.execute("SELECT COUNT(*) FROM trades WHERE status='COMPLETED'").fetchone()[0]
    profit = con.execute("SELECT total FROM platform_profit WHERE id=1").fetchone()[0]
    con.close()

    return jsonify({"users": users, "trades": trades, "completed": completed, "profit": profit})


@app.route("/admin_backup")
@admin_required
def admin_backup():
    shutil.copy("database.db", "database_backup.db")
    return "تم إنشاء نسخة احتياطية"


@app.route("/admin_cash_accept/<int:id>")
@admin_required
def admin_cash_accept(id):

    con = connect()

    con.execute(
        "UPDATE cash_ads SET status='OPEN' WHERE id=?",
        (id,)
    )

    con.commit()
    con.close()

    return redirect("/admin_cash_ads")


@app.route("/admin_cash_reject/<int:id>")
@admin_required
def admin_cash_reject(id):

    con = connect()

    con.execute(
        "UPDATE cash_ads SET status='REJECTED' WHERE id=?",
        (id,)
    )

    con.commit()
    con.close()

    return redirect("/admin_cash_ads")


# تشغيل بوت التليجرام تلقائياً مع خيوط المعالجة (Threading)
try:
    threading.Thread(
        target=telegram_bot.bot_loop,
        daemon=True
    ).start()
except Exception:
    traceback.print_exc()


# تحديث سعر الدولار و USDT تلقائياً

def auto_price_update():

    while True:

        try:
            price_updater.update_price()

        except Exception as e:
            print("AUTO PRICE ERROR:", e)


        # تحديث كل ساعة
        import time
        time.sleep(3600)



try:

    threading.Thread(
        target=auto_price_update,
        daemon=True
    ).start()

    print("PRICE UPDATER STARTED")

except Exception:

    traceback.print_exc()


if __name__ == "__main__":
    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False
        )
    except Exception:
        traceback.print_exc()
