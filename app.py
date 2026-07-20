from functools import wraps
import os
import shutil
import sqlite3
from flask import Flask, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "APEX_USDT_SECRET_KEY_CHANGE"

# =========================
# DATABASE CONNECTION
# =========================


def connect():
  con = sqlite3.connect("database.db")
  con.row_factory = sqlite3.Row
  return con


# =========================
# DATABASE SETUP
# =========================


def setup():
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

  # ADS
  con.execute("""
    CREATE TABLE IF NOT EXISTS ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        title TEXT,
        amount REAL DEFAULT 0,
        price REAL,
        payment TEXT DEFAULT '',
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
        amount REAL DEFAULT 0,
        price REAL,
        fee REAL DEFAULT 0,
        status TEXT DEFAULT 'PENDING',
        dispute TEXT DEFAULT 'NONE',
        created DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated DATETIME DEFAULT CURRENT_TIMESTAMP
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

  # PLATFORM PROFIT
  con.execute("""
    CREATE TABLE IF NOT EXISTS platform_profit(
        id INTEGER PRIMARY KEY,
        total REAL DEFAULT 0
    )
    """)

  # TRANSACTIONS
  con.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id INTEGER,
        username TEXT,
        type TEXT,
        amount REAL,
        description TEXT,
        created DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

  # NOTIFICATIONS
  con.execute("""
    CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        title TEXT,
        description TEXT,
        link TEXT,
        seen INTEGER DEFAULT 0,
        created DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

  # CHAT
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
        fee REAL,
        status TEXT DEFAULT 'OPEN'
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
        status TEXT DEFAULT 'PENDING'
    )
    """)

  # DEFAULT COMMISSION
  fee = con.execute("SELECT * FROM commission WHERE id=1").fetchone()
  if not fee:
    con.execute(
        "INSERT INTO commission (id,trade_fee,cash_fee) VALUES(1,1,2)"
    )

  profit = con.execute("SELECT * FROM platform_profit WHERE id=1").fetchone()
  if not profit:
    con.execute("INSERT INTO platform_profit (id,total) VALUES(1,0)")

  con.commit()
  con.close()


setup()


# =========================
# AUTH SYSTEM & DECORATORS
# =========================


def login_required(f):
  @wraps(f)
  def wrapper(*args, **kwargs):
    if "user" not in session:
      return redirect("/login")
    return f(*args, **kwargs)

  return wrapper


def admin_required(f):
  @wraps(f)
  def wrapper(*args, **kwargs):
    if "user" not in session:
      return redirect("/login")

    con = connect()
    user = con.execute(
        "SELECT * FROM users WHERE username=?", (session["user"],)
    ).fetchone()
    con.close()

    if not user or user["status"] != "ADMIN":
      return "غير مصرح", 403

    return f(*args, **kwargs)

  return wrapper


# =========================
# REGISTER & LOGIN ROUTES
# =========================


@app.route("/register", methods=["GET", "POST"])
def register():
  if request.method == "POST":
    username = request.form.get("username", "").strip()
    raw_password = request.form.get("password", "")

    if not username or not raw_password:
      return "الرجاء إدخال اسم المستخدم وكلمة المرور"

    password = generate_password_hash(raw_password)
    con = connect()
    try:
      con.execute(
          "INSERT INTO users (username,password) VALUES(?,?)",
          (username, password),
      )
      con.commit()
      con.close()
      session["user"] = username
      return redirect("/dashboard")
    except sqlite3.IntegrityError:
      con.close()
      return "اسم المستخدم موجود مسبقاً"
    except Exception as e:
      con.close()
      return f"حدث خطأ ما: {e}"

  return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
  if request.method == "POST":
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    con = connect()
    user = con.execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()
    con.close()

    if user and check_password_hash(user["password"], password):
      if user["status"] == "BANNED":
        return "هذا الحساب محظور"
      session["user"] = username
      return redirect("/dashboard")
    return "بيانات الدخول خاطئة"
  return render_template("login.html")


@app.route("/logout")
def logout():
  session.clear()
  return redirect("/")


@app.route("/logout_all")
def logout_all():
  session.clear()
  return redirect("/")


# =========================
# NOTIFICATIONS SYSTEM
# =========================


def notify(username, title, description, link="/profile"):
  con = connect()
  con.execute(
      "INSERT INTO notifications (username,title,description,link) VALUES(?,?,?,?)",
      (username, title, description, link),
  )
  con.commit()
  con.close()


@app.route("/notifications")
@login_required
def notifications():
  con = connect()
  data = con.execute(
      "SELECT * FROM notifications WHERE username=? ORDER BY id DESC",
      (session["user"],),
  ).fetchall()
  con.close()
  return render_template("notifications.html", notifications=data)


# =========================
# ADS & HOME
# =========================


@app.route("/")
def home():
  con = connect()
  ads = con.execute(
      "SELECT * FROM ads WHERE status='OPEN' ORDER BY id DESC"
  ).fetchall()
  con.close()
  return render_template("index.html", ads=ads)


@app.route("/create_ad", methods=["GET", "POST"])
@login_required
def create_ad():
  if request.method == "POST":
    title = request.form.get("title", "")
    try:
      amount = float(request.form.get("amount", 0))
      price = float(request.form.get("price", 0))
    except ValueError:
      return "الرجاء إدخال أرقام صحيحة للمبلغ والسعر"

    payment = request.form.get("payment", "")

    con = connect()
    con.execute(
        "INSERT INTO ads (user,title,amount,price,payment,status) VALUES(?,?,?,?,?,?)",
        (session["user"], title, amount, price, payment, "OPEN"),
    )
    con.commit()
    con.close()
    return redirect("/")
  return render_template("create_ad.html")


# =========================
# TRADING SYSTEM
# =========================


def get_trade_fee(price):
  con = connect()
  setting = con.execute("SELECT trade_fee FROM commission WHERE id=1").fetchone()
  con.close()
  if not setting:
    return 0
  return price * setting["trade_fee"] / 100


def add_platform_profit(amount, trade_id):
  con = connect()
  con.execute("UPDATE platform_profit SET total = total + ? WHERE id=1", (amount,))
  con.execute(
      "INSERT INTO transactions (trade_id,username,type,amount,description) VALUES(?,?,?,?,?)",
      (trade_id, "PLATFORM", "FEE", amount, "عمولة صفقة"),
  )
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
    return "لا يمكنك الشراء من إعلانك الخاص"

  fee = get_trade_fee(ad["price"])
  cur = con.execute(
      "INSERT INTO trades (ad_id,buyer,seller,amount,price,fee,status) VALUES(?,?,?,?,?,?,?)",
      (id, session["user"], ad["user"], ad["amount"], ad["price"], fee, "PENDING_PAYMENT"),
  )
  trade_id = cur.lastrowid

  con.execute("UPDATE ads SET status='CLOSED' WHERE id=?", (id,))
  con.commit()
  con.close()

  notify(ad["user"], "طلب شراء جديد", "تم فتح صفقة جديدة", "/trade/" + str(trade_id))
  return redirect("/trade/" + str(trade_id))


@app.route("/trade/<int:id>", methods=["GET", "POST"])
@login_required
def trade(id):
  con = connect()
  if request.method == "POST":
    message = request.form.get("message")
    receiver = request.form.get("receiver")
    if message and receiver:
      con.execute(
          "INSERT INTO messages (sender,receiver,text) VALUES(?,?,?)",
          (session["user"], receiver, message),
      )
      con.commit()

  trade_item = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()
  con.close()
  return render_template("trade.html", trade=trade_item)


@app.route("/update_trade/<int:id>/<status>")
@login_required
def update_trade(id, status):
  allowed = ["PENDING_PAYMENT", "PAYMENT_SENT", "COMPLETED", "CANCELLED", "DISPUTE"]
  if status not in allowed:
    return "حالة غير صحيحة"

  con = connect()
  trade_item = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()
  if not trade_item:
    con.close()
    return "الصفقة غير موجودة"

  con.execute(
      "UPDATE trades SET status=?, updated=CURRENT_TIMESTAMP WHERE id=?",
      (status, id),
  )
  con.commit()
  con.close()

  notify(trade_item["buyer"], "تحديث الصفقة", "تم تغيير حالة الصفقة إلى " + status)
  notify(trade_item["seller"], "تحديث الصفقة", "تم تغيير حالة الصفقة إلى " + status)
  return redirect("/trade/" + str(id))


@app.route("/finish_trade/<int:id>")
@login_required
def finish_trade(id):
  con = connect()
  trade_item = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()
  if not trade_item:
    con.close()
    return "لا توجد صفقة"

  con.execute(
      "UPDATE trades SET status='COMPLETED', updated=CURRENT_TIMESTAMP WHERE id=?",
      (id,),
  )
  con.execute(
      "UPDATE users SET trades_count=trades_count+1 WHERE username=?",
      (trade_item["buyer"],),
  )
  con.execute(
      "UPDATE users SET trades_count=trades_count+1 WHERE username=?",
      (trade_item["seller"],),
  )
  con.commit()
  con.close()

  add_platform_profit(trade_item["fee"], id)
  notify(trade_item["buyer"], "اكتملت الصفقة", "تم إغلاق الصفقة بنجاح")
  notify(trade_item["seller"], "اكتملت الصفقة", "تم إغلاق الصفقة بنجاح")
  return redirect("/profile")


# =========================
# PROFILE & DASHBOARD
# =========================


@app.route("/profile")
@login_required
def profile():
  con = connect()
  user = con.execute(
      "SELECT * FROM users WHERE username=?", (session["user"],)
  ).fetchone()
  trades = con.execute(
      "SELECT * FROM trades WHERE buyer=? OR seller=? ORDER BY id DESC",
      (session["user"], session["user"]),
  ).fetchall()
  ads = con.execute(
      "SELECT * FROM ads WHERE user=? ORDER BY id DESC", (session["user"],)
  ).fetchall()
  con.close()
  return render_template("profile.html", user=user, trades=trades, ads=ads)


@app.route("/dashboard")
@login_required
def dashboard():
  con = connect()
  user = con.execute(
      "SELECT * FROM users WHERE username=?", (session["user"],)
  ).fetchone()
  completed = con.execute(
      "SELECT COUNT(*) FROM trades WHERE (buyer=? OR seller=?) AND status='COMPLETED'",
      (session["user"], session["user"]),
  ).fetchone()[0]
  con.close()
  return render_template("dashboard.html", user=user, completed=completed)


# =========================
# CHAT SYSTEM
# =========================


@app.route("/chat/<username>")
@login_required
def chat(username):
  con = connect()
  messages = con.execute(
      "SELECT * FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) ORDER BY id ASC",
      (session["user"], username, username, session["user"]),
  ).fetchall()
  con.close()
  return render_template("chat.html", messages=messages, target=username)


@app.route("/send_message", methods=["POST"])
@login_required
def send_message():
  receiver = request.form.get("receiver")
  text = request.form.get("text")
  if not receiver or not text:
    return redirect(request.referrer or "/")

  con = connect()
  con.execute(
      "INSERT INTO messages (sender,receiver,text) VALUES(?,?,?)",
      (session["user"], receiver, text),
  )
  con.commit()
  con.close()
  return redirect("/chat/" + receiver)


# =========================
# REVIEWS SYSTEM
# =========================


@app.route("/review/<int:trade_id>", methods=["POST"])
@login_required
def review(trade_id):
  try:
    rating = int(request.form.get("rating", 5))
  except ValueError:
    rating = 5

  comment = request.form.get("comment", "")
  con = connect()

  trade_item = con.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
  if not trade_item:
    con.close()
    return "صفقة غير موجودة"

  target = (
      trade_item["seller"]
      if session["user"] == trade_item["buyer"]
      else trade_item["buyer"]
  )

  con.execute(
      "INSERT INTO reviews (trade_id,from_user,to_user,rating,comment) VALUES(?,?,?,?,?)",
      (trade_id, session["user"], target, rating, comment),
  )

  avg = con.execute(
      "SELECT AVG(rating) FROM reviews WHERE to_user=?", (target,)
  ).fetchone()[0]
  if avg:
    con.execute(
        "UPDATE users SET rating=? WHERE username=?", (round(avg, 2), target)
    )

  con.commit()
  con.close()
  return redirect("/profile")


# =========================
# CASH MARKET SYSTEM
# =========================


@app.route("/cash_market")
def cash_market():
  con = connect()

  ads = con.execute(
      """
        SELECT *
        FROM cash_ads
        WHERE status='OPEN'
        ORDER BY id DESC
        """
  ).fetchall()

  con.close()

  return render_template("cash_ads.html", ads=ads)


@app.route("/create_cash_ad", methods=["GET", "POST"])
@login_required
def create_cash_ad():
  if request.method == "POST":
    try:
      amount = float(request.form.get("amount", 0))
      price = float(request.form.get("price", 0))
    except ValueError:
      return "الرجاء إدخال بيانات صحيحة"

    city = request.form.get("city", "")
    location = request.form.get("location", "")
    notes = request.form.get("notes", "")

    con = connect()
    fee = con.execute("SELECT cash_fee FROM commission WHERE id=1").fetchone()[
        "cash_fee"
    ]
    con.execute(
        "INSERT INTO cash_ads (user,amount,price,city,location,notes,fee) VALUES(?,?,?,?,?,?,?)",
        (session["user"], amount, price, city, location, notes, fee),
    )
    con.commit()
    con.close()
    return redirect("/cash_market")
  return render_template("create_cash_ad.html")


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
    return "لا يمكنك الشراء من إعلانك الخاص"

  con.execute(
      "INSERT INTO cash_trades (ad_id,buyer,seller,amount,price) VALUES(?,?,?,?,?)",
      (id, session["user"], ad["user"], ad["amount"], ad["price"]),
  )
  con.execute("UPDATE cash_ads SET status='CLOSED' WHERE id=?", (id,))
  con.commit()
  con.close()
  return redirect("/profile")


# =========================
# CASH MEETING PAGE
# =========================


@app.route("/cash_trade/<int:id>")
@login_required
def cash_trade_page(id):
  con = connect()

  trade = con.execute(
      """
      SELECT *
      FROM cash_trades
      WHERE id=?
      """,
      (id,),
  ).fetchone()

  if not trade:
    con.close()
    return "المقابلة غير موجودة"

  ad = con.execute(
      """
      SELECT *
      FROM cash_ads
      WHERE id=?
      """,
      (trade["ad_id"],),
  ).fetchone()

  con.close()

  return render_template("cash_trade.html", trade=trade, ad=ad)


# =========================
# ADMIN PANEL SYSTEM
# =========================


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
  if request.method == "POST":
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    con = connect()
    user = con.execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()
    con.close()

    if (
        user
        and check_password_hash(user["password"], password)
        and user["status"] == "ADMIN"
    ):
      session["user"] = username
      return redirect("/admin")
    return "بيانات الأدمن خطأ"
  return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin():
  con = connect()
  users = con.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
  trades = con.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
  profit = con.execute("SELECT total FROM platform_profit WHERE id=1").fetchone()
  commission = con.execute("SELECT * FROM commission WHERE id=1").fetchone()
  con.close()
  return render_template(
      "admin.html",
      users=users,
      trades=trades,
      profit=profit,
      commission=commission,
  )


@app.route("/admin_commission", methods=["POST"])
@admin_required
def admin_commission():
  try:
    trade_fee = float(request.form.get("trade_fee", 1))
    cash_fee = float(request.form.get("cash_fee", 2))
  except ValueError:
    return "قيم غير صالحة"

  con = connect()
  con.execute(
      "UPDATE commission SET trade_fee=?, cash_fee=? WHERE id=1",
      (trade_fee, cash_fee),
  )
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


@app.route("/admin_verify/<username>")
@admin_required
def admin_verify(username):
  con = connect()
  con.execute("UPDATE users SET verified=1 WHERE username=?", (username,))
  con.commit()
  con.close()
  return redirect("/admin")


@app.route("/admin_search")
@admin_required
def admin_search():
  q = request.args.get("q", "")
  con = connect()
  trades = con.execute(
      "SELECT * FROM trades WHERE buyer LIKE ? OR seller LIKE ? OR status LIKE ? ORDER BY id DESC",
      ("%" + q + "%", "%" + q + "%", "%" + q + "%"),
  ).fetchall()
  con.close()
  return render_template("admin_search.html", trades=trades)


@app.route("/stats")
@admin_required
def stats():
  con = connect()
  users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
  trades = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
  completed = con.execute(
      "SELECT COUNT(*) FROM trades WHERE status='COMPLETED'"
  ).fetchone()[0]
  profit_row = con.execute("SELECT total FROM platform_profit WHERE id=1").fetchone()
  profit = profit_row[0] if profit_row else 0
  con.close()
  return jsonify(
      {"users": users, "trades": trades, "completed": completed, "profit": profit}
  )


@app.route("/admin_backup")
@admin_required
def admin_backup():
  shutil.copy("database.db", "database_backup.db")
  return "تم أخذ نسخة احتياطية بنجاح"


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=False)
