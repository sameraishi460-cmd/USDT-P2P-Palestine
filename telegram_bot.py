import requests
import time
import traceback


TOKEN = "8881823408:AAFOF1wDyMjrW7hLQAy9hwY2LvzzeddxQbk"

WEBAPP_URL = "https://usdt-p2p-palestine-1.onrender.com"


def send_message(chat_id, text, keyboard=None):

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



def bot_loop():

    print("Telegram Bot Started 🚀")

    last_update = 0


    while True:

        try:

            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"


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

                text = message.get("text","")



                if text == "/start":


                    keyboard = {

                        "inline_keyboard":[


                            [

                                {
                                    "text":"🚀 فتح منصة USDT P2P فلسطين",

                                    "web_app":{

                                        "url": WEBAPP_URL

                                    }

                                }

                            ],


                            [

                                {
                                    "text":"🔐 دخول الإدارة",

                                    "web_app":{

                                        "url": WEBAPP_URL + "/admin_login"

                                    }

                                }

                            ]


                        ]

                    }



                    send_message(

                        chat_id,

                        "أهلاً بك في منصة USDT P2P فلسطين 🇵🇸\n\nاختر الخدمة:",

                        keyboard

                    )




                elif text == "/help":


                    send_message(

                        chat_id,

                        "استخدم /start لفتح المنصة 🚀"

                    )




                else:


                    send_message(

                        chat_id,

                        "استخدم /start لفتح التطبيق 🚀"

                    )



        except Exception as e:

            print("Telegram Error:", e)

            traceback.print_exc()



        time.sleep(2)




if __name__ == "__main__":

    bot_loop()
