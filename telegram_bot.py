import requests
import time


TOKEN = "8881823408:AAFOF1wDyMjrW7hLQAy9hwY2LvzzeddxQbk"

WEBAPP_URL = "https://usdt-p2p-palestine-1.onrender.com/telegram_login"


def send_message(chat_id, text, keyboard=None):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    requests.post(url, json=data)



def bot_loop():

    last_update = 0

    print("Telegram Bot Started")


    while True:

        try:

            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

            params = {
                "offset": last_update + 1,
                "timeout": 30
            }

            response = requests.get(
                url,
                params=params
            ).json()


            for update in response.get("result", []):

                last_update = update["update_id"]


                if "message" in update:

                    message = update["message"]

                    chat_id = message["chat"]["id"]

                    text = message.get("text", "")


                    if text == "/start":

                        keyboard = {
                            "inline_keyboard": [
                                [
                                    {
                                        "text": "🚀 فتح منصة USDT P2P",
                                        "web_app": {
                                            "url": WEBAPP_URL
                                        }
                                    }
                                ]
                            ]
                        }


                        send_message(
                            chat_id,
                            "أهلاً بك في منصة USDT P2P فلسطين 🇵🇸\n\nاضغط لفتح التطبيق:",
                            keyboard
                        )


                    elif text == "/help":

                        send_message(
                            chat_id,
                            "اكتب /start لفتح المنصة 🚀"
                        )


                    else:

                        send_message(
                            chat_id,
                            "استخدم /start لفتح التطبيق 🚀"
                        )


        except Exception as e:

            print("BOT ERROR:", e)


        time.sleep(2)



if __name__ == "__main__":
    bot_loop()
