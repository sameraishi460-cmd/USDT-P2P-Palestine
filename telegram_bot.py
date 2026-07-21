import requests
import time


TOKEN = "8881823408:AAFOF1wDyMjrW7hLQAy9hwY2LvzzeddxQbk"

WEBAPP_URL = "https://usdt-p2p-palestine-1.onrender.com/"


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

    print("Bot started...")


    while True:

        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

        params = {
            "offset": last_update + 1,
            "timeout": 30
        }

        try:

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
                            "أهلاً بك في منصة USDT P2P فلسطين 🇵🇸\n\nاضغط الزر لفتح التطبيق:",
                            keyboard
                        )


                    else:

                        send_message(
                            chat_id,
                            "اكتب /start لفتح التطبيق 🚀"
                        )


        except Exception as e:

            print(e)


        time.sleep(2)



if __name__ == "__main__":
    bot_loop()
