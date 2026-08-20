"""
AI Trading Engine — Notification System

Sends Telegram notifications for trading events:
- Signal generated
- Trade opened/closed
- TP/SL hit
- Daily reports
- Errors
- Risk limits

Respects user notification preferences.
"""

import os
import json
import sqlite3
import requests
from datetime import datetime


def _get_bot_token():
    """Get Telegram bot token from environment."""
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _get_chat_id(username):
    """Look up a user's Telegram chat_id from the users table."""
    try:
        con = sqlite3.connect("database.db", timeout=10)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT telegram_id FROM users WHERE username=?", (username,)
        ).fetchone()
        con.close()
        if row and row["telegram_id"]:
            return str(row["telegram_id"])
    except Exception:
        pass
    return None


def _get_preferences(username):
    """Get notification preferences for a user."""
    try:
        con = sqlite3.connect("database.db", timeout=10)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM trading_notification_prefs WHERE username=?",
            (username,),
        ).fetchone()
        con.close()
        if row:
            return dict(row)
    except Exception:
        pass
    return {
        "enabled": True,
        "daily_reports": True,
        "min_ai_score": 70,
        "notify_long": True,
        "notify_short": True,
        "notify_tp": True,
        "notify_sl": True,
        "notify_signals": True,
        "notify_errors": True,
    }


def _should_notify(username, event_type, ai_score=0, direction=""):
    """Check if notification should be sent based on preferences."""
    prefs = _get_preferences(username)

    if not prefs.get("enabled", True):
        return False

    if event_type == "daily_report" and not prefs.get("daily_reports", True):
        return False

    if event_type in ("signal", "high_quality") and ai_score < prefs.get("min_ai_score", 70):
        return False

    if direction == "LONG" and not prefs.get("notify_long", True):
        return False
    if direction == "SHORT" and not prefs.get("notify_short", True):
        return False

    if event_type in ("tp_hit", "tp1_reached") and not prefs.get("notify_tp", True):
        return False

    if event_type == "sl_hit" and not prefs.get("notify_sl", True):
        return False

    if event_type in ("signal", "high_quality") and not prefs.get("notify_signals", True):
        return False

    if event_type.startswith("error") and not prefs.get("notify_errors", True):
        return False

    return True


def send_telegram(chat_id, text, parse_mode="HTML"):
    """Send a Telegram message."""
    token = _get_bot_token()
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def notify_signal(username, signal_data):
    """Notify when a high-quality signal is generated."""
    if not _should_notify(username, "signal",
                          ai_score=signal_data.get("ai_score", 0),
                          direction=signal_data.get("direction", "")):
        return False

    chat_id = _get_chat_id(username)
    direction = signal_data.get("direction", "?")
    symbol = signal_data.get("symbol", "?")
    ai_score = signal_data.get("ai_score", 0)
    regime = signal_data.get("regime", "")
    entry = signal_data.get("entry_price", 0)
    sl = signal_data.get("stop_loss", 0)
    tp1 = signal_data.get("take_profit1", 0)
    rr = signal_data.get("rr_ratio", 0)
    grade = signal_data.get("quality", {}).get("grade", "?")
    executed = signal_data.get("executed", False)

    emoji = "🟢" if direction == "LONG" else "🔴"
    exec_text = "✅ تم التنفيذ" if executed else "⏸️ لم يتم التنفيذ"

    text = (
        f"{emoji} <b>إشارة AI</b> — {symbol}\n\n"
        f"📊 الاتجاه: <b>{direction}</b>\n"
        f"🤖 نقاط AI: <b>{ai_score:.0f}/100</b> ({grade})\n"
        f"📈 السوق: {regime}\n\n"
        f"💰 السعر: {entry:.2f}\n"
        f"🛑 وقف الخسارة: {sl:.2f}\n"
        f"🎯 جني الأرباح: {tp1:.2f}\n"
        f"⚖️ Risk/Reward: 1:{rr:.1f}\n\n"
        f"📌 الحالة: {exec_text}"
    )
    return send_telegram(chat_id, text)


def notify_trade_opened(username, trade_data):
    """Notify when a trade is opened."""
    if not _should_notify(username, "trade_opened",
                          direction=trade_data.get("side", "")):
        return False

    chat_id = _get_chat_id(username)
    side = trade_data.get("side", "?")
    symbol = trade_data.get("symbol", "?")
    qty = trade_data.get("quantity", 0)
    entry = trade_data.get("entry_price", 0)
    sl = trade_data.get("stop_loss", 0)
    tp1 = trade_data.get("take_profit1", 0)
    ai_score = trade_data.get("ai_score", 0)

    emoji = "🟢" if side == "LONG" else "🔴"

    text = (
        f"{emoji} <b>صفقة جديدة مفتوحة</b>\n\n"
        f"📊 الزجاج: {symbol}\n"
        f"📌 الاتجاه: <b>{side}</b>\n"
        f"💰 الكمية: {qty:.6f}\n"
        f"💵 سعر الدخول: {entry:.2f}\n"
        f"🛑 وقف الخسارة: {sl:.2f}\n"
        f"🎯 جني الأرباح: {tp1:.2f}\n"
        f"🤖 نقاط AI: {ai_score:.0f}/100\n"
        f"🧪 وضعي: ورقي فقط"
    )
    return send_telegram(chat_id, text)


def notify_tp_reached(username, data):
    """Notify when take profit is reached."""
    if not _should_notify(username, "tp_hit", direction=data.get("side", "")):
        return False

    chat_id = _get_chat_id(username)
    tp_level = data.get("tp_level", "TP")
    symbol = data.get("symbol", "?")
    side = data.get("side", "?")
    pnl = data.get("pnl", 0)
    price = data.get("price", 0)

    text = (
        f"🎯 <b>{tp_level} تم الوصول!</b>\n\n"
        f"📊 الزجاج: {symbol}\n"
        f"📌 الاتجاه: {side}\n"
        f"💰 السعر: {price:.2f}\n"
        f"💵 الأرباح: ${pnl:.2f}\n"
        f"🧪 وضعي: ورقي فقط"
    )
    return send_telegram(chat_id, text)


def notify_sl_hit(username, data):
    """Notify when stop loss is hit."""
    if not _should_notify(username, "sl_hit", direction=data.get("side", "")):
        return False

    chat_id = _get_chat_id(username)
    symbol = data.get("symbol", "?")
    side = data.get("side", "?")
    loss = data.get("pnl", 0)
    price = data.get("price", 0)

    text = (
        f"🛑 <b>وقف الخسارة تم!</b>\n\n"
        f"📊 الزجاج: {symbol}\n"
        f"📌 الاتجاه: {side}\n"
        f"💰 السعر: {price:.2f}\n"
        f"💸 الخسارة: ${loss:.2f}\n"
        f"🧪 وضعي: ورقي فقط"
    )
    return send_telegram(chat_id, text)


def notify_trade_closed(username, data):
    """Notify when a trade is fully closed."""
    chat_id = _get_chat_id(username)
    symbol = data.get("symbol", "?")
    side = data.get("side", "?")
    net_pnl = data.get("net_pnl", 0)
    reason = data.get("exit_reason", "?")
    holding = data.get("holding_periods", 0)
    ai_score = data.get("ai_score", 0)

    emoji = "✅" if net_pnl > 0 else "❌"

    text = (
        f"{emoji} <b>صفقة مغلقة</b>\n\n"
        f"📊 الزجاج: {symbol}\n"
        f"📌 الاتجاه: {side}\n"
        f"💵 صافي الربح/الخسارة: <b>${net_pnl:.2f}</b>\n"
        f"📝 السبب: {reason}\n"
        f"⏱️ مدة الاحتفاظ: {holding} شمعة\n"
        f"🤖 نقاط AI عند الدخول: {ai_score:.0f}\n"
        f"🧪 وضعي: ورقي فقط"
    )
    return send_telegram(chat_id, text)


def notify_daily_report(username, stats, bot_status):
    """Send daily performance report."""
    if not _should_notify(username, "daily_report"):
        return False

    chat_id = _get_chat_id(username)
    if not chat_id:
        return False

    bot = bot_status.get("bot", {})
    equity = bot.get("equity", 10000) if bot else 10000
    capital = bot.get("starting_equity", 10000) if bot else 10000
    pnl = equity - capital
    roi = (pnl / capital * 100) if capital > 0 else 0

    today_pnl = bot.get("today_pnl", 0) if bot else 0

    text = (
        f"📊 <b>تقرير يومي — AI Trading</b>\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"💰رأس المال: ${equity:.2f}\n"
        f"📈 الأرباح اليوم: <b>${today_pnl:.2f}</b>\n"
        f"📈 إجمالي الأرباح: <b>${pnl:.2f} ({roi:.1f}%)</b>\n\n"
        f"📋 الصفقات: {stats.get('total_trades', 0)}\n"
        f"✅ انتصارات: {stats.get('wins', 0)} ({stats.get('win_rate', 0):.1f}%)\n"
        f"❌ خسائر: {stats.get('losses', 0)}\n"
        f"📊 عامل الربح: {stats.get('profit_factor', 0):.2f}\n\n"
        f"🧪 وضعي: ورقي فقط — لا أموال حقيقية"
    )
    return send_telegram(chat_id, text)


def notify_error(username, error_type, message):
    """Notify about bot errors."""
    if not _should_notify(username, f"error_{error_type}"):
        return False

    chat_id = _get_chat_id(username)

    text = (
        f"⚠️ <b>خطأ في البوت</b>\n\n"
        f"📝 النوع: {error_type}\n"
        f"💬 الرسالة: {message}\n"
        f"⏰ الوقت: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🧪 وضعي: ورقي فقط"
    )
    return send_telegram(chat_id, text)


def notify_emergency_stop(username, positions_closed):
    """Notify about emergency stop."""
    chat_id = _get_chat_id(username)

    text = (
        f"🚨 <b>إيقاف طوارئ!</b>\n\n"
        f"تم إغلاق جميع الصفقات المفتوحة: {positions_closed}\n"
        f"⏰ الوقت: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🧪 وضعي: ورقي فقط"
    )
    return send_telegram(chat_id, text)


def notify_risk_limit(username, reason):
    """Notify about risk limit reached."""
    if not _should_notify(username, "risk_limit"):
        return False

    chat_id = _get_chat_id(username)

    text = (
        f"🛑 <b>تم الوصول لحد المخاطرة</b>\n\n"
        f"📝 السبب: {reason}\n"
        f"⏰ الوقت: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"البوت سيتوقف مؤقتاً عن فتح صفقات جديدة.\n"
        f"🧪 وضعي: ورقي فقط"
    )
    return send_telegram(chat_id, text)


def notify_model_failure(username, reason):
    """Notify about ML model failure."""
    if not _should_notify(username, "error_model"):
        return False

    chat_id = _get_chat_id(username)

    text = (
        f"🧠 <b>فشل نموذج ML</b>\n\n"
        f"📝 السبب: {reason}\n"
        f"⏰ الوقت: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"النظام ي退回 للتحليل الفني فقط.\n"
        f"🧪 وضعي: ورقي فقط"
    )
    return send_telegram(chat_id, text)


# ============================================================
# NOTIFICATION PREFERENCES HELPERS
# ============================================================

def create_notification_prefs_table(con):
    """Create notification preferences table if not exists."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS trading_notification_prefs (
            username TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            daily_reports INTEGER DEFAULT 1,
            min_ai_score REAL DEFAULT 70,
            notify_long INTEGER DEFAULT 1,
            notify_short INTEGER DEFAULT 1,
            notify_tp INTEGER DEFAULT 1,
            notify_sl INTEGER DEFAULT 1,
            notify_signals INTEGER DEFAULT 1,
            notify_errors INTEGER DEFAULT 1,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()


def get_notification_prefs(con, username):
    """Get notification preferences for a user."""
    old_factory = con.row_factory
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM trading_notification_prefs WHERE username=?",
        (username,),
    ).fetchone()
    con.row_factory = old_factory
    if row:
        return dict(row)
    return {
        "enabled": 1,
        "daily_reports": 1,
        "min_ai_score": 70,
        "notify_long": 1,
        "notify_short": 1,
        "notify_tp": 1,
        "notify_sl": 1,
        "notify_signals": 1,
        "notify_errors": 1,
    }


def save_notification_prefs(con, username, prefs):
    """Save notification preferences."""
    con.execute("""
        INSERT OR REPLACE INTO trading_notification_prefs
        (username, enabled, daily_reports, min_ai_score,
         notify_long, notify_short, notify_tp, notify_sl,
         notify_signals, notify_errors, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        username,
        1 if prefs.get("enabled", True) else 0,
        1 if prefs.get("daily_reports", True) else 0,
        prefs.get("min_ai_score", 70),
        1 if prefs.get("notify_long", True) else 0,
        1 if prefs.get("notify_short", True) else 0,
        1 if prefs.get("notify_tp", True) else 0,
        1 if prefs.get("notify_sl", True) else 0,
        1 if prefs.get("notify_signals", True) else 0,
        1 if prefs.get("notify_errors", True) else 0,
    ))
    con.commit()
