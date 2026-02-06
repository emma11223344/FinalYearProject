from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scenario = db.Column(db.String(100))

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign = db.Column(db.String(100))
    action = db.Column(db.String(50))