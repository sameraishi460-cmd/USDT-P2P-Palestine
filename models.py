from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# المستخدمين
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(50), unique=True)
    email = db.Column(db.String(120), unique=True)

    verified = db.Column(db.Boolean, default=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


# محافظ المستخدمين
class Wallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id')
    )

    balance = db.Column(
        db.Float,
        default=0
    )

    locked_balance = db.Column(
        db.Float,
        default=0
    )


# إعلانات البيع والشراء
class Ad(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    seller_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id')
    )

    amount = db.Column(
        db.Float
    )

    price = db.Column(
        db.Float
    )

    payment_method = db.Column(
        db.String(100)
    )

    status = db.Column(
        db.String(20),
        default="active"
    )


# الطلبات
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id')
    )

    seller_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id')
    )

    amount = db.Column(
        db.Float
    )

    total_price = db.Column(
        db.Float
    )

    status = db.Column(
        db.String(30),
        default="waiting_payment"
    )


# عمولات المنصة
class Fee(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    order_id = db.Column(
        db.Integer,
        db.ForeignKey('order.id')
    )

    amount = db.Column(
        db.Float
    )
