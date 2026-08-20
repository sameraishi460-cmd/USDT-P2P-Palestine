import os
import requests
import time
import traceback

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8881823408:AAFOF1wDyMjrW7hLQAy9hwY2LvzzeddxQbk")
WEBAPP_URL = os.environ.get("TELEGRAM_WEBAPP_URL", "https://usdt-p2p-palestine-1.onrender.com")
ADMIN_ID = int(os.environ.get("TELEGRAM_ADMIN_ID", "5681774891"))


def send_message(chat_id, text, keyboard=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print("SEND ERROR:", e)


def send_admin(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": ADMIN_ID, "text": text}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print("ADMIN SEND ERROR:", e)


def get_main_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🚀 فتح منصة USDT P2P فلسطين",
                    "web_app": {"url": WEBAPP_URL}
                }
            ],
            [
                {
                    "text": "💰 محفظتي",
                    "web_app": {"url": WEBAPP_URL + "/wallet"}
                },
                {
                    "text": "📊 السوق",
                    "web_app": {"url": WEBAPP_URL + "/market"}
                }
            ],
            [
                {
                    "text": "💵 شراء USDT",
                    "web_app": {"url": WEBAPP_URL + "/market"}
                },
                {
                    "text": "💸 بيع USDT",
                    "web_app": {"url": WEBAPP_URL + "/create_ad"}
                }
            ],
            [
                {
                    "text": "📥 إيداع USDT",
                    "web_app": {"url": WEBAPP_URL + "/usdt_deposit"}
                },
                {
                    "text": "📤 سحب USDT",
                    "web_app": {"url": WEBAPP_URL + "/withdraw"}
                }
            ],
            [
                {
                    "text": "📋 صفقاتي",
                    "web_app": {"url": WEBAPP_URL + "/my_trades"}
                },
                {
                    "text": "👤 حسابي",
                    "web_app": {"url": WEBAPP_URL + "/profile"}
                }
            ],
            [
                {
                    "text": "🤖 بوت التداول",
                    "web_app": {"url": WEBAPP_URL + "/trading_bot"}
                }
            ],
            [
                {
                    "text": "🤝 مقابلة شخصية",
                    "web_app": {"url": WEBAPP_URL + "/cash_market"}
                }
            ],
            [
                {
                    "text": "🔐 دخول الإدارة",
                    "web_app": {"url": WEBAPP_URL + "/admin_login"}
                }
            ]
        ]
    }


def bot_loop():
    print("Telegram Bot Started 🚀")
    last_update = 0

    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            params = {"offset": last_update + 1, "timeout": 30}
            response = requests.get(url, params=params, timeout=40).json()

            for update in response.get("result", []):
                last_update = update["update_id"]

                if "message" not in update:
                    continue

                message = update["message"]
                chat_id = message["chat"]["id"]
                text = message.get("text", "")

                if text == "/start":
                    send_message(
                        chat_id,
                        "أهلاً بك في منصة USDT P2P فلسطين 🇵🇸\n\n"
                        "شراء وبيع USDT بسهولة وأمان 🔐\n\n"
                        "اختر الخدمة:",
                        get_main_keyboard()
                    )

                elif text == "/help":
                    send_message(
                        chat_id,
                        "📋 الأوامر المتاحة:\n\n"
                        "/start — فتح المنصة\n"
                        "/wallet — رصيد المحفظة\n"
                        "/help — المساعدة\n\n"
                        "🌐 اضغط على الزر لفتح المنصة مباشرة"
                    )

                elif text == "/wallet":
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "💰 فتح المحفظة",
                                    "web_app": {"url": WEBAPP_URL + "/wallet"}
                                }
                            ],
                            [
                                {
                                    "text": "📥 إيداع USDT",
                                    "web_app": {"url": WEBAPP_URL + "/usdt_deposit"}
                                },
                                {
                                    "text": "📤 سحب USDT",
                                    "web_app": {"url": WEBAPP_URL + "/withdraw"}
                                }
                            ]
                        ]
                    }
                    send_message(
                        chat_id,
                        "💰 محفظتك\n\n"
                        "افتح المحفظة لعرض رصيدك وإجراء المعاملات",
                        keyboard
                    )

                elif text == "/market":
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "📊 فتح السوق",
                                    "web_app": {"url": WEBAPP_URL + "/market"}
                                }
                            ]
                        ]
                    }
                    send_message(chat_id, "📊 سوق USDT\n\nتصفح أفضل العروض", keyboard)

                elif text == "/admin":
                    if chat_id == ADMIN_ID:
                        send_message(
                            chat_id,
                            "👨‍💻 لوحة الإدارة",
                            {
                                "inline_keyboard": [
                                    [
                                        {
                                            "text": "📊 لوحة الأدمن",
                                            "web_app": {"url": WEBAPP_URL + "/admin"}
                                        }
                                    ]
                                ]
                            }
                        )
                    else:
                        send_message(chat_id, "❌ غير مصرح لك")

                else:
                    send_message(
                        chat_id,
                        "استخدم /start لفتح المنصة 🚀",
                        get_main_keyboard()
                    )

        except Exception as e:
            print("Telegram Error:", e)
            traceback.print_exc()

        time.sleep(2)


if __name__ == "__main__":
    bot_loop()
