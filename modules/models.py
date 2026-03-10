from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy() #initialize SQLAlchemy to manage the database connection and operations

class Campaign(db.Model): #define the Campaign model to represent phishing campaigns in the database
    id = db.Column(db.Integer, primary_key=True)
    scenario = db.Column(db.String(100))

class Result(db.Model): #define the Result model to represent the results of phishing simulations in the database
    id = db.Column(db.Integer, primary_key=True)
    campaign = db.Column(db.String(100))
    action = db.Column(db.String(50))