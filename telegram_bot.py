import requests
import time
import os


# ضع توكن البوت هنا
TOKEN = "8881823408:AAFOF1wDyMjrW7hLQAy9hwY2LvzzeddxQbk"


# رابط منصتك
WEBAPP_URL = "https://usdt-p2p-palestine-1.onrender.com/telegram_login"


def telegram_api(method, data=None):

    url = f"https://api.telegram.org/bot{TOKEN}/{method}"

    try:
        r = requests.post(url, json=data, timeout=30)
        return r.json()

    except Exception as e:
        print("Telegram API Error:", e)
        return {}



def send_message(chat_id, text, keyboard=None):

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    telegram_api("sendMessage", data)



def bot_loop():

    print("USDT P2P Telegram Bot Started 🚀")

    last_update = 0


    while True:

        try:

            response = telegram_api(
                "getUpdates",
                {
                    "offset": last_update + 1,
                    "timeout": 30
                }
            )


            for update in response.get("result", []):

                last_update = update["update_id"]


                if "message" not in update:
                    continue


                message = update["message"]

                chat_id = message["chat"]["id"]

                text = message.get("text", "")



                if text == "/start":

                    keyboard = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "🚀 فتح منصة USDT P2P فلسطين",
                                    "web_app": {
                                        "url": WEBAPP_URL
                                    }
                                }
                            ]
                        ]
                    }


                    send_message(
                        chat_id,
                        """
🇵🇸 أهلاً بك في منصة USDT P2P فلسطين

شراء وبيع USDT بسهولة وأمان.

اضغط الزر لفتح المنصة 👇
                        """,
                        keyboard
                    )


                elif text == "/help":

                    send_message(
                        chat_id,
                        """
الأوامر:

/start فتح المنصة 🚀

/help المساعدة ℹ️
                        """
                    )


                elif text == "/id":

                    send_message(
                        chat_id,
                        f"Telegram ID الخاص بك:\n{chat_id}"
                    )


                else:

                    send_message(
                        chat_id,
                        "اكتب /start لفتح المنصة 🚀"
                    )


        except Exception as e:

            print("BOT ERROR:", e)


        time.sleep(2)



if name == "__main__":
    bot_loop()
