from flask import Flask, render_template, request, redirect, session
from modules.models import db, Campaign, Result
from modules.report_generator import generate_campaign_report
from collections import Counter
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text

#firebase
from firebase_admin import auth, firestore
import firebase_config


app = Flask(__name__)
#set secret key for session management
app.secret_key = "secret-key"
# Firestore is used for profile metadata (role + password hash) while Firebase Auth stores identity records.
firestore_db = firestore.client()


#database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
#disable modification tracking to save resources
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["REPORTS_DIR"] = "instance/reports"
#initialize the database with the Flask app
db.init_app(app)
_db_initialized = False


def ensure_result_email_column():
    # Backward-compatible DB migration for the new employee email field in Result.
    inspector = inspect(db.engine)
    result_columns = {column["name"] for column in inspector.get_columns("result")}

    if "employee_email" not in result_columns:
        db.session.execute(text("ALTER TABLE result ADD COLUMN employee_email VARCHAR(255)"))
        db.session.commit()


def ensure_result_campaign_id_column():
    # Backward-compatible DB migration for campaign_id, used to lock each campaign to one completion per employee.
    inspector = inspect(db.engine)
    result_columns = {column["name"] for column in inspector.get_columns("result")}

    if "campaign_id" not in result_columns:
        db.session.execute(text("ALTER TABLE result ADD COLUMN campaign_id INTEGER"))
        db.session.commit()


def initialize_database():
    global _db_initialized
    if _db_initialized:
        return

    with app.app_context():
        db.create_all()
        # Run lightweight schema upgrades for existing local SQLite databases.
        ensure_result_email_column()
        ensure_result_campaign_id_column()

    _db_initialized = True


@app.before_request
def ensure_database_ready():
    initialize_database()

#simulation builder with scenarios red flags, and risk levels for simulations
def build_simulation_payload(scenario, recipient_email, recipient_name):
    simulation_by_scenario = {
        "Password Reset": {
            "sender": "IT Support <support@company-it.com>",
            "reply_to": "security-alerts@company-helpdesk.net",
            "recipient": recipient_email,
            "subject": "Urgent: Password Reset Required",
            "received_time": "08:14 AM",
            "display_link": "https://intranet.company.com/reset",
            "attachment": None,
            "risk_level": "High",
            "body": [
                f"Dear {recipient_name},",
                "We detected unusual activity on your account. To secure your access, please reset your password immediately.",
                "Click the link below to complete the reset.",
            ],
            "closing": "If you do not reset your password within 24 hours, your account may be locked.",
            "signature": "IT Support Team",
        },
        "Invoice Scam": {
            "sender": "Finance Team <invoices@finance-alerts.com>",
            "reply_to": "payments@finance-alerts-payments.com",
            "recipient": recipient_email,
            "subject": "Outstanding Invoice - Immediate Payment Needed",
            "received_time": "10:47 AM",
            "display_link": "https://finance.company.com/invoices",
            "attachment": "Invoice_Overdue_88421.zip",
            "risk_level": "High",
            "body": [
                "Hello,",
                "An overdue invoice has been flagged against your department.",
                "Open the secure invoice portal below and confirm payment details.",
            ],
            "closing": "Failure to act today may result in account suspension.",
            "signature": "Finance Operations",
        },
        "Delivery Notice": {
            "sender": "Courier Service <delivery@track-shipping-now.com>",
            "reply_to": "noreply@courier-notices.net",
            "recipient": recipient_email,
            "subject": "Package Delivery Failed - Reschedule Required",
            "received_time": "07:52 AM",
            "display_link": "https://courier.example.com/track",
            "attachment": None,
            "risk_level": "Medium",
            "body": [
                "Hi,",
                "We attempted to deliver your package but no one was available.",
                "Use the secure tracking page below to reschedule delivery.",
            ],
            "closing": "Your package will be returned to sender if not rescheduled in 24 hours.",
            "signature": "Courier Dispatch",
        },
        "MFA Expiration": {
            "sender": "Identity Team <identity@company-security.com>",
            "reply_to": "auth-refresh@company-security-login.net",
            "recipient": recipient_email,
            "subject": "Action Needed: MFA Session Expires Today",
            "received_time": "09:06 AM",
            "display_link": "https://sso.company.com/mfa",
            "attachment": None,
            "risk_level": "High",
            "body": [
                f"Hi {recipient_name},",
                "Our records show your MFA session is no longer trusted.",
                "Re-verify now to avoid automatic sign-out from all company tools.",
            ],
            "closing": "If not completed by 5:00 PM, access to internal systems may be interrupted.",
            "signature": "Identity Assurance Team",
        },
        "Shared Document": {
            "sender": "Microsoft Share <noreply@sharepoint-docs.com>",
            "reply_to": "collab@shared-docs-mail.net",
            "recipient": recipient_email,
            "subject": "New Shared File: Compensation_Review.xlsx",
            "received_time": "11:18 AM",
            "display_link": "https://sharepoint.company.com/sites/hr",
            "attachment": None,
            "risk_level": "Medium",
            "body": [
                "You have been tagged in a confidential document.",
                "Open the file below and confirm that your compensation details are accurate.",
            ],
            "closing": "Your manager expects acknowledgement before noon.",
            "signature": "Document Collaboration Service",
        },
        "HR Policy Update": {
            "sender": "HR Team <hr@company-people.com>",
            "reply_to": "policy-signoff@company-hrforms.net",
            "recipient": recipient_email,
            "subject": "Required: New Remote Work Policy Sign-off",
            "received_time": "03:24 PM",
            "display_link": "https://hr.company.com/policies",
            "attachment": "Remote_Work_Policy_2026.docm",
            "risk_level": "High",
            "body": [
                "A mandatory remote working policy update has been issued.",
                "Please open and sign the attached document before end of day.",
            ],
            "closing": "Failure to complete this step may affect payroll processing.",
            "signature": "Human Resources",
        },
        "CEO Wire Request": {
            "sender": "CEO Office <ceo.office@executive-mail.co>",
            "reply_to": "ceo.private@proton-fastmail.com",
            "recipient": recipient_email,
            "subject": "Confidential: Immediate Vendor Transfer Needed",
            "received_time": "06:42 AM",
            "display_link": "https://finance.company.com/approvals",
            "attachment": "Wire_Instructions.pdf",
            "risk_level": "Critical",
            "body": [
                f"{recipient_name}, I need this handled before the board call.",
                "Initiate the attached vendor transfer and reply once complete.",
                "Do not discuss with others until this is finished.",
            ],
            "closing": "This is highly time-sensitive and must be completed in the next 20 minutes.",
            "signature": "CEO Office",
        },
        "Benefits Enrollment": {
            "sender": "Benefits Center <benefits@company-benefits.org>",
            "reply_to": "enrollment@benefits-secure-now.net",
            "recipient": recipient_email,
            "subject": "Final Reminder: Benefits Enrollment Window Closing",
            "received_time": "01:09 PM",
            "display_link": "https://benefits.company.com/enroll",
            "attachment": None,
            "risk_level": "Medium",
            "body": [
                "Your health and pension enrollment appears incomplete.",
                "Use the secure portal below to verify your details and prevent coverage disruption.",
            ],
            "closing": "You may lose selected benefits if not completed today.",
            "signature": "Employee Benefits Desk",
        },
        "Team Lunch Invite": {
            "sender": "People Team <people@company.com>",
            "reply_to": "people@company.com",
            "recipient": recipient_email,
            "subject": "Team Lunch This Friday",
            "received_time": "12:05 PM",
            "display_link": "https://intranet.company.com/events/lunch",
            "attachment": None,
            "risk_level": "Low",
            "red_flags": [],
            "body": [
                f"Hi {recipient_name},",
                "You are invited to the monthly team lunch this Friday at 1:00 PM.",
                "Use the intranet event page below to RSVP if you can attend.",
            ],
            "closing": "Please RSVP by Thursday so catering can be confirmed.",
            "signature": "People Team",
        },
        "IT Maintenance Notice": {
            "sender": "IT Operations <it-ops@company.com>",
            "reply_to": "it-ops@company.com",
            "recipient": recipient_email,
            "subject": "Scheduled Maintenance Tonight",
            "received_time": "04:35 PM",
            "display_link": "https://status.company.com/maintenance",
            "attachment": None,
            "risk_level": "Info",
            "body": [
                "This is a planned maintenance notification for internal systems.",
                "Some services may be temporarily unavailable between 10:00 PM and 11:00 PM.",
                "You can track real-time updates using the status page link below.",
            ],
            "closing": "No action is required from you at this time.",
            "signature": "IT Operations",
        },
        "Quarterly Town Hall": {
            "sender": "Internal Communications <comms@company.com>",
            "reply_to": "comms@company.com",
            "recipient": recipient_email,
            "subject": "Q2 Town Hall Agenda and Stream Link",
            "received_time": "09:22 AM",
            "display_link": "https://intranet.company.com/townhall",
            "attachment": "Q2_TownHall_Agenda.pdf",
            "risk_level": "Low",
            "red_flags": [],
            "body": [
                "The quarterly town hall will begin at 3:00 PM on Wednesday.",
                "Please review the agenda and join using the official stream link.",
            ],
            "closing": "A recording will be posted afterward for anyone unable to attend live.",
            "signature": "Internal Communications",
        },
        "Training Reminder": {
            "sender": "Learning Portal <learning@company.com>",
            "reply_to": "learning@company.com",
            "recipient": recipient_email,
            "subject": "Reminder: Complete Data Privacy Refresher",
            "received_time": "02:11 PM",
            "display_link": "https://learning.company.com/courses/privacy-refresh",
            "attachment": None,
            "risk_level": "Info",
            "red_flags": [],
            "body": [
                "Your annual data privacy refresher course is now available.",
                "Please complete the module before the end of the month.",
            ],
            "closing": "Reach out to Learning Support if you have trouble accessing the module.",
            "signature": "Learning and Development",
        },
        "Security Patch Advisory": {
            "sender": "IT Security <security-notices@company.com>",
            "reply_to": "security-notices@company.com",
            "recipient": recipient_email,
            "subject": "Approved Browser Security Patch Available",
            "received_time": "08:41 AM",
            "display_link": "https://intranet.company.com/patches/browser",
            "attachment": None,
            "risk_level": "Info",
            "body": [
                "A new approved browser security patch is now available for managed devices.",
                "Please review deployment notes and install before Friday if your team has not auto-updated yet.",
            ],
            "closing": "Contact the service desk only if the update fails after restart.",
            "signature": "IT Security",
        },
        "Facilities Access Notice": {
            "sender": "Facilities Team <facilities@company.com>",
            "reply_to": "facilities@company.com",
            "recipient": recipient_email,
            "subject": "Building Access Schedule for Weekend Work",
            "received_time": "05:12 PM",
            "display_link": "https://intranet.company.com/facilities/access",
            "attachment": None,
            "risk_level": "Low",
            "red_flags": [],
            "body": [
                "If you plan to work on-site this weekend, please confirm your access window using the facilities portal.",
                "The schedule helps security and reception prepare badge support.",
            ],
            "closing": "No action is needed if you are not attending the office this weekend.",
            "signature": "Facilities Management",
        },
        "Project Kickoff Invite": {
            "sender": "Program Office <program.office@company.com>",
            "reply_to": "program.office@company.com",
            "recipient": recipient_email,
            "subject": "Invitation: Q3 Project Kickoff Workshop",
            "received_time": "10:03 AM",
            "display_link": "https://intranet.company.com/projects/q3-kickoff",
            "attachment": "Q3_Kickoff_Agenda.pdf",
            "risk_level": "Low",
            "body": [
                "You have been invited to the Q3 cross-team kickoff workshop.",
                "Review the draft agenda and confirm your attendance in the project space.",
            ],
            "closing": "Please respond by Wednesday to finalize room capacity.",
            "signature": "Program Management Office",
        },
        "Payroll Schedule Update": {
            "sender": "Payroll Team <payroll@company.com>",
            "reply_to": "payroll@company.com",
            "recipient": recipient_email,
            "subject": "Payroll Processing Calendar for Next Month",
            "received_time": "01:36 PM",
            "display_link": "https://hr.company.com/payroll/calendar",
            "attachment": None,
            "risk_level": "Info",
            "body": [
                "The payroll processing dates for next month have been published.",
                "Please review key submission deadlines for overtime and expense claims.",
            ],
            "closing": "No acknowledgement is required unless your department has an exception.",
            "signature": "Payroll Operations",
        },
    }

    return simulation_by_scenario.get(
        scenario,
        {
            "sender": "Security Team <security@company.com>",
            "reply_to": "security@company.com",
            "recipient": recipient_email,
            "subject": "Security Notice",
            "received_time": "09:00 AM",
            "display_link": "https://company-security.example",
            "attachment": None,
            "risk_level": "Info",
            "body": [
                "Please review this security notice.",
            ],
            "closing": "Contact IT if you did not request this action.",
            "signature": "Security Team",
        },
    )


def simulation_requires_sensitive_input(simulation):
    #mismatched destination links or flagged content as phishing-like interactions.
    return simulation.get("display_link") != simulation.get("link") or bool(simulation.get("red_flags"))


#home page
@app.route("/")
def index():
    return render_template("index.html")


#login
@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    error = None
    role = role.strip().lower()
    # Role-specific login pages are enforced to keep admin/employee flows separated.
    if role not in ("admin", "employee"):
        return redirect("/")

    # Handle login form submission and verify Firebase identity + Firestore profile.
    if request.method == "POST":
        # Normalize email so lookups and stored profile keys stay consistent.
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        try:
            #check if the Firebase user exists first.
            user = auth.get_user_by_email(email)
            profile_doc = firestore_db.collection("users").document(user.uid).get()
            # Every Firebase auth account must have a matching Firestore profile document.
            if not profile_doc.exists:
                error = "Account profile not found. Please contact support."
                
                return render_template("login.html", role=role, error=error)

            #read role and password hash used for role-aware login validation.
            profile = profile_doc.to_dict() or {}
            stored_password_hash = profile.get("password_hash", "")
            stored_role = (profile.get("role") or "").strip().lower()

            #validate password against the stored hash written during account creation.
            if not stored_password_hash or not check_password_hash(stored_password_hash, password):
                error = "Invalid email or password"
                return render_template("login.html", role=role, error=error)

            #prevent users from entering through the wrong role portal.
            if stored_role != role:
                error = f"This account is registered as {stored_role or 'unknown'}. Use the correct login page."
                return render_template("login.html", role=role, error=error)

            #role and identity in session for route access checks
            session["user"] = user.uid
            session["email"] = email
            session["role"] = stored_role

            #route user to the correct dashboard immediately after successful login
            if stored_role == "admin":
                return redirect("/admin")
            else:
                return redirect("/employee")
        
        except:
            error = "Invalid email or password"

    return render_template("login.html", role=role, error=error)


#create account
@app.route("/create-account", methods=["GET", "POST"])
def create_account():
    error = None
    success = None
    selected_role = "employee"

    #explicit role selection and password
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        selected_role = request.form.get("role", "employee").strip().lower()

        #validate role and password requirements before creating the Firebase account
        if selected_role not in ("admin", "employee"):
            error = "Please select a valid account role"
        elif password != confirm_password:
            error = "Passwords do not match"
        elif len(password) < 6:
            error = "Password must be at least 6 characters"
        else:
            try:
                user = auth.create_user(email=email, password=password)
                #store role + password firestore so login can enforce role and verify credential
                firestore_db.collection("users").document(user.uid).set(
                    {
                        "email": email,
                        "role": selected_role,
                        "password_hash": generate_password_hash(password),
                    }
                )
                
                success = f"{selected_role.capitalize()} account created successfully. You can now log in."
            except Exception as e:
                message = str(e)
                if "EMAIL_EXISTS" in message:
                    error = "An account with this email already exists"
                else:
                    error = "Could not create account. Please try again."

    return render_template(
        "create_account.html",
        error=error,
        success=success,
        selected_role=selected_role,
    )


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
    recent_interactions = Result.query.order_by(Result.id.desc()).limit(12).all()
    campaign_stats = {}

    for campaign in campaigns:
        rows = Result.query.filter_by(campaign_id=campaign.id).all()
        summary = Counter(r.action for r in rows)
        unique_employees = len({r.employee_email for r in rows if r.employee_email})

        campaign_stats[campaign.id] = {
            "total": len(rows),
            "clicked": summary.get("Clicked Link", 0),
            "reported": summary.get("Reported", 0),
            "ignored": summary.get("Ignored", 0),
            "employees": unique_employees,
        }

    return render_template(
        "admin.html",
        campaigns=campaigns,
        recent_interactions=recent_interactions,
        campaign_stats=campaign_stats,
        message=request.args.get("message"),
    )


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
    campaigns = Campaign.query.order_by(Campaign.id.desc()).all()
    actions = [r.action for r in data]
    summary = Counter(actions)

    return render_template("results.html", data=data, summary=summary, campaigns=campaigns)


#campaign detail page
@app.route("/admin/campaign/<int:id>")
def campaign_detail(id):
    if session.get("role") != "admin":
        return redirect("/login/admin")

    campaign = Campaign.query.get(id)

    if not campaign:
        return redirect("/admin")

    data = Result.query.filter_by(campaign_id=id).all()
    summary = Counter(r.action for r in data)
    unique_employees = len({r.employee_email for r in data if r.employee_email})
    admin_email = session.get("email", "admin@company.com")
    admin_name = admin_email.split("@")[0].replace(".", " ").title() if admin_email else "Admin"
    campaign_preview = build_simulation_payload(campaign.scenario, admin_email, admin_name)

    return render_template(
        "campaign_detail.html",
        campaign=campaign,
        data=data,
        summary=summary,
        total_actions=len(data),
        unique_employees=unique_employees,
        campaign_preview=campaign_preview,
    )


#delete campaign
@app.route("/admin/campaign/<int:id>/delete", methods=["POST"])
def delete_campaign(id):
    if session.get("role") != "admin":
        return redirect("/login/admin")

    campaign = Campaign.query.get(id)

    if not campaign:
        return redirect("/admin?message=campaign-not-found")

    Result.query.filter_by(campaign_id=id).delete()
    db.session.delete(campaign)
    db.session.commit()

    return redirect("/admin?message=campaign-deleted")


#employee page
@app.route("/employee")
def employee():
    if session.get("role") != "employee":
        return redirect("/login/employee")

    employee_email = session.get("email", "")
    campaigns = Campaign.query.all()
    # Build a per-employee set of completed campaign IDs to disable re-running completed simulations.
    completed_campaign_ids = {
        r.campaign_id
        for r in Result.query.filter_by(employee_email=employee_email).all()
        if r.campaign_id is not None
    }

    return render_template(
        "employee.html",
        campaigns=campaigns,
        completed_campaign_ids=completed_campaign_ids,
        message=request.args.get("message"),
    )


#simulations
@app.route("/simulate/<int:id>")
def simulate(id):
    if session.get("role") != "employee":
        return redirect("/login/employee")

    employee_email = session.get("email", "")
    campaign = Campaign.query.get(id)

    if not campaign:
        return "Campaign not found"

    # Block simulation view if this employee already completed this campaign once.
    existing_result = Result.query.filter_by(employee_email=employee_email, campaign_id=id).first()
    if existing_result:
        return redirect("/employee?message=already-completed")

    employee_name = employee_email.split("@")[0].replace(".", " ").title() if employee_email else "Employee"
    simulation = build_simulation_payload(campaign.scenario, employee_email or "employee@company.com", employee_name)
    simulation["requires_sensitive_input"] = simulation_requires_sensitive_input(simulation)

    return render_template("simulate.html", campaign=campaign, simulation=simulation)


@app.route("/simulate/<int:id>/link", methods=["GET", "POST"])
def simulate_link_interaction(id):
    if session.get("role") != "employee":
        return redirect("/login/employee")

    employee_email = session.get("email", "")
    campaign = Campaign.query.get(id)

    if not campaign:
        return redirect("/employee")

    existing_result = Result.query.filter_by(employee_email=employee_email, campaign_id=id).first()
    if existing_result:
        return redirect("/employee?message=already-completed")

    employee_name = employee_email.split("@")[0].replace(".", " ").title() if employee_email else "Employee"
    simulation = build_simulation_payload(campaign.scenario, employee_email or "employee@company.com", employee_name)
    is_phishing = simulation_requires_sensitive_input(simulation)

    error = None
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        account_identifier = request.form.get("account_identifier", "").strip()
        verification_value = request.form.get("verification_value", "").strip()

        if not full_name or not account_identifier or not verification_value:
            error = "All fields are required to submit this portal form."
        else:
            action = "Clicked Link" if is_phishing else "Completed Legitimate Form"

            db.session.add(
                Result(
                    campaign=campaign.scenario,
                    campaign_id=id,
                    action=action,
                    employee_email=employee_email,
                )
            )
            db.session.commit()

            campaign_results = Result.query.filter_by(campaign_id=id).all()
            if len(campaign_results) >= 5:
                generate_campaign_report(
                    campaign=campaign,
                    results=campaign_results,
                    reports_dir=app.config.get("REPORTS_DIR", "instance/reports"),
                )

            return redirect("/employee?message=form-submitted")

    return render_template(
        "simulation_link_form.html",
        campaign=campaign,
        simulation=simulation,
        is_phishing=is_phishing,
        error=error,
    )


#report results
@app.route("/report", methods=["POST"])
def report():
    if session.get("role") != "employee":
        return redirect("/login/employee")

    campaign_id = request.form.get("campaign_id", type=int)
    action = request.form["action"]
    employee_email = session.get("email", "")

    # campaign_id is required so completion is tracked against the exact campaign record.
    if not campaign_id:
        return redirect("/employee")

    campaign_obj = Campaign.query.get(campaign_id)
    if not campaign_obj:
        return redirect("/employee")

    # Reject duplicate submissions so each employee can complete each campaign only once.
    existing_result = Result.query.filter_by(employee_email=employee_email, campaign_id=campaign_id).first()
    if existing_result:
        return redirect("/employee?message=already-completed")

    db.session.add(
        Result(
            campaign=campaign_obj.scenario,
            campaign_id=campaign_id,
            action=action,
            employee_email=employee_email,
        )
    )
    db.session.commit()

    campaign_results = Result.query.filter_by(campaign_id=campaign_id).all()
    if len(campaign_results) >= 5:
        generate_campaign_report(
            campaign=campaign_obj,
            results=campaign_results,
            reports_dir=app.config.get("REPORTS_DIR", "instance/reports"),
        )

    return redirect("/employee")


#awareness page
@app.route("/awareness")
def awareness():
    if "role" not in session:
        return redirect("/")

    return render_template("awareness.html")


#run app
if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)