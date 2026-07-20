from flask import Flask, render_template, request, redirect, session
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "USDT_P2P_SECRET"

ADMIN_PASS = "123456"

def db():
    x = sqlite3.connect("database.db")
    x.row_factory = sqlite3.Row
    return x


def setup():
    c = db()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    username TEXT,
    email TEXT,
    password TEXT)
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ads(
    id INTEGER PRIMARY KEY,
    user TEXT,
    type TEXT,
    amount REAL,
    price REAL,
    payment TEXT,
    status TEXT)
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS trades(
    id INTEGER PRIMARY KEY,
    buyer TEXT,
    seller TEXT,
    amount REAL,
    price REAL,
    status TEXT,
    proof TEXT)
    """)

    c.commit()
    c.close()


setup()


@app.route("/")
def home():

    c=db()

    ads=c.execute(
        "SELECT * FROM ads WHERE status='OPEN'"
    ).fetchall()

    c.close()

    return render_template(
        "index.html",
        ads=ads
    )


@app.route("/create_ad",methods=["GET","POST"])
def create_ad():

    if request.method=="POST":

        c=db()

        c.execute("""
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

        c.commit()
        c.close()

        return redirect("/")

    return render_template("create_ad.html")


@app.route("/buy/<int:id>")
def buy(id):

    c=db()

    ad=c.execute(
        "SELECT * FROM ads WHERE id=?",
        (id,)
    ).fetchone()


    c.execute("""
    INSERT INTO trades
    (buyer,seller,amount,price,status,proof)
    VALUES(?,?,?,?,?,?)
    """,
    (
    session.get("user","Guest"),
    ad["user"],
    ad["amount"],
    ad["price"],
    "WAITING_PAYMENT",
    ""
    ))


    c.execute(
        "UPDATE ads SET status='CLOSED' WHERE id=?",
        (id,)
    )

    c.commit()
    c.close()

    return redirect("/")


@app.route("/admin")
def admin():

    if request.args.get("pass") != ADMIN_PASS:
        return "غير مسموح"

    c=db()

    trades=c.execute(
        "SELECT * FROM trades"
    ).fetchall()

    c.close()

    return render_template(
        "admin.html",
        trades=trades
    )


@app.route("/confirm/<int:id>")
def confirm(id):

    c=db()

    c.execute(
        "UPDATE trades SET status='COMPLETED' WHERE id=?",
        (id,)
    )

    c.commit()
    c.close()

    return redirect("/")


if __name__=="__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )
