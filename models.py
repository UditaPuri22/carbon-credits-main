from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    credits = db.Column(db.Float, default=5.0)           # in tCO₂e
    wallet_balance = db.Column(db.Float, default=5000.0) # in ₹ (INR)


    activities = db.relationship("Activity", backref="user", lazy=True)
    emission_records = db.relationship("EmissionRecord", backref="user", lazy=True)
    offset_transactions = db.relationship("OffsetTransaction", backref="user", lazy=True)
    listings = db.relationship("MarketplaceListing", backref="user", lazy=True)

class EmissionFactor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(100), unique=True, nullable=False)
    factor = db.Column(db.Float, nullable=False)  # kg CO₂ per unit

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    #emission = db.Column(db.Float, nullable=True)           # store emission result (kg CO₂e)
    #remaining_credits = db.Column(db.Float, nullable=True)  # for dashboard consistency
    
    
class EmissionRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.Date)
    emission_value = db.Column(db.Float)

class MarketplaceListing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    credits = db.Column(db.Float, nullable=False)
    price_per_credit = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="available")  # available / sold
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    credits_transferred = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    buyer = db.relationship("User", foreign_keys=[buyer_id], backref="purchases")
    seller = db.relationship("User", foreign_keys=[seller_id], backref="sales")
    
class OffsetProgram(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    rate_per_kg = db.Column(db.Float, nullable=False)  # credits required per kg CO2
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    image = db.Column(db.String(200), nullable=True) 


class OffsetTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey("offset_program.id"), nullable=False)
    co2_offset = db.Column(db.Float, nullable=False)
    credits_used = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    program = db.relationship("OffsetProgram", backref="transactions")

