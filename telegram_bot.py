import requests
import time
import os


TOKEN = os.getenv("BOT_TOKEN")

WEBAPP_URL = "https://usdt-p2p-palestine-1.onrender.com/telegram_login"



def telegram_request(method, data=None):

    url = f"https://api.telegram.org/bot{TOKEN}/{method}"

    try:
        r = requests.post(
            url,
            json=data,
            timeout=30
        )
        return r.json()

    except Exception as e:
        print("Telegram Error:", e)
        return {}



def send_message(chat_id, text, keyboard=None):

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    telegram_request(
        "sendMessage",
        data
    )



def bot_loop():

    if not TOKEN:
        print("BOT_TOKEN missing")
        return


    print("Telegram Bot Started 🚀")


    last_update = 0


    while True:

        try:

            result = telegram_request(
                "getUpdates",
                {
                    "offset": last_update + 1,
                    "timeout": 30
                }
            )


            for update in result.get("result", []):

                last_update = update["update_id"]


                if "message" not in update:
                    continue


                msg = update["message"]

                chat_id = msg["chat"]["id"]

                text = msg.get("text", "")



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
                        "🇵🇸 أهلاً بك في منصة USDT P2P فلسطين\n\nاضغط لفتح التطبيق:",
                        keyboard
                    )



                elif text == "/id":

                    send_message(
                        chat_id,
                        f"Telegram ID:\n{chat_id}"
                    )



                elif text == "/help":

                    send_message(
                        chat_id,
                        "استخدم /start لفتح المنصة 🚀"
                    )



                else:

                    send_message(
                        chat_id,
                        "اكتب /start لفتح المنصة 🚀"
                    )


        except Exception as e:

            print("BOT LOOP ERROR:", e)


        time.sleep(2)



if __name__ == "__main__":
    bot_loop()
