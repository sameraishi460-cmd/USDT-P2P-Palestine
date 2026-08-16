import requests
import time
import traceback
import os


# ===============================
# CONFIG
# ===============================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

WEBAPP_URL = "https://usdt-p2p-palestine-1.onrender.com"

ADMIN_ID = 5681774891


# ===============================
# SEND MESSAGE
# ===============================

def send_message(chat_id, text, keyboard=None):

    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    try:

        requests.post(
            url,
            json=data,
            timeout=10
        )

    except Exception as e:

        print("SEND ERROR:", e)


# ===============================
# SEND ADMIN
# ===============================

def send_admin(text):

    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": ADMIN_ID,
        "text": text
    }

    try:

        requests.post(
            url,
            json=data,
            timeout=10
        )

    except Exception as e:

        print("ADMIN SEND ERROR:", e)


# ===============================
# TELEGRAM BOT
# ===============================

def bot_loop():

    print("Telegram Bot Started 🚀")

    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN is missing")
        return

    last_update = 0

    while True:

        try:

            url = (
                f"https://api.telegram.org/"
                f"bot{TOKEN}/getUpdates"
            )

            params = {
                "offset": last_update + 1,
                "timeout": 30
            }

            response = requests.get(
                url,
                params=params,
                timeout=40
            ).json()

            for update in response.get("result", []):

                last_update = update["update_id"]

                if "message" not in update:
                    continue

                message = update["message"]

                chat_id = message["chat"]["id"]

                text = message.get("text", "")


                # ===============================
                # START
                # ===============================

                if text == "/start":

                    keyboard = {

                        "inline_keyboard": [

                            [

                                {
                                    "text":
                                    "🚀 فتح منصة USDT P2P فلسطين",

                                    "web_app": {
                                        "url": WEBAPP_URL
                                    }
                                }

                            ],

                            [

                                {
                                    "text":
                                    "🤖 Trading Bot",

                                    "web_app": {
                                        "url":
                                        WEBAPP_URL +
                                        "/trading_bot"
                                    }
                                }

                            ],

                            [

                                {
                                    "text":
                                    "🔐 دخول الإدارة",

                                    "web_app": {
                                        "url":
                                        WEBAPP_URL +
                                        "/admin_login"
                                    }
                                }

                            ]

                        ]

                    }

                    send_message(

                        chat_id,

                        "أهلاً بك في منصة USDT P2P فلسطين 🇵🇸\n\n"
                        "اختر الخدمة:",

                        keyboard
                    )


                # ===============================
                # HELP
                # ===============================

                elif text == "/help":

                    send_message(

                        chat_id,

                        "استخدم /start لفتح المنصة 🚀"
                    )


                # ===============================
                # ADMIN
                # ===============================

                elif text == "/admin":

                    if chat_id == ADMIN_ID:

                        send_message(

                            chat_id,

                            "👨‍💻 أنت الأدمن\n\n"
                            "لوحة الإدارة:",

                            {
                                "inline_keyboard": [

                                    [

                                        {
                                            "text":
                                            "فتح لوحة الأدمن",

                                            "web_app": {
                                                "url":
                                                WEBAPP_URL +
                                                "/admin_login"
                                            }
                                        }

                                    ]

                                ]
                            }
                        )

                    else:

                        send_message(

                            chat_id,

                            "❌ غير مصرح لك"
                        )


                # ===============================
                # UNKNOWN COMMAND
                # ===============================

                else:

                    send_message(

                        chat_id,

                        "استخدم /start لفتح التطبيق 🚀"
                    )


        except Exception as e:

            print(
                "Telegram Error:",
                e
            )

            traceback.print_exc()


        time.sleep(2)


# ===============================
# RUN
# ===============================

if __name__ == "__main__":

    bot_loop()
