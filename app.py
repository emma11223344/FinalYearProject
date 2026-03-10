from flask import Flask, render_template, request, redirect, session
from modules.models import db, Campaign, Result
from collections import Counter

# Firebase
from firebase_admin import auth
import firebase_config


app = Flask(__name__)
app.secret_key = "secret-key"


# database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


# home page
@app.route("/")
def index():
    return render_template("index.html")


#login
@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    error = None

    if request.method == "POST":

        email = request.form["email"]

        try:
            #check if firebase user exists
            user = auth.get_user_by_email(email)

            session["user"] = user.uid
            session["email"] = email
            session["role"] = role

            if role == "admin":
                return redirect("/admin")
            else:
                return redirect("/employee")

        except:
            error = "Invalid email or user does not exist"

    return render_template("login.html", role=role, error=error)


#create account
@app.route("/create-account", methods=["GET", "POST"])
def create_account():
    error = None
    success = None

    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            error = "Passwords do not match"
        elif len(password) < 6:
            error = "Password must be at least 6 characters"
        else:
            try:
                auth.create_user(email=email, password=password)
                success = "Account created successfully. You can now log in."
            except Exception as e:
                message = str(e)
                if "EMAIL_EXISTS" in message:
                    error = "An account with this email already exists"
                else:
                    error = "Could not create account. Please try again."

    return render_template("create_account.html", error=error, success=success)


#logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


#admin page
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect("/login/admin")

    campaigns = Campaign.query.all()
    return render_template("admin.html", campaigns=campaigns)


#create campaign
@app.route("/create", methods=["POST"])
def create():
    if session.get("role") != "admin":
        return redirect("/login/admin")

    scenario = request.form["scenario"]

    db.session.add(Campaign(scenario=scenario))
    db.session.commit()

    return redirect("/admin")


#results page
@app.route("/results")
def results():
    if session.get("role") != "admin":
        return redirect("/login/admin")

    data = Result.query.all()
    actions = [r.action for r in data]
    summary = Counter(actions)

    return render_template("results.html", data=data, summary=summary)


#employee page
@app.route("/employee")
def employee():
    if session.get("role") != "employee":
        return redirect("/login/employee")

    campaigns = Campaign.query.all()
    return render_template("employee.html", campaigns=campaigns)


#simulations
@app.route("/simulate/<int:id>")
def simulate(id):
    if session.get("role") != "employee":
        return redirect("/login/employee")

    campaign = Campaign.query.get(id)

    if not campaign:
        return "Campaign not found"

    simulation_by_scenario = {
        "Password Reset": {
            "sender": "IT Support <support@company-it.com>",
            "recipient": session.get("email", "employee@company.com"),
            "subject": "Urgent: Password Reset Required",
            "body": [
                "Dear Employee,",
                "We detected unusual activity on your account. To secure your access, please reset your password immediately.",
                "Click the link below to complete the reset.",
            ],
            "link": "https://company-security-reset.com",
            "closing": "If you do not reset your password within 24 hours, your account may be locked.",
            "signature": "IT Support Team",
        },
        "Invoice Scam": {
            "sender": "Finance Team <invoices@finance-alerts.com>",
            "recipient": session.get("email", "employee@company.com"),
            "subject": "Outstanding Invoice - Immediate Payment Needed",
            "body": [
                "Hello,",
                "An overdue invoice has been flagged against your department.",
                "Open the secure invoice portal below and confirm payment details.",
            ],
            "link": "https://finance-verification-portal.com",
            "closing": "Failure to act today may result in account suspension.",
            "signature": "Finance Operations",
        },
        "Delivery Notice": {
            "sender": "Courier Service <delivery@track-shipping-now.com>",
            "recipient": session.get("email", "employee@company.com"),
            "subject": "Package Delivery Failed - Reschedule Required",
            "body": [
                "Hi,",
                "We attempted to deliver your package but no one was available.",
                "Use the secure tracking page below to reschedule delivery.",
            ],
            "link": "https://secure-delivery-reschedule.com",
            "closing": "Your package will be returned to sender if not rescheduled in 24 hours.",
            "signature": "Courier Dispatch",
        },
    }

    simulation = simulation_by_scenario.get(
        campaign.scenario,
        {
            "sender": "Security Team <security@company.com>",
            "recipient": session.get("email", "employee@company.com"),
            "subject": "Security Notice",
            "body": [
                "Please review this security notice.",
            ],
            "link": "https://company-security.example",
            "closing": "Contact IT if you did not request this action.",
            "signature": "Security Team",
        },
    )

    return render_template("simulate.html", campaign=campaign, simulation=simulation)


#report results
@app.route("/report", methods=["POST"])
def report():
    if session.get("role") != "employee":
        return redirect("/login/employee")

    campaign = request.form["campaign"]
    action = request.form["action"]

    db.session.add(Result(campaign=campaign, action=action))
    db.session.commit()

    return redirect("/employee")


#awareness page
@app.route("/awareness")
def awareness():
    if "role" not in session:
        return redirect("/")

    return render_template("awareness.html")


#run app
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)