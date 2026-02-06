from flask import Flask, render_template, request, redirect
from modules.models import db, Campaign, Result
from collections import Counter

app = Flask(__name__)

# Configure SQLite database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# ---------- HOME ----------
@app.route("/")
def index():
    return render_template("index.html")

# ---------- ADMIN ----------
@app.route("/admin")
def admin():
    campaigns = Campaign.query.all()
    return render_template("admin.html", campaigns=campaigns)

@app.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        scenario = request.form["scenario"]
        db.session.add(Campaign(scenario=scenario))
        db.session.commit()
        return redirect("/admin")
    return render_template("create_campaign.html")

@app.route("/results")
def results():
    data = Result.query.all()
    actions = [r.action for r in data]
    summary = Counter(actions)
    return render_template("results.html", data=data, summary=summary)

# ---------- EMPLOYEE ----------
@app.route("/employee")
def employee():
    campaigns = Campaign.query.all()
    return render_template("employee.html", campaigns=campaigns)

@app.route("/simulate/<int:id>")
def simulate(id):
    campaign = Campaign.query.get(id)
    if campaign is None:
        return "Campaign not found"
    return render_template("simulate.html", campaign=campaign)

@app.route("/report", methods=["POST"])
def report():
    campaign = request.form["campaign"]
    action = request.form["action"]
    db.session.add(Result(campaign=campaign, action=action))
    db.session.commit()
    return redirect("/employee")

# ---------- AWARENESS ----------
@app.route("/awareness")
def awareness():
    return render_template("awareness.html")

# ---------- TEST ROUTE (optional) ----------
@app.route("/test")
def test():
    return "Flask is working!"

# ---------- RUN APP ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create database tables if they don't exist
    app.run(debug=True)