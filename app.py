from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

app.secret_key = "USDT_SECRET_KEY"

ADMIN_USER = "admin"
ADMIN_PASS = "SA526614@mer"

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
        proof TEXT
    )
    """)

    con.commit()
    con.close()


setup()


@app.route("/")
def home():
    con = connect()
    ads = con.execute("SELECT * FROM ads WHERE status='OPEN'").fetchall()
    con.close()

    return render_template("index.html", ads=ads, user=session.get("user"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        phone = request.form["phone"]
        bank = request.form["bank"]
        wallet = request.form["wallet"]

        con = connect()

        try:
            con.execute(
                """
            INSERT INTO users
            (username,password,phone,bank,wallet)
            VALUES(?,?,?,?,?)
            """,
                (username, password, phone, bank, wallet),
            )

            con.commit()
            con.close()

            session["user"] = username
            return redirect("/")

        except:
            con.close()
            return "اسم المستخدم موجود"

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        con = connect()

        user = con.execute(
            """
        SELECT * FROM users
        WHERE username=? AND password=?
        """,
            (username, password),
        ).fetchone()

        con.close()

        if user:
            session["user"] = username
            return redirect("/")

        return "بيانات الدخول خطأ"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")


@app.route("/create_ad", methods=["GET", "POST"])
def create_ad():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        amount = request.form["amount"]
        price = request.form["price"]
        payment = request.form["payment"]

        con = connect()

        con.execute(
            """
        INSERT INTO ads
        (user,amount,price,payment,status)
        VALUES(?,?,?,?,?)
        """,
            (session["user"], float(amount), float(price), payment, "OPEN"),
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

    ad = con.execute("SELECT * FROM ads WHERE id=?", (id,)).fetchone()

    if not ad:
        con.close()
        return redirect("/")

    cur = con.execute(
        """
    INSERT INTO trades
    (buyer,seller,amount,price,status,proof)
    VALUES(?,?,?,?,?,?)
    """,
        (
            session["user"],
            ad["user"],
            ad["amount"],
            ad["price"],
            "WAITING_PAYMENT",
            "",
        ),
    )

    trade_id = cur.lastrowid

    con.execute("UPDATE ads SET status='CLOSED' WHERE id=?", (id,))

    con.commit()
    con.close()

    return redirect("/trade/" + str(trade_id))


@app.route("/trade/<int:id>")
def trade(id):
    con = connect()

    trade_item = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()

    con.close()

    return render_template("trade.html", trade=trade_item)


@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect("/login")

    con = connect()

    user = con.execute(
        "SELECT * FROM users WHERE username=?", (session["user"],)
    ).fetchone()

    con.close()

    return render_template("profile.html", user=user)


@app.route("/upload_payment/<int:id>", methods=["POST"])
def upload_payment(id):
    file = request.files["proof"]

    filename = secure_filename(file.filename)

    file.save(os.path.join(UPLOAD_FOLDER, filename))

    con = connect()

    con.execute(
        """
    UPDATE trades
    SET proof=?,status='PAYMENT_SENT'
    WHERE id=?
    """,
        (filename, id),
    )

    con.commit()
    con.close()

    return redirect("/trade/" + str(id))


@app.route("/confirm/<int:id>")
def confirm(id):
    con = connect()

    con.execute(
        """
        UPDATE trades
        SET status='COMPLETED'
        WHERE id=?
        """,
        (id,),
    )

    con.commit()
    con.close()

    return redirect("/trade/" + str(id))


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == ADMIN_USER and password == ADMIN_PASS:
            session["admin"] = True
            return redirect("/admin")
        else:
            return "بيانات الأدمن خطأ"

    return render_template("admin_login.html")


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin_login")

    con = connect()

    trades = con.execute("SELECT * FROM trades").fetchall()

    con.close()

    return render_template("admin.html", trades=trades)


@app.route("/admin_logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin_login")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
