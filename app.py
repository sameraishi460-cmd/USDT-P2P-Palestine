from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
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
        email TEXT UNIQUE,
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



@app.route("/upload_payment/<int:id>", methods=["POST"])
def upload_payment(id):

    file = request.files["proof"]

    filename = secure_filename(
        file.filename
    )

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
        SET proof=?,
        status='PAYMENT_SENT'
        WHERE id=?
        """,
        (
            filename,
            id
        )
    )


    db.commit()

    db.close()


    return redirect(
        "/trade/" + str(id)
    )



@app.route("/confirm/<int:id>")
def confirm(id):

    db = connect()

    db.execute(
        """
        UPDATE trades
        SET status='COMPLETED'
        WHERE id=?
        """,
        (id,)
    )

    db.commit()

    db.close()


    return redirect(
        "/trade/" + str(id)
    )



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



if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
