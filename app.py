from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "USDT_P2P_SECRET"

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def connect():
    db = sqlite3.connect("database.db")
    db.row_factory = sqlite3.Row
    return db


def setup():

    db = connect()

    db.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        email TEXT,
        password TEXT
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        type TEXT,
        amount REAL,
        price REAL,
        payment TEXT,
        status TEXT
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS trades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        buyer TEXT,
        seller TEXT,
        amount REAL,
        price REAL,
        fee REAL,
        status TEXT,
        proof TEXT
    )
    """)

    db.commit()
    db.close()


setup()


@app.route("/")
def home():

    db = connect()

    ads = db.execute(
        "SELECT * FROM ads WHERE status='OPEN'"
    ).fetchall()

    db.close()

    return render_template(
        "index.html",
        ads=ads
    )


@app.route("/create_ad", methods=["GET","POST"])
def create_ad():

    if request.method == "POST":

        db = connect()

        db.execute("""
        INSERT INTO ads
        (user,type,amount,price,payment,status)
        VALUES(?,?,?,?,?,?)
        """,
        (
            session.get("user","Guest"),
            request.form["type"],
            request.form["amount"],
            request.form["price"],
            request.form["payment"],
            "OPEN"
        ))

        db.commit()
        db.close()

        return redirect("/")

    return render_template("create_ad.html")


@app.route("/buy/<int:id>")
def buy(id):

    db = connect()

    ad = db.execute(
        "SELECT * FROM ads WHERE id=?",
        (id,)
    ).fetchone()


    fee = float(ad["amount"]) * 0.02


    db.execute("""
    INSERT INTO trades
    (buyer,seller,amount,price,fee,status,proof)
    VALUES(?,?,?,?,?,?,?)
    """,
    (
        session.get("user","Guest"),
        ad["user"],
        ad["amount"],
        ad["price"],
        fee,
        "WAITING_PAYMENT",
        ""
    ))


    db.execute(
        "UPDATE ads SET status='CLOSED' WHERE id=?",
        (id,)
    )


    db.commit()
    db.close()

    return redirect("/")
 @app.route("/trade/<int:id>")
def trade(id):

    db = connect()

    trade = db.execute(
        "SELECT * FROM trades WHERE id=?",
        (id,)
    ).fetchone()

    db.close()

    return render_template(
        "trade.html",
        trade=trade
    )


@app.route("/upload_payment/<int:id>", methods=["POST"])
def upload_payment(id):

    file = request.files["proof"]

    filename = secure_filename(file.filename)

    file.save(
        os.path.join(
            UPLOAD_FOLDER,
            filename
        )
    )

    db = connect()

    db.execute(
        """
        UPDATE trades
        SET proof=?, status='PAYMENT_SENT'
        WHERE id=?
        """,
        (filename, id)
    )

    db.commit()
    db.close()

    return redirect("/trade/" + str(id))


@app.route("/confirm/<int:id>")
def confirm(id):

    db = connect()

    db.execute(
        "UPDATE trades SET status='COMPLETED' WHERE id=?",
        (id,)
    )

    db.commit()
    db.close()

    return redirect("/trade/" + str(id))


@app.route("/admin")
def admin():

    db = connect()

    trades = db.execute(
        "SELECT * FROM trades ORDER BY id DESC"
    ).fetchall()

    db.close()

    return render_template(
        "admin.html",
        trades=trades
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
