from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps


app = Flask(__name__)

app.secret_key = "USDT_SECRET_KEY"


ADMIN_USER = "admin"
ADMIN_PASS = "SA526614@mer"


# عمولة افتراضية في حال لم يتم تعديلها من قاعدة البيانات
DEFAULT_CASH_AD_FEE = 2


UPLOAD_FOLDER = "uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)



def connect():

    con = sqlite3.connect("database.db")

    con.row_factory = sqlite3.Row

    return con




def setup():

    con = connect()


    con.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        phone TEXT,
        bank TEXT,
        wallet TEXT
    )
    """)



    con.execute("""
    CREATE TABLE IF NOT EXISTS ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        amount REAL,
        price REAL,
        payment TEXT,
        status TEXT
    )
    """)



    con.execute("""
    CREATE TABLE IF NOT EXISTS trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        buyer TEXT,
        seller TEXT,
        amount REAL,
        price REAL,
        status TEXT,
        proof TEXT,
        escrow_status TEXT,
        seller_wallet TEXT,
        buyer_wallet TEXT,
        platform_wallet TEXT,
        dispute TEXT
    )
    """)



    con.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        id INTEGER PRIMARY KEY,
        wallet TEXT,
        network TEXT
    )
    """)



    con.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id INTEGER,
        sender TEXT,
        message TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)



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
        status TEXT
    )
    """)



    con.execute("""
    CREATE TABLE IF NOT EXISTS cash_trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad_id INTEGER,
        buyer TEXT,
        seller TEXT,
        amount REAL,
        price REAL,
        status TEXT
    )
    """)



    # جدول التحكم بالعمولة الديناميكية
    con.execute("""
    CREATE TABLE IF NOT EXISTS commission(
        id INTEGER PRIMARY KEY,
        cash_fee REAL
    )
    """)



    check = con.execute(
        "SELECT * FROM commission WHERE id=1"
    ).fetchone()



    if not check:

        con.execute(
        """
        INSERT INTO commission
        (id, cash_fee)
        VALUES(1, ?)
        """,
        (DEFAULT_CASH_AD_FEE,)
        )



    con.commit()

    con.close()



setup()




def admin_required(f):

    @wraps(f)

    def check(*args, **kwargs):

        if not session.get("admin"):

            return redirect("/admin_login")

        return f(*args, **kwargs)

    return check




@app.route("/")
def home():

    con = connect()

    ads = con.execute(
        """
        SELECT * FROM ads
        WHERE status='OPEN'
        """
    ).fetchall()

    con.close()


    return render_template(
        "index.html",
        ads=ads,
        user=session.get("user")
    )




@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        raw_password = request.form["password"]
        phone = request.form["phone"]
        bank = request.form["bank"]
        wallet = request.form["wallet"]

        # تشفير كلمة المرور أمنياً
        password = generate_password_hash(raw_password)

        con = connect()

        try:
            con.execute(
            """
            INSERT INTO users
            (username, password, phone, bank, wallet)
            VALUES(?,?,?,?,?)
            """,
            (username, password, phone, bank, wallet)
            )

            con.commit()
            con.close()

            session["user"] = username
            return redirect("/")

        except:
            con.close()
            return "اسم المستخدم موجود مسبقاً"

    return render_template("register.html")




@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        raw_password = request.form["password"]

        con = connect()

        user = con.execute(
        """
        SELECT * FROM users
        WHERE username=?
        """,
        (username,)
        ).fetchone()

        con.close()

        if user and check_password_hash(user["password"], raw_password):
            session["user"] = username
            return redirect("/")

        return "بيانات الدخول خطأ"

    return render_template("login.html")




@app.route("/logout")
def logout():

    session.pop("user", None)

    return redirect("/")




@app.route("/create_ad", methods=["GET","POST"])
def create_ad():

    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":

        try:
            amount = float(request.form["amount"])
            price = float(request.form["price"])
        except ValueError:
            return "الرجاء إدخال أرقام صحيحة"

        if amount <= 0 or price <= 0:
            return "الكمية والسعر يجب أن يكونا أكبر من صفر"

        payment = request.form["payment"]

        con = connect()

        con.execute(
        """
        INSERT INTO ads
        (user, amount, price, payment, status)
        VALUES(?,?,?,?,?)
        """,
        (session["user"], amount, price, payment, "OPEN")
        )

        con.commit()
        con.close()

        return redirect("/")

    return render_template("create_ad.html")




@app.route("/buy/<int:id>")
def buy(id):

    if "user" not in session:
        return redirect("/login")

    con = connect()

    ad = con.execute(
        "SELECT * FROM ads WHERE id=?",
        (id,)
    ).fetchone()

    if not ad:
        con.close()
        return redirect("/")

    setting = con.execute(
        "SELECT * FROM settings WHERE id=1"
    ).fetchone()

    platform_wallet = ""
    if setting:
        platform_wallet = setting["wallet"]

    cur = con.execute(
    """
    INSERT INTO trades
    (
    buyer, seller, amount, price, status,
    proof, escrow_status, seller_wallet,
    buyer_wallet, platform_wallet, dispute
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """,
    (
        session["user"],
        ad["user"],
        ad["amount"],
        ad["price"],
        "WAITING_ESCROW",
        "",
        "WAITING_DEPOSIT",
        "",
        "",
        platform_wallet,
        "NONE"
    )
    )

    trade_id = cur.lastrowid

    con.execute(
        "UPDATE ads SET status='CLOSED' WHERE id=?",
        (id,)
    )

    con.commit()
    con.close()

    return redirect("/trade/" + str(trade_id))





@app.route("/trade/<int:id>", methods=["GET","POST"])
def trade(id):

    if "user" not in session:
        return redirect("/login")

    con = connect()

    if request.method == "POST":

        msg = request.form.get("message")

        if msg and msg.strip():
            con.execute(
            """
            INSERT INTO messages
            (trade_id, sender, message)
            VALUES(?,?,?)
            """,
            (id, session["user"], msg.strip())
            )
            con.commit()

    trade_item = con.execute(
        "SELECT * FROM trades WHERE id=?",
        (id,)
    ).fetchone()

    messages = con.execute(
        """
        SELECT * FROM messages
        WHERE trade_id=?
        ORDER BY id ASC
        """,
        (id,)
    ).fetchall()

    con.close()

    return render_template(
        "trade.html",
        trade=trade_item,
        messages=messages
    )






@app.route("/upload_payment/<int:id>", methods=["POST"])
def upload_payment(id):

    if "user" not in session:
        return redirect("/login")

    if "proof" not in request.files:
        return redirect("/trade/" + str(id))

    file = request.files["proof"]

    if file.filename == "":
        return redirect("/trade/" + str(id))

    filename = secure_filename(file.filename)
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    con = connect()

    con.execute(
    """
    UPDATE trades
    SET proof=?, status='PAYMENT_SENT'
    WHERE id=?
    """,
    (filename, id)
    )

    con.commit()
    con.close()

    return redirect("/trade/" + str(id))




@app.route("/complete_trade/<int:id>")
def complete_trade(id):

    if "user" not in session:
        return redirect("/login")

    con = connect()

    con.execute(
    """
    UPDATE trades
    SET status='COMPLETED'
    WHERE id=?
    """,
    (id,)
    )

    con.commit()
    con.close()

    return redirect("/trade/" + str(id))






# =========================
# المقابلات الشخصية (Cash Trades)
# =========================


@app.route("/cash_market")
def cash_market():

    con = connect()

    ads = con.execute(
        """
        SELECT * FROM cash_ads
        WHERE status='OPEN'
        """
    ).fetchall()

    con.close()

    return render_template(
        "cash_market.html",
        ads=ads,
        user=session.get("user")
    )





@app.route("/create_cash_ad", methods=["GET","POST"])
def create_cash_ad():

    if "user" not in session:
        return redirect("/login")


    con = connect()


    commission = con.execute(
        "SELECT cash_fee FROM commission WHERE id=1"
    ).fetchone()


    fee = commission["cash_fee"] if commission else DEFAULT_CASH_AD_FEE



    if request.method == "POST":

        try:
            amount = float(request.form["amount"])
            price = float(request.form["price"])

        except ValueError:
            con.close()
            return "الرجاء إدخال أرقام صحيحة"



        city = request.form["city"]
        location = request.form["location"]
        notes = request.form["notes"]



        con.execute(
        """
        INSERT INTO cash_ads
        (user, amount, price, city, location, notes, fee, status)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            session["user"],
            amount,
            price,
            city,
            location,
            notes,
            fee,
            "OPEN"
        )
        )


        con.commit()
        con.close()


        return redirect("/cash_market")



    con.close()


    return render_template(
        "create_cash_ad.html",
        fee=fee
    )




@app.route("/cash_buy/<int:id>")
def cash_buy(id):

    if "user" not in session:
        return redirect("/login")

    con = connect()

    ad = con.execute(
        "SELECT * FROM cash_ads WHERE id=?",
        (id,)
    ).fetchone()

    if not ad:
        con.close()
        return redirect("/cash_market")

    con.execute(
    """
    INSERT INTO cash_trades
    (ad_id, buyer, seller, amount, price, status)
    VALUES(?,?,?,?,?,?)
    """,
    (id, session["user"], ad["user"], ad["amount"], ad["price"], "WAITING_CONFIRM")
    )

    con.execute(
        "UPDATE cash_ads SET status='CLOSED' WHERE id=?",
        (id,)
    )

    con.commit()
    con.close()

    return redirect("/profile")




@app.route("/complete_cash_trade/<int:id>")
def complete_cash_trade(id):

    if "user" not in session:
        return redirect("/login")

    con = connect()

    con.execute(
    """
    UPDATE cash_trades
    SET status='COMPLETED'
    WHERE id=?
    """,
    (id,)
    )

    con.commit()
    con.close()

    return redirect("/profile")






# =========================
# الملف الشخصي وتعديل البيانات
# =========================


@app.route("/profile")
def profile():

    if "user" not in session:
        return redirect("/login")

    con = connect()

    user = con.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    trades = con.execute(
        """
        SELECT * FROM trades
        WHERE buyer=? OR seller=?
        """,
        (session["user"], session["user"])
    ).fetchall()

    cash_trades = con.execute(
        """
        SELECT * FROM cash_trades
        WHERE buyer=? OR seller=?
        """,
        (session["user"], session["user"])
    ).fetchall()

    ads = con.execute(
        """
        SELECT * FROM ads
        WHERE user=?
        """,
        (session["user"],)
    ).fetchall()

    con.close()

    return render_template(
        "profile.html",
        user=user,
        trades=trades,
        cash_trades=cash_trades,
        ads=ads
    )




@app.route("/edit_profile", methods=["GET","POST"])
def edit_profile():

    if "user" not in session:
        return redirect("/login")

    con = connect()

    if request.method == "POST":
        phone = request.form["phone"]
        bank = request.form["bank"]
        wallet = request.form["wallet"]

        con.execute(
        """
        UPDATE users
        SET phone=?, bank=?, wallet=?
        WHERE username=?
        """,
        (phone, bank, wallet, session["user"])
        )
        con.commit()
        con.close()

        return redirect("/profile")

    user = con.execute(
        "SELECT * FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    con.close()

    return render_template(
        "edit_profile.html",
        user=user
    )






# =========================
# لوحة تحكم الأدمن
# =========================


@app.route("/admin_login", methods=["GET","POST"])
def admin_login():

    if request.method == "POST":

        if (
            request.form["username"] == ADMIN_USER
            and
            request.form["password"] == ADMIN_PASS
        ):
            session["admin"] = True
            return redirect("/admin")

        return "بيانات الأدمن خطأ"

    return render_template("admin_login.html")




@app.route("/admin")
@admin_required
def admin():

    con = connect()

    trades = con.execute(
        "SELECT * FROM trades"
    ).fetchall()

    cash_ads = con.execute(
        "SELECT * FROM cash_ads"
    ).fetchall()

    cash_trades = con.execute(
        "SELECT * FROM cash_trades"
    ).fetchall()

    commission = con.execute(
        "SELECT cash_fee FROM commission WHERE id=1"
    ).fetchone()

    con.close()

    current_fee = commission["cash_fee"] if commission else DEFAULT_CASH_AD_FEE

    return render_template(
        "admin.html",
        trades=trades,
        cash_ads=cash_ads,
        cash_trades=cash_trades,
        current_fee=current_fee
    )




@app.route("/update_commission", methods=["POST"])
@admin_required
def update_commission():

    try:
        new_fee = float(request.form["new_fee"])
    except ValueError:
        return "الرجاء إدخال رقم صحيح للعمولة"

    con = connect()
    con.execute(
        "UPDATE commission SET cash_fee=? WHERE id=1",
        (new_fee,)
    )
    con.commit()
    con.close()

    return redirect("/admin")




@app.route("/admin_wallet", methods=["GET","POST"])
@admin_required
def admin_wallet():

    con = connect()

    if request.method == "POST":
        wallet = request.form["wallet"]
        network = request.form["network"]

        con.execute(
        """
        INSERT OR REPLACE INTO settings
        (id, wallet, network)
        VALUES(1, ?, ?)
        """,
        (wallet, network)
        )
        con.commit()

    setting = con.execute(
        "SELECT * FROM settings WHERE id=1"
    ).fetchone()

    con.close()

    return render_template(
        "admin_wallet.html",
        setting=setting
    )




@app.route("/admin_logout")
def admin_logout():

    session.pop("admin", None)

    return redirect("/admin_login")




@app.route("/escrow_confirm/<int:id>")
def escrow_confirm(id):

    con = connect()

    con.execute(
    """
    UPDATE trades
    SET escrow_status='RECEIVED',
    status='WAITING_PAYMENT'
    WHERE id=?
    """,
    (id,)
    )

    con.commit()
    con.close()

    return redirect("/trade/" + str(id))




@app.route("/cancel_trade/<int:id>")
def cancel_trade(id):

    con = connect()

    con.execute(
    """
    UPDATE trades
    SET status='CANCELLED'
    WHERE id=?
    """,
    (id,)
    )

    con.commit()
    con.close()

    return redirect("/trade/" + str(id))




if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
