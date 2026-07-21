import requests
import sqlite3
import time


TOKEN = "8064024379:AAE3UZRfkPzhrr98w3WmO0dO5wlIzEugt_w"

ADMIN_CHAT_ID = "5681774891"

WEBAPP_URL = "https://usdt-p2p-palestine-1.onrender.com/"

DATABASE = "database.db"


def send_message(chat_id, text, keyboard=None):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    requests.post(url, json=data)


def notify_admin(text):
    send_message(ADMIN_CHAT_ID, text)



def get_stats():

    con = sqlite3.connect(DATABASE)

    users = con.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    trades = con.execute(
        "SELECT COUNT(*) FROM trades"
    ).fetchone()[0]

    profit = con.execute(
        "SELECT total FROM platform_profit WHERE id=1"
    ).fetchone()[0]

    con.close()

    return users, trades, profit



def bot_loop():

    last_update = 0

    while True:

        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

        params = {
            "offset": last_update + 1,
            "timeout": 30
        }

        r = requests.get(url, params=params).json()


        for update in r.get("result", []):

            last_update = update["update_id"]

            if "message" in update:

                chat_id = update["message"]["chat"]["id"]

                text = update["message"].get("text", "")


                if text == "/start":

                    keyboard = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "🚀 فتح التطبيق",
                                    "web_app": {
                                        "url": WEBAPP_URL
                                    }
                                }
                            ]
                        ]
                    }


                    send_message(
                        chat_id,
                        "مرحبا بك في منصة USDT P2P فلسطين 🇵🇸\n\nاضغط لفتح التطبيق:",
                        keyboard
                    )


                elif text == "/stats":

                    users, trades, profit = get_stats()

                    send_message(
                        chat_id,
                        f"""
📊 إحصائيات المنصة

👤 المستخدمين: {users}

💰 الصفقات: {trades}

💵 الأرباح: {profit}$
"""
                    )


        time.sleep(2)



if __name__ == "__main__":
    bot_loop()
