from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy() #initialize SQLAlchemy to manage the database connection and operations

class Campaign(db.Model): #define the Campaign model to represent phishing campaigns in the database
    id = db.Column(db.Integer, primary_key=True)
    scenario = db.Column(db.String(100))

class Result(db.Model): #define the Result model to represent the results of phishing simulations in the database
    id = db.Column(db.Integer, primary_key=True)
    campaign = db.Column(db.String(100))
    # New: links result rows to a specific campaign ID so users cannot complete the same campaign twice.
    campaign_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(50))
    # New: stores which employee submitted the result so admin reports can show who completed it.
    employee_email = db.Column(db.String(255), nullable=True)