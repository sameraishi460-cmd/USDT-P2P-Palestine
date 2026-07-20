 """from flask import Flask, render_template, request, redirect, sessio
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "USDT_P2P_Palestine_SECRET"


def connect():
    db = sqlite3.connect("database.db")
    db.row_factory = sqlite3.Row
    return db


def setup():
    db = connect()

    db.execute(\"\"\"
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        email TEXT UNIQUE,
        password TEXT
    )
    \"\"\")

    db.execute(\"\"\"
    CREATE TABLE IF NOT EXISTS ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        type TEXT,
        amount REAL,
        price REAL,
        payment TEXT,
        status TEXT
    )
    \"\"\")

    db.execute(\"\"\"
    CREATE TABLE IF NOT EXISTS trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        buyer TEXT,
        seller TEXT,
        amount REAL,
        price REAL,
        fee REAL,
        status TEXT
    )
    \"\"\")

    db.commit()
    db.close()


@app.route("/")
def home():
    db = connect()
    ads = db.execute("SELECT * FROM ads WHERE status='OPEN'").fetchall()
    db.close()
    return render_template("index.html", ads=ads)


@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        db = connect()
        db.execute(
            "INSERT INTO users(username,email,password) VALUES(?,?,?)",
            (
                request.form["username"],
                request.form["email"],
                generate_password_hash(request.form["password"])
            )
        )
        db.commit()
        db.close()
        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        db = connect()
        user = db.execute(
            "SELECT * FROM users WHERE email=?",
            (request.form["email"],)
        ).fetchone()
        db.close()

        if user and check_password_hash(user["password"], request.form["password"]):
            session["user"] = user["username"]
            return redirect("/")

        return "بيانات الدخول غير صحيحة"

    return render_template("login.html")


@app.route("/create_ad", methods=["GET","POST"])
def create_ad():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        db = connect()
        db.execute(
            "INSERT INTO ads(user,type,amount,price,payment,status) VALUES(?,?,?,?,?,?)",
            (
                session["user"],
                request.form["type"],
                request.form["amount"],
                request.form["price"],
                request.form["payment"],
                "OPEN"
            )
        )
        db.commit()
        db.close()
        return redirect("/")

    return render_template("create_ad.html")


@app.route("/buy/<int:id>")
def buy(id):
    if "user" not in session:
        return redirect("/login")

    db = connect()
    ad = db.execute("SELECT * FROM ads WHERE id=?", (id,)).fetchone()

    if not ad:
        db.close()
        return "الإعلان غير موجود"

    fee = float(ad["amount"]) * 0.02

    db.execute(
        "INSERT INTO trades(buyer,seller,amount,price,fee,status) VALUES(?,?,?,?,?,?)",
        (
            session["user"],
            ad["user"],
            ad["amount"],
            ad["price"],
            fee,
            "WAITING_PAYMENT"
        )
    )

    db.execute("UPDATE ads SET status='CLOSED' WHERE id=?", (id,))
    db.commit()
    db.close()

    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    setup()
    app.run(host="0.0.0.0", port=5000)
