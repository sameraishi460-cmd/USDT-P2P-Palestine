import sqlite3
import requests
from datetime import datetime


DATABASE = "database.db"


def column_exists(con, table, column):

    result = con.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return any(
        row[1] == column
        for row in result
    )


def update_price():

    con = None

    try:

        # جلب سعر الدولار مقابل الشيكل
        url = "https://open.er-api.com/v6/latest/USD"

        response = requests.get(
            url,
            timeout=10
        )

        data = response.json()


        usd_ils = data["rates"]["ILS"]

        # USDT قريب من الدولار
        usdt_ils = usd_ils



        con = sqlite3.connect(
            DATABASE
        )


        # تأكد أن جدول market_price موجود
        con.execute(
        """
        CREATE TABLE IF NOT EXISTS market_price(

            id INTEGER PRIMARY KEY,

            usd_ils REAL DEFAULT 3.70,

            usdt_ils REAL DEFAULT 3.70

        )
        """
        )


        # إضافة updated إذا غير موجود
        if not column_exists(
            con,
            "market_price",
            "updated"
        ):

            con.execute(
            """
            ALTER TABLE market_price
            ADD COLUMN updated DATETIME
            """
            )



        # تأكد وجود صف رقم 1
        check = con.execute(
        """
        SELECT *
        FROM market_price
        WHERE id=1
        """
        ).fetchone()



        if not check:

            con.execute(
            """
            INSERT INTO market_price
            (
                id,
                usd_ils,
                usdt_ils,
                updated
            )
            VALUES(1,?,?,?)
            """,
            (
                round(usd_ils,3),
                round(usdt_ils,3),
                datetime.now()
            )
            )


        else:

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
                round(usd_ils,3),
                round(usdt_ils,3),
                datetime.now()
            )
            )



        con.commit()



        result = con.execute(
        """
        SELECT *
        FROM market_price
        WHERE id=1
        """
        ).fetchone()



        print("MARKET PRICE UPDATED ✅")
        print("USD:", result[1])
        print("USDT:", result[2])
        print("TIME:", result[3])



    except Exception as e:

        print(
            "PRICE UPDATE ERROR:",
            e
        )


    finally:

        if con:

            con.close()



if __name__ == "__main__":

    update_price()
