from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

def db():
    con = sqlite3.connect("database.db")
    con.row_factory = sqlite3.Row
    return con


def init():
    con = db()

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
        status TEXT
    )
    """)

    con.commit()
    con.close()


init()


@app.route("/")
def home():

    con = db()

    ads = con.execute(
        "SELECT * FROM ads WHERE status='OPEN'"
    ).fetchall()

    con.close()

    return render_template("index.html", ads=ads)



@app.route("/add")
def add():

    con=db()

    con.execute("""
    INSERT INTO ads
    (user,amount,price,payment,status)
    VALUES
    ('Samer',100,300,'Reflect','OPEN')
    """)

    con.commit()
    con.close()

    return redirect("/")



@app.route("/buy/<int:id>")
def buy(id):

    con=db()

    ad=con.execute(
        "SELECT * FROM ads WHERE id=?",
        (id,)
    ).fetchone()


    con.execute("""
    INSERT INTO trades
    (buyer,seller,amount,price,status)
    VALUES
    (?,?,?,?,?)
    """,
    (
        "Buyer",
        ad["user"],
        ad["amount"],
        ad["price"],
        "WAITING_PAYMENT"
    ))


    con.execute(
        "UPDATE ads SET status='CLOSED' WHERE id=?",
        (id,)
    )


    con.commit()
    con.close()

    return "تم إنشاء الصفقة"


@app.route("/admin")
def admin():

    con=db()

    trades=con.execute(
        "SELECT * FROM trades"
    ).fetchall()

    con.close()

return render_template("index.html", ads=ads)


if __name__=="__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )
