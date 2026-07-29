from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    jsonify,
    send_from_directory
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename

from functools import wraps

import sqlite3
import os
import shutil
import threading
import traceback
import time

from datetime import timedelta, datetime

import telegram_bot
import price_updater

from web3 import Web3


# ===============================
# FLASK CONFIG
# ===============================

app = Flask(__name__)

app.secret_key = "USDT_P2P_PALESTINE_SECRET_KEY_CHANGE_THIS"

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

app.config["UPLOAD_FOLDER"] = "uploads"


if not os.path.exists("uploads"):
    os.makedirs("uploads")


# ===============================
# DATABASE
# ===============================

DATABASE = "database.db"


def connect():

    con = sqlite3.connect(
        DATABASE,
        check_same_thread=False
    )

    con.row_factory = sqlite3.Row

    return con



# ===============================
# WEB3 BSC
# ===============================

NETWORK = "BSC"

BSC_RPC = "https://bsc-dataseed.binance.org/"


w3 = Web3(
    Web3.HTTPProvider(BSC_RPC)
)


PLATFORM_WALLET = Web3.to_checksum_address(
    "0x659dd7cba24363c903abe3fddfc89eb30ffbf58a"
)


USDT_CONTRACT = Web3.to_checksum_address(
    "0x55d398326f99059fF775485246999027B3197955"
)


USDT_ABI = [

{
    "constant": True,

    "inputs":[
        {
            "name":"_owner",
            "type":"address"
        }
    ],

    "name":"balanceOf",

    "outputs":[
        {
            "name":"balance",
            "type":"uint256"
        }
    ],

    "type":"function"
}

]


usdt_contract = w3.eth.contract(
    address=USDT_CONTRACT,
    abi=USDT_ABI
)



# ===============================
# DATABASE HELPERS
# ===============================


def column_exists(
        con,
        table,
        column
):

    result = con.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()


    return any(
        row["name"] == column
        for row in result
    )



def add_column(
        con,
        table,
        column,
        datatype
):

    if not column_exists(
        con,
        table,
        column
    ):

        con.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {column} {datatype}
            """
        )



# ===============================
# DATABASE SETUP
# ===============================


def setup_database():

    con = connect()


    # USERS

    con.execute(
    """
    CREATE TABLE IF NOT EXISTS users(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE,

        password TEXT,

        phone TEXT DEFAULT '',

        bank TEXT DEFAULT '',

        iban TEXT DEFAULT '',

        payment_method TEXT DEFAULT '',

        usdt_wallet TEXT DEFAULT '',

        rating REAL DEFAULT 5,

        verified INTEGER DEFAULT 0,

        trades_count INTEGER DEFAULT 0,

        status TEXT DEFAULT 'ACTIVE',

        telegram_id TEXT

    )
    """
    )



    # WALLETS

    con.execute(
    """
    CREATE TABLE IF NOT EXISTS wallets(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE,

        balance REAL DEFAULT 0,

        locked REAL DEFAULT 0

    )
    """
    )



    # ADS

    con.execute(
    """
    CREATE TABLE IF NOT EXISTS ads(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user TEXT,

        title TEXT,

        amount REAL,

        price REAL,

        payment TEXT,

        status TEXT DEFAULT 'OPEN',

        created DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )



    # TRADES

    con.execute(
    """
    CREATE TABLE IF NOT EXISTS trades(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        ad_id INTEGER,

        buyer TEXT,

        seller TEXT,

        amount REAL,

        price REAL,

        fee REAL DEFAULT 0,

        status TEXT DEFAULT 'PENDING',

        payment_proof TEXT DEFAULT '',

        escrow_status TEXT DEFAULT 'WAITING',

        usdt_tx_hash TEXT DEFAULT '',

        release_tx_hash TEXT DEFAULT '',

        created DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )


    # CASH ADS

    con.execute(
    """
    CREATE TABLE IF NOT EXISTS cash_ads(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user TEXT,

        title TEXT,

        amount REAL,

        price REAL,

        payment TEXT,

        status TEXT DEFAULT 'OPEN',

        created DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )


    # MARKET PRICE

    con.execute(
    """
    CREATE TABLE IF NOT EXISTS market_price(

        id INTEGER PRIMARY KEY,

        usd_ils REAL DEFAULT 3.70,

        usdt_ils REAL DEFAULT 3.70,

        updated DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )

    # USDT DEPOSITS

    con.execute(
    """
    CREATE TABLE IF NOT EXISTS usdt_deposits(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT,

        amount REAL,

        tx_hash TEXT UNIQUE,

        status TEXT DEFAULT 'PENDING',

        created DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )


    # WITHDRAW REQUESTS

    con.execute(
    """
    CREATE TABLE IF NOT EXISTS withdraw_requests(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT,

        amount REAL,

        wallet TEXT,

        status TEXT DEFAULT 'PENDING',

        created DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )


    # FIX OLD DATABASE
    if not column_exists(con, "market_price", "updated"):

        con.execute(
        """
        ALTER TABLE market_price
        ADD COLUMN updated DATETIME
        """
        )


    # INSERT DEFAULT PRICE

    check_price = con.execute(
        """
        SELECT *
        FROM market_price
        WHERE id=1
        """
    ).fetchone()


    if not check_price:

        con.execute(
        """
        INSERT INTO market_price
        (
        id,
        usd_ils,
        usdt_ils
        )
        VALUES(1,3.70,3.70)
        """
        )


    con.commit()

    con.close()



setup_database()


print(
    "DATABASE:",
    os.path.abspath(DATABASE)
)


# ===============================
# AUTH SYSTEM
# ===============================


def login_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if "user" not in session:

            return redirect("/login")

        return func(*args, **kwargs)

    return wrapper



def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        if "user" not in session:

            return redirect("/login")


        con = connect()

        user = con.execute(
            """
            SELECT *
            FROM users
            WHERE username=?
            """,
            (
                session["user"],
            )
        ).fetchone()


        con.close()


        if not user or user["status"] != "ADMIN":

            return "غير مصرح لك",403


        return func(*args, **kwargs)


    return wrapper



# ===============================
# NOTIFICATIONS
# ===============================


def notify(
        username,
        title,
        message
):

    con = connect()

    con.execute(
        """
        INSERT INTO notifications
        (username,title,message)
        VALUES(?,?,?)
        """,
        (
            username,
            title,
            message
        )
    )


    con.commit()

    con.close()



# إنشاء جدول الإشعارات

def create_extra_tables():

    con = connect()


    con.execute(
    """
    CREATE TABLE IF NOT EXISTS notifications(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT,

        title TEXT,

        message TEXT,

        seen INTEGER DEFAULT 0,

        created DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )


    con.execute(
    """
    CREATE TABLE IF NOT EXISTS messages(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        sender TEXT,

        receiver TEXT,

        text TEXT,

        created DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )


    con.commit()

    con.close()



create_extra_tables()



# ===============================
# CREATE ADMIN
# ===============================


def create_admin_account():

    con = connect()


    admin = con.execute(
        """
        SELECT *
        FROM users
        WHERE username='Admin'
        """
    ).fetchone()



    if not admin:


        con.execute(
        """
        INSERT INTO users
        (
        username,
        password,
        status
        )

        VALUES(?,?,?)
        """,

        (
            "Admin",
            generate_password_hash(
                "SA526614@mer"
            ),
            "ADMIN"
        )

        )


        con.commit()


        print(
            "ADMIN CREATED"
        )


    con.close()



create_admin_account()



# ===============================
# REGISTER
# ===============================


@app.route(
    "/register",
    methods=["GET","POST"]
)

def register():


    if request.method=="POST":


        username=request.form.get(
            "username"
        )


        password=request.form.get(
            "password"
        )


        if not username or not password:

            return "بيانات ناقصة"



        con=connect()


        try:


            con.execute(
            """
            INSERT INTO users
            (
            username,
            password
            )
            VALUES(?,?)
            """,

            (
                username,
                generate_password_hash(password)
            )

            )


            con.execute(
            """
            INSERT INTO wallets
            (
            username
            )
            VALUES(?)
            """,

            (
                username,
            )

            )


            con.commit()


            session["user"]=username


            con.close()


            return redirect(
                "/dashboard"
            )


        except Exception as e:


            con.close()


            return "المستخدم موجود"



    return render_template(
        "register.html"
    )



# ===============================
# LOGIN
# ===============================


@app.route(
    "/login",
    methods=["GET","POST"]
)

def login():


    if request.method=="POST":


        username=request.form.get(
            "username"
        )


        password=request.form.get(
            "password"
        )


        con=connect()


        user=con.execute(
        """
        SELECT *
        FROM users
        WHERE username=?
        """,

        (
            username,
        )

        ).fetchone()


        con.close()



        if user and check_password_hash(
            user["password"],
            password
        ):


            if user["status"]=="BANNED":

                return "الحساب محظور"



            session.permanent=True

            session["user"]=username


            return redirect(
                "/dashboard"
            )



        return "خطأ في البيانات"



    return render_template(
        "login.html"
    )



# ===============================
# LOGOUT
# ===============================


@app.route("/logout")

def logout():

    session.clear()

    return redirect(
        "/login"
    )



# ===============================
# ADMIN LOGIN
# ===============================


@app.route(
    "/admin_login",
    methods=["GET","POST"]
)

def admin_login():


    if request.method=="POST":


        username=request.form.get(
            "username"
        )

        password=request.form.get(
            "password"
        )



        con=connect()


        user=con.execute(
        """
        SELECT *
        FROM users
        WHERE username=?
        """,

        (
            username,
        )

        ).fetchone()


        con.close()



        if (
            user
            and user["status"]=="ADMIN"
            and check_password_hash(
                user["password"],
                password
            )
        ):


            session["user"]=username


            return redirect(
                "/admin"
            )



        return "بيانات الأدمن خاطئة"



    return render_template(
        "admin_login.html"
    )



# ===============================
# DASHBOARD
# ===============================


@app.route("/dashboard")

@login_required

def dashboard():


    con=connect()


    user=con.execute(
    """
    SELECT *
    FROM users
    WHERE username=?
    """,

    (
        session["user"],
    )

    ).fetchone()



    trades=con.execute(
    """
    SELECT COUNT(*)
    FROM trades
    WHERE buyer=? OR seller=?
    """,

    (
        session["user"],
        session["user"]
    )

    ).fetchone()[0]



    con.close()


    return render_template(
        "dashboard.html",
        user=user,
        trades=trades
    )


# ===============================
# WALLET FUNCTIONS
# ===============================


def create_wallet_if_missing(username):

    con = connect()

    wallet = con.execute(
        """
        SELECT *
        FROM wallets
        WHERE username=?
        """,
        (username,)
    ).fetchone()


    if not wallet:

        con.execute(
            """
            INSERT INTO wallets
            (
            username,
            balance,
            locked
            )
            VALUES(?,?,?)
            """,
            (
                username,
                0,
                0
            )
        )

        con.commit()


    con.close()



def wallet_log(
        username,
        action,
        amount
):

    con = connect()

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS wallet_history(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT,

            action TEXT,

            amount REAL,

            created DATETIME DEFAULT CURRENT_TIMESTAMP

        )
        """
    )


    con.execute(
        """
        INSERT INTO wallet_history
        (
        username,
        action,
        amount
        )
        VALUES(?,?,?)
        """,
        (
            username,
            action,
            amount
        )
    )


    con.commit()

    con.close()



# ===============================
# HOME PAGE
# ===============================


@app.route("/")
def home():

    con = connect()

    ads = con.execute(
        """
        SELECT *
        FROM ads
        WHERE status='OPEN'
        ORDER BY id DESC
        """
    ).fetchall()


    cash_ads = con.execute(
        """
        SELECT *
        FROM cash_ads
        WHERE status='OPEN'
        ORDER BY id DESC
        """
    ).fetchall()


    price = con.execute(
        """
        SELECT *
        FROM market_price
        WHERE id=1
        """
    ).fetchone()


    user = None

    if "user" in session:
        user = session["user"]


    con.close()


    return render_template(
        "index.html",
        ads=ads,
        cash_ads=cash_ads,
        price=price,
        user=user
    )



# ===============================
# MARKET
# ===============================


@app.route("/market")

def market():

    con = connect()


    ads = con.execute(
        """
        SELECT *
        FROM ads
        WHERE status='OPEN'
        ORDER BY id DESC
        """
    ).fetchall()



    con.close()


    return render_template(
        "market.html",
        ads=ads
    )



# ===============================
# CREATE USDT AD
# ===============================


@app.route(
    "/create_ad",
    methods=["GET","POST"]
)

@login_required

def create_ad():


    con = connect()


    user = con.execute(
        """
        SELECT *
        FROM users
        WHERE username=?
        """,
        (
            session["user"],
        )
    ).fetchone()



    if request.method=="POST":


        title=request.form.get(
            "title"
        )


        amount=float(
            request.form.get(
                "amount",
                0
            )
        )


        price=float(
            request.form.get(
                "price",
                0
            )
        )


        payment=request.form.get(
            "payment",
            "BANK"
        )



        con.execute(
        """
        INSERT INTO ads
        (
        user,
        title,
        amount,
        price,
        payment
        )
        VALUES(?,?,?,?,?)
        """,

        (
            session["user"],
            title,
            amount,
            price,
            payment
        )

        )


        con.commit()

        con.close()


        return redirect(
            "/market"
        )



    con.close()


    return render_template(
        "create_ad.html",
        user=user
    )



# ===============================
# TRADE FEE
# ===============================


def get_trade_fee(price):

    fee_percent = 1


    return (
        price *
        fee_percent /
        100
    )



# ===============================
# BUY USDT
# ===============================


@app.route(
    "/buy/<int:id>"
)

@login_required

def buy(id):


    con=connect()



    ad=con.execute(
    """
    SELECT *
    FROM ads
    WHERE id=?
    """,
    (id,)
    ).fetchone()



    if not ad:

        con.close()

        return "الإعلان غير موجود"



    if ad["status"]!="OPEN":

        con.close()

        return "الإعلان مغلق"



    if ad["user"]==session["user"]:

        con.close()

        return "لا يمكنك شراء إعلانك"



    seller_wallet=con.execute(
    """
    SELECT *
    FROM wallets
    WHERE username=?
    """,
    (
        ad["user"],
    )

    ).fetchone()



    if not seller_wallet:

        con.close()

        return "لا توجد محفظة للبائع"



    if seller_wallet["balance"] < ad["amount"]:

        con.close()

        return "البائع لا يملك رصيد USDT كافي"



    # حجز USDT

    con.execute(
    """
    UPDATE wallets

    SET

    balance = balance - ?,

    locked = locked + ?

    WHERE username=?

    """,

    (
        ad["amount"],
        ad["amount"],
        ad["user"]
    )

    )



    wallet_log(
        ad["user"],
        "ESCROW_LOCK",
        ad["amount"]
    )



    fee=get_trade_fee(
        ad["price"]
    )



    trade=con.execute(
    """
    INSERT INTO trades
    (
    ad_id,
    buyer,
    seller,
    amount,
    price,
    fee,
    status,
    escrow_status
    )

    VALUES(?,?,?,?,?,?,?,?)

    """,

    (
        id,
        session["user"],
        ad["user"],
        ad["amount"],
        ad["price"],
        fee,
        "PENDING",
        "LOCKED"
    )

    )



    trade_id=trade.lastrowid



    con.execute(
    """
    UPDATE ads

    SET status='SOLD'

    WHERE id=?

    """,
    (id,)
    )



    con.commit()

    con.close()



    notify(
        ad["user"],
        "تم حجز USDT",
        f"تم حجز {ad['amount']} USDT للصفقة"
    )


    notify(
        session["user"],
        "تم إنشاء الصفقة",
        "يمكنك التواصل مع البائع"
    )


    return redirect(
        "/trade/"+str(trade_id)
    )


# ===============================
# TRADE PAGE + CHAT
# ===============================


@app.route(
    "/trade/<int:id>",
    methods=["GET","POST"]
)

@login_required

def trade(id):

    con = connect()


    trade = con.execute(
        """
        SELECT *
        FROM trades
        WHERE id=?
        """,
        (id,)
    ).fetchone()



    if not trade:

        con.close()

        return "الصفقة غير موجودة"



    if request.method=="POST":


        text=request.form.get(
            "message"
        )


        receiver=request.form.get(
            "receiver"
        )


        if text and receiver:


            con.execute(
            """
            INSERT INTO messages
            (
            sender,
            receiver,
            text
            )
            VALUES(?,?,?)
            """,

            (
                session["user"],
                receiver,
                text
            )

            )


            con.commit()



    messages=con.execute(
    """
    SELECT *
    FROM messages

    WHERE

    (sender=? AND receiver=?)

    OR

    (sender=? AND receiver=?)

    ORDER BY id ASC

    """,

    (
        session["user"],
        trade["seller"],
        trade["seller"],
        session["user"]
    )

    ).fetchall()



    con.close()



    return render_template(
        "trade.html",
        trade=trade,
        messages=messages
    )



# ===============================
# CONFIRM PAYMENT BY BUYER
# ===============================


@app.route(
    "/confirm_payment/<int:id>"
)

@login_required

def confirm_payment(id):


    con=connect()



    trade=con.execute(
    """
    SELECT *
    FROM trades
    WHERE id=?
    """,
    (id,)
    ).fetchone()



    if not trade:

        con.close()

        return "الصفقة غير موجودة"



    if trade["buyer"] != session["user"]:

        con.close()

        return "غير مصرح"



    con.execute(
    """
    UPDATE trades

    SET status='PAYMENT_SENT'

    WHERE id=?

    """,
    (id,)
    )


    con.commit()

    con.close()



    notify(
        trade["seller"],
        "تم إرسال الدفع",
        "المشتري أكد إرسال المبلغ"
    )


    return redirect(
        "/trade/"+str(id)
    )



# ===============================
# UPLOAD PAYMENT PROOF
# ===============================


@app.route(
    "/upload_payment/<int:id>",
    methods=["POST"]
)

@login_required

def upload_payment(id):


    if "proof" not in request.files:

        return "لم يتم اختيار ملف"



    file=request.files["proof"]


    if file.filename=="":

        return "الملف فارغ"



    con=connect()



    trade=con.execute(
    """
    SELECT *
    FROM trades
    WHERE id=?
    """,
    (id,)
    ).fetchone()



    if not trade:

        con.close()

        return "الصفقة غير موجودة"



    if trade["buyer"] != session["user"]:

        con.close()

        return "غير مصرح"



    filename=secure_filename(
        f"payment_{id}_{file.filename}"
    )


    path=os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )


    file.save(path)



    con.execute(
    """
    UPDATE trades

    SET payment_proof=?

    WHERE id=?

    """,

    (
        filename,
        id
    )

    )


    con.commit()

    con.close()



    notify(
        trade["seller"],
        "إثبات دفع",
        "تم رفع إثبات الدفع"
    )



    return redirect(
        "/trade/"+str(id)
    )



# ===============================
# SELLER RELEASE ESCROW
# ===============================


@app.route(
    "/seller_confirm/<int:id>"
)

@login_required

def seller_confirm(id):


    con=connect()



    trade=con.execute(
    """
    SELECT *
    FROM trades
    WHERE id=?
    """,
    (id,)
    ).fetchone()



    if not trade:

        con.close()

        return "الصفقة غير موجودة"



    if trade["seller"] != session["user"]:

        con.close()

        return "غير مصرح"



    if not trade["payment_proof"]:

        con.close()

        return """
        لا يمكن تحرير USDT قبل وجود إثبات الدفع
        """



    if trade["status"]=="COMPLETED":

        con.close()

        return "الصفقة مكتملة"



    amount=trade["amount"]



    # إزالة المحجوز من البائع

    con.execute(
    """
    UPDATE wallets

    SET locked = locked - ?

    WHERE username=?

    """,

    (
        amount,
        trade["seller"]
    )

    )



    wallet_log(
        trade["seller"],
        "ESCROW_RELEASE",
        amount
    )



    # إضافة للمشتري

    create_wallet_if_missing(
        trade["buyer"]
    )


    con.execute(
    """
    UPDATE wallets

    SET balance = balance + ?

    WHERE username=?

    """,

    (
        amount,
        trade["buyer"]
    )

    )


    wallet_log(
        trade["buyer"],
        "USDT_RECEIVED",
        amount
    )



    con.execute(
    """
    UPDATE trades

    SET

    status='COMPLETED',

    escrow_status='RELEASED'

    WHERE id=?

    """,

    (id,)

    )



    con.commit()

    con.close()



    notify(
        trade["buyer"],
        "تم استلام USDT",
        f"تم تحويل {amount} USDT لمحفظتك"
    )


    notify(
        trade["seller"],
        "تم إنهاء الصفقة",
        "تم تحرير USDT بنجاح"
    )



    return redirect(
        "/trade/"+str(id)
    )



# ===============================
# UPLOADS VIEW
# ===============================


@app.route(
    "/uploads/<filename>"
)

def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# ===============================
# WALLET PAGE
# ===============================


@app.route("/wallet")
@login_required
def wallet():

    con = connect()


    wallet = con.execute(
        """
        SELECT *
        FROM wallets
        WHERE username=?
        """,
        (
            session["user"],
        )
    ).fetchone()


    user = con.execute(
        """
        SELECT *
        FROM users
        WHERE username=?
        """,
        (
            session["user"],
        )
    ).fetchone()


    con.close()


    return render_template(
        "wallet.html",
        wallet=wallet,
        user=user
    )



# ===============================
# USDT DEPOSIT REQUEST
# ===============================


@app.route(
    "/usdt_deposit",
    methods=["GET","POST"]
)

@login_required

def usdt_deposit():


    if request.method=="POST":


        amount=float(
            request.form.get(
                "amount",
                0
            )
        )


        tx_hash=request.form.get(
            "tx_hash",
            ""
        )



        if amount <= 0 or not tx_hash:

            return "بيانات ناقصة"



        con=connect()



        con.execute(
        """
        CREATE TABLE IF NOT EXISTS usdt_deposits(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT,

            amount REAL,

            tx_hash TEXT UNIQUE,

            status TEXT DEFAULT 'PENDING',

            created DATETIME DEFAULT CURRENT_TIMESTAMP

        )
        """
        )



        con.execute(
        """
        INSERT INTO usdt_deposits
        (
        username,
        amount,
        tx_hash
        )

        VALUES(?,?,?)

        """,

        (
            session["user"],
            amount,
            tx_hash
        )

        )


        con.commit()

        con.close()



        try:

            telegram_bot.send_admin(
            f"""
💰 إيداع USDT جديد

👤 المستخدم:
{session['user']}

💵 الكمية:
{amount} USDT

🔗 TX:
{tx_hash}
"""
            )

        except:

            pass



        return redirect(
            "/wallet"
        )



    return render_template(
        "usdt_deposit.html",
        wallet=PLATFORM_WALLET
    )



# ===============================
# CHECK BSC TRANSACTION
# ===============================


def check_usdt_transaction(
        tx_hash,
        expected_amount
):

    try:


        receipt=w3.eth.get_transaction_receipt(
            tx_hash
        )


        if receipt.status != 1:

            return False



        balance=usdt_contract.functions.balanceOf(
            PLATFORM_WALLET
        ).call()



        current=balance / 10**18



        if current >= expected_amount:

            return True



        return False



    except Exception as e:


        print(
            "USDT CHECK ERROR:",
            e
        )


        return False



# ===============================
# WITHDRAW REQUEST
# ===============================


@app.route(
    "/withdraw",
    methods=["GET","POST"]
)

@login_required

def withdraw():


    con=connect()


    wallet=con.execute(
    """
    SELECT *
    FROM wallets
    WHERE username=?
    """,
    (
        session["user"],
    )

    ).fetchone()



    if request.method=="POST":


        amount=float(
            request.form.get(
                "amount",
                0
            )
        )


        address=request.form.get(
            "wallet"
        )



        if amount <= 0:

            con.close()

            return "كمية غير صحيحة"



        if wallet["balance"] < amount:

            con.close()

            return "الرصيد غير كافي"



        con.execute(
        """
        CREATE TABLE IF NOT EXISTS withdraw_requests(

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT,

            amount REAL,

            wallet TEXT,

            status TEXT DEFAULT 'PENDING'

        )
        """
        )



        con.execute(
        """
        INSERT INTO withdraw_requests
        (
        username,
        amount,
        wallet
        )

        VALUES(?,?,?)

        """,

        (
            session["user"],
            amount,
            address
        )

        )



        con.execute(
        """
        UPDATE wallets

        SET balance=balance-?

        WHERE username=?

        """,

        (
            amount,
            session["user"]
        )

        )


        con.commit()

        con.close()



        try:

            telegram_bot.send_admin(
            f"""
📤 طلب سحب USDT

👤 المستخدم:
{session['user']}

💰 الكمية:
{amount}

🏦 العنوان:
{address}
"""
            )

        except:

            pass



        return redirect(
        "/wallet"
        )



    con.close()


    return render_template(
        "withdraw.html",
        wallet=wallet
    )



# ===============================
# ADMIN PANEL
# ===============================


@app.route("/admin")
@admin_required

def admin():


    con=connect()


    users=con.execute(
        """
        SELECT *
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()



    trades=con.execute(
        """
        SELECT *
        FROM trades
        ORDER BY id DESC
        """
    ).fetchall()



    deposits=con.execute(
        """
        SELECT *
        FROM usdt_deposits
        ORDER BY id DESC
        """
    ).fetchall()



    con.close()



    return render_template(
        "admin.html",
        users=users,
        trades=trades,
        deposits=deposits
    )



# ===============================
# ADMIN CONFIRM DEPOSIT
# ===============================


@app.route(
    "/admin_confirm_deposit/<int:id>"
)

@admin_required

def admin_confirm_deposit(id):


    con=connect()



    deposit=con.execute(
    """
    SELECT *
    FROM usdt_deposits
    WHERE id=?
    """,
    (id,)
    ).fetchone()



    if not deposit:

        con.close()

        return "الإيداع غير موجود"



    if deposit["status"]=="CONFIRMED":

        con.close()

        return "تم التأكيد مسبقاً"



    verified=check_usdt_transaction(
        deposit["tx_hash"],
        deposit["amount"]
    )



    if not verified:

        con.close()

        return "لم يتم العثور على التحويل"



    create_wallet_if_missing(
        deposit["username"]
    )



    con.execute(
    """
    UPDATE wallets

    SET balance=balance+?

    WHERE username=?

    """,

    (
        deposit["amount"],
        deposit["username"]
    )

    )



    con.execute(
    """
    UPDATE usdt_deposits

    SET status='CONFIRMED'

    WHERE id=?

    """,

    (id,)

    )



    con.commit()

    con.close()



    notify(
        deposit["username"],
        "تم قبول الإيداع",
        f"تم إضافة {deposit['amount']} USDT"
    )



    return redirect(
        "/admin"
    )


# ===============================
# PROFILE
# ===============================


@app.route("/profile")
@login_required

def profile():

    con=connect()


    user=con.execute(
    """
    SELECT *
    FROM users
    WHERE username=?
    """,
    (
        session["user"],
    )

    ).fetchone()



    ads=con.execute(
    """
    SELECT *
    FROM ads
    WHERE user=?
    ORDER BY id DESC
    """,
    (
        session["user"],
    )

    ).fetchall()



    trades=con.execute(
    """
    SELECT *
    FROM trades
    WHERE buyer=? OR seller=?
    ORDER BY id DESC
    """,
    (
        session["user"],
        session["user"]
    )

    ).fetchall()



    con.close()


    return render_template(
        "profile.html",
        user=user,
        ads=ads,
        trades=trades
    )



# ===============================
# EDIT PROFILE
# ===============================


@app.route(
    "/edit_profile",
    methods=["GET","POST"]
)

@login_required

def edit_profile():


    con=connect()



    if request.method=="POST":


        phone=request.form.get(
            "phone",
            ""
        )


        bank=request.form.get(
            "bank",
            ""
        )


        iban=request.form.get(
            "iban",
            ""
        )


        payment=request.form.get(
            "payment_method",
            ""
        )


        wallet=request.form.get(
            "usdt_wallet",
            ""
        )



        con.execute(
        """
        UPDATE users

        SET

        phone=?,

        bank=?,

        iban=?,

        payment_method=?,

        usdt_wallet=?

        WHERE username=?

        """,

        (
            phone,
            bank,
            iban,
            payment,
            wallet,
            session["user"]
        )

        )



        con.commit()

        con.close()



        return redirect(
            "/profile"
        )



    user=con.execute(
    """
    SELECT *
    FROM users
    WHERE username=?
    """,
    (
        session["user"],
    )

    ).fetchone()



    con.close()


    return render_template(
        "edit_profile.html",
        user=user
    )



# ===============================
# REVIEWS
# ===============================


@app.route(
    "/review/<int:id>",
    methods=["POST"]
)

@login_required

def review(id):


    rating=int(
        request.form.get(
            "rating",
            5
        )
    )


    comment=request.form.get(
        "comment",
        ""
    )


    con=connect()



    trade=con.execute(
    """
    SELECT *
    FROM trades
    WHERE id=?
    """,
    (id,)
    ).fetchone()



    if not trade:

        con.close()

        return "الصفقة غير موجودة"



    target = (
        trade["seller"]
        if session["user"]==trade["buyer"]
        else trade["buyer"]
    )



    con.execute(
    """
    CREATE TABLE IF NOT EXISTS reviews(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        trade_id INTEGER,

        from_user TEXT,

        to_user TEXT,

        rating INTEGER,

        comment TEXT

    )
    """
    )



    con.execute(
    """
    INSERT INTO reviews

    (
    trade_id,
    from_user,
    to_user,
    rating,
    comment
    )

    VALUES(?,?,?,?,?)

    """,

    (
        id,
        session["user"],
        target,
        rating,
        comment
    )

    )



    avg=con.execute(
    """
    SELECT AVG(rating)
    FROM reviews
    WHERE to_user=?
    """,
    (
        target,
    )

    ).fetchone()[0]



    if avg:

        con.execute(
        """
        UPDATE users

        SET rating=?

        WHERE username=?

        """,
        (
            round(avg,2),
            target
        )

        )



    con.commit()

    con.close()



    return redirect(
        "/profile"
    )



# ===============================
# NOTIFICATIONS PAGE
# ===============================


@app.route("/notifications")

@login_required

def notifications():


    con=connect()


    data=con.execute(
    """
    SELECT *
    FROM notifications

    WHERE username=?

    ORDER BY id DESC

    """,
    (
        session["user"],
    )

    ).fetchall()



    con.close()


    return render_template(
        "notifications.html",
        notifications=data
    )



# ===============================
# CASH ADS
# ===============================


@app.route(
    "/cash_market"
)

def cash_market():


    con=connect()


    ads=con.execute(
    """
    SELECT *
    FROM cash_ads
    WHERE status='OPEN'
    ORDER BY id DESC
    """
    ).fetchall()


    con.close()


    return render_template(
        "cash_market.html",
        ads=ads
    )



# ===============================
# START THREADS
# ===============================


def start_bot():

    try:

        telegram_bot.bot_loop()

    except Exception:

        print(
            traceback.format_exc()
        )



def update_prices():

    while True:

        try:

            price_updater.update_price()

        except Exception as e:

            print(
                "PRICE ERROR",
                e
            )


        time.sleep(
            3600
        )



try:

    threading.Thread(
        target=start_bot,
        daemon=True
    ).start()


except Exception:

    print(
        traceback.format_exc()
    )



try:

    threading.Thread(
        target=update_prices,
        daemon=True
    ).start()


except Exception:

    print(
        traceback.format_exc()
    )



# ===============================
# ADMIN MARKET PRICE CONTROL
# ===============================

@app.route("/admin_price", methods=["GET", "POST"])
@admin_required
def admin_price():

    con = connect()


    if request.method == "POST":

        usd = float(
            request.form.get("usd_ils", 0)
        )

        usdt = float(
            request.form.get("usdt_ils", 0)
        )


        con.execute(
        """
        UPDATE market_price

        SET

        usd_ils=?,

        usdt_ils=?,

        updated=?

        WHERE id=1
        """,
        (
            usd,
            usdt,
            datetime.now()
        )
        )


        con.commit()


    price = con.execute(
    """
    SELECT *
    FROM market_price
    WHERE id=1
    """
    ).fetchone()


    con.close()


    return render_template(
        "admin_price.html",
        price=price
    )



# ===============================
# CREATE CASH AD
# ===============================

@app.route(
    "/create_cash_ad",
    methods=["GET","POST"]
)
@login_required
def create_cash_ad():

    con = connect()


    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        )

        amount = float(
            request.form.get(
                "amount",
                0
            )
        )


        price = float(
            request.form.get(
                "price",
                0
            )
        )


        payment = request.form.get(
            "payment",
            "BANK"
        )


        if amount <= 0 or price <= 0:

            con.close()

            return "بيانات غير صحيحة"


        con.execute(
        """
        INSERT INTO cash_ads
        (
        user,
        title,
        amount,
        price,
        payment
        )

        VALUES(?,?,?,?,?)

        """,

        (
            session["user"],
            title,
            amount,
            price,
            payment
        )

        )


        con.commit()

        con.close()


        return redirect(
            "/cash_market"
        )


    con.close()


    return render_template(
        "create_cash_ad.html"
    )



# ===============================
# BUY CASH AD
# ===============================

@app.route(
    "/cash_buy/<int:id>"
)
@login_required
def cash_buy(id):

    con = connect()


    ad = con.execute(
    """
    SELECT *
    FROM cash_ads
    WHERE id=?
    """,
    (id,)
    ).fetchone()



    if not ad:

        con.close()

        return "الإعلان غير موجود"



    if ad["status"] != "OPEN":

        con.close()

        return "الإعلان مغلق"



    if ad["user"] == session["user"]:

        con.close()

        return "لا يمكنك شراء إعلانك"



    con.execute(
    """
    CREATE TABLE IF NOT EXISTS cash_trades(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        ad_id INTEGER,

        buyer TEXT,

        seller TEXT,

        amount REAL,

        price REAL,

        status TEXT DEFAULT 'PENDING',

        created DATETIME DEFAULT CURRENT_TIMESTAMP

    )
    """
    )



    trade = con.execute(
    """
    INSERT INTO cash_trades
    (
    ad_id,
    buyer,
    seller,
    amount,
    price
    )

    VALUES(?,?,?,?,?)

    """,

    (
        id,
        session["user"],
        ad["user"],
        ad["amount"],
        ad["price"]
    )

    )


    trade_id = trade.lastrowid



    con.execute(
    """
    UPDATE cash_ads

    SET status='SOLD'

    WHERE id=?

    """,
    (id,)
    )


    con.commit()

    con.close()



    notify(
        ad["user"],
        "طلب شراء كاش",
        "يوجد طلب جديد على إعلانك"
    )


    return redirect(
        "/cash_trade/"+str(trade_id)
    )



# ===============================
# CASH TRADE PAGE
# ===============================

@app.route(
    "/cash_trade/<int:id>"
)
@login_required
def cash_trade(id):

    con = connect()


    trade = con.execute(
    """
    SELECT *
    FROM cash_trades
    WHERE id=?
    """,
    (id,)
    ).fetchone()


    con.close()


    if not trade:

        return "الصفقة غير موجودة"


    return render_template(
        "cash_trade.html",
        trade=trade
    )



# ===============================
# ERROR HANDLER
# ===============================


@app.errorhandler(Exception)

def handle_error(error):

    print(
        traceback.format_exc()
    )

    return "حدث خطأ في السيرفر",500



# ===============================
# RUN
# ===============================


if __name__=="__main__":


    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
