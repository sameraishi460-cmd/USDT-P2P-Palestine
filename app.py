from flask import Flask, render_template, request, redirect, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "USDT_P2P_SECRET"


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
        status TEXT
    )
    """)


    db.commit()
    db.close()




@app.route("/")
def home():

    db=connect()

    ads=db.execute(
        "SELECT * FROM ads WHERE status='OPEN'"
    ).fetchall()

    db.close()

    return render_template(
        "index.html",
        ads=ads
    )




@app.route("/register", methods=["GET","POST"])
def register():

    if request.method=="POST":

        username=request.form["username"]
        email=request.form["email"]

        password=generate_password_hash(
            request.form["password"]
        )

        db=connect()

        db.execute(
        """
        INSERT INTO users
        (username,email,password)
        VALUES(?,?,?)
        """,
        (username,email,password)
        )

        db.commit()
        db.close()

        return redirect("/login")


    return render_template("register.html")





@app.route("/login", methods=["GET","POST"])
def login():

    if request.method=="POST":

        email=request.form["email"]
        password=request.form["password"]


        db=connect()

        user=db.execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
        ).fetchone()


        db.close()


        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user"]=user["username"]

            return redirect("/")


        return "خطأ في البيانات"


    return render_template("login.html")
