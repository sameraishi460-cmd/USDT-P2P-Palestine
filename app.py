from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "USDT_SECRET_KEY"

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

    current_user = session.get("user")

    return render_template("index.html", ads=ads, user=current_user)


@app.route("/create_ad", methods=["GET", "POST"])
def create_ad():
    if request.method == "POST":
        user_name = request.form.get("user")
        amount = request.form.get("amount")
        price = request.form.get("price")
        payment = request.form.get("payment")

        if not user_name or not amount or not price or not payment:
            return redirect("/create_ad")

        con = connect()
        con.execute(
            """
        INSERT INTO ads
        (user, amount, price, payment, status)
        VALUES (?, ?, ?, ?, ?)
        """,
            (user_name, float(amount), float(price), payment, "OPEN"),
        )

        con.commit()
        con.close()

        return redirect("/")

    return render_template("create_ad.html")


@app.route("/buy/<int:id>")
def buy(id):
    con = connect()

    ad = con.execute("SELECT * FROM ads WHERE id=?", (id,)).fetchone()

    if not ad or ad["status"] != "OPEN":
        con.close()
        return redirect("/")

    buyer_name = session.get("user", "Buyer")

    con.execute(
        """
    INSERT INTO trades
    (buyer, seller, amount, price, status, proof)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
        (buyer_name, ad["user"], ad["amount"], ad["price"], "WAITING_PAYMENT", ""),
    )

    con.execute("UPDATE ads SET status='CLOSED' WHERE id=?", (id,))

    con.commit()
    con.close()

    return redirect("/")


@app.route("/trade/<int:id>")
def trade(id):
    con = connect()

    trade_item = con.execute("SELECT * FROM trades WHERE id=?", (id,)).fetchone()
    con.close()

    if not trade_item:
        return redirect("/")

    return render_template("trade.html", trade=trade_item)


@app.route("/upload_payment/<int:id>", methods=["POST"])
def upload_payment(id):
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


@app.route("/admin")
def admin():
    con = connect()

    trades = con.execute("SELECT * FROM trades").fetchall()
    con.close()

    return render_template("admin.html", trades=trades)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
