import sqlite3
import requests
from datetime import datetime


DATABASE = "database.db"


def update_price():

    try:

        # جلب سعر الدولار مقابل الشيكل
        url = "https://open.er-api.com/v6/latest/USD"

        data = requests.get(url, timeout=10).json()

        usd_ils = data["rates"]["ILS"]


        # سعر USDT المرجعي (نفس الدولار تقريباً)
        usdt_ils = usd_ils


        con = sqlite3.connect(DATABASE)


        con.execute(
            """
            UPDATE market_price
            SET usd_ils=?,
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
        con.close()


        print(
            "PRICE UPDATED:",
            usd_ils,
            usdt_ils
        )


    except Exception as e:

        print(
            "PRICE UPDATE ERROR:",
            e
        )



if __name__ == "__main__":

    update_price()
