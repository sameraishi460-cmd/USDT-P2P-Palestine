import sqlite3
import requests
from datetime import datetime


DATABASE = "database.db"


def update_price():

    try:

        url = "https://open.er-api.com/v6/latest/USD"

        response = requests.get(url, timeout=10)
        data = response.json()

        usd_ils = data["rates"]["ILS"]

        # USDT قريب من الدولار
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


        # للتأكد أنه انحفظ
        check = con.execute(
            "SELECT * FROM market_price WHERE id=1"
        ).fetchone()


        print("MARKET PRICE UPDATED:")
        print("USD:", check[1])
        print("USDT:", check[2])


        con.close()


    except Exception as e:

        print("PRICE UPDATE ERROR:", e)



if __name__ == "__main__":
    update_price()
