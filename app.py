import os
from types import SimpleNamespace

from flask import Flask, redirect, render_template, request, session, url_for
from firebase_admin import firestore

import firebase_config
from src.auth import authenticate_user, register_user

firestore_db = firestore.client()  # use the Firestore client initialized in firebase_config.py for all database operations in this module


def _normalize_email(email):
    return (email or "").strip().lower()


def save_simulation_result(
    full_name,
    account_identifier,
    verification_value,
    campaign_id,
    campaign=None,
    action=None,
    employee_email=None,
    logger=None,
    testing=False,
):
    # store all relevant information about the simulation result, including employee details, campaign info, and action taken
    payload = {
        "full_name": full_name,
        "account_identifier": account_identifier,
        "verification_value": verification_value,
        "campaign_id": campaign_id,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    if campaign:  # include campaign name for easier reporting without needing a collection join
        payload["campaign"] = campaign
    if action:
        payload["action"] = action
    if employee_email:  # store which employee submitted the result for employee-level tracking
        payload["employee_email"] = _normalize_email(employee_email)

    try:  # save to Firestore, and log if a write fails
        firestore_db.collection("simulation_results").add(payload)
    except Exception as e:
        if logger and not testing:
            logger.warning("Failed to save simulation_result: %s", e)


def save_employee_action_result(campaign, campaign_id, action, employee_email, logger=None, testing=False):
    # store quick action outcomes (e.g., reported/ignored) for simulation analytics in the dashboard
    payload = {
        "campaign": campaign,
        "campaign_id": campaign_id,
        "action": action,
        "employee_email": _normalize_email(employee_email),
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    try:
        firestore_db.collection("simulation_results").add(payload)
    except Exception as e:
        if logger and not testing:
            logger.warning("Failed to save employee action: %s", e)


def _sort_by_date(items, key_fn, reverse=True):
    # helper used to keep campaign and result ordering consistent in the UI
    return sorted(items, key=key_fn, reverse=reverse)


def fetch_all_simulation_results():
    # fetch all simulation results from Firestore for admin reporting
    docs = firestore_db.collection("simulation_results").stream()
    results = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    return _sort_by_date(results, lambda r: r.get("created_at") or "", reverse=True)


def fetch_results_by_campaign(campaign_id):
    # fetch all simulation results for one campaign by campaign_id
    docs = firestore_db.collection("simulation_results").where("campaign_id", "==", campaign_id).stream()
    results = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    return _sort_by_date(results, lambda r: r.get("created_at") or "", reverse=True)


def fetch_results_by_employee(employee_email):
    # fetch all simulation results for one employee by employee_email
    normalized = _normalize_email(employee_email)
    raw = (employee_email or "").strip()

    docs = firestore_db.collection("simulation_results").where("employee_email", "==", normalized).stream()
    results = [{"id": doc.id, **doc.to_dict()} for doc in docs]

    # Backward compatibility for old records saved before normalization.
    if raw and raw != normalized:
        raw_docs = firestore_db.collection("simulation_results").where("employee_email", "==", raw).stream()
        seen = {r.get("id") for r in results}
        for doc in raw_docs:
            payload = {"id": doc.id, **doc.to_dict()}
            if payload["id"] not in seen:
                results.append(payload)

    return results


def has_result_for_employee_campaign(employee_email, campaign_id):
    # check if an employee already completed a specific campaign to prevent duplicate submissions
    normalized = _normalize_email(employee_email)
    docs = (
        firestore_db.collection("simulation_results")
        .where("employee_email", "==", normalized)
        .where("campaign_id", "==", campaign_id)
        .limit(1)
        .stream()
    )
    return next(docs, None) is not None


def delete_results_by_campaign(campaign_id):
    # delete all results linked to a campaign when that campaign is removed
    docs = firestore_db.collection("simulation_results").where("campaign_id", "==", campaign_id).stream()
    for doc in docs:
        doc.reference.delete()


def fetch_all_campaigns(descending=False):
    # fetch all campaigns and sort by campaign_id for consistent display order
    docs = firestore_db.collection("campaigns").stream()
    campaigns = [{"firestore_doc_id": doc.id, **doc.to_dict()} for doc in docs]
    return _sort_by_date(campaigns, lambda c: c.get("campaign_id") or 0, reverse=descending)


def get_campaign_by_id(campaign_id):
    # fetch one campaign document by integer campaign_id
    docs = firestore_db.collection("campaigns").where("campaign_id", "==", campaign_id).limit(1).stream()
    doc = next(docs, None)
    return {"firestore_doc_id": doc.id, **doc.to_dict()} if doc else None


def get_next_campaign_id():
    # generate the next sequential campaign id
    campaigns = fetch_all_campaigns(descending=True)
    return campaigns[0]["campaign_id"] + 1 if campaigns else 1


def create_campaign_record(scenario):
    # create a new campaign record in Firestore from the selected scenario
    campaign_id = get_next_campaign_id()
    payload = {
        "campaign_id": campaign_id,
        "scenario": scenario,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    firestore_db.collection("campaigns").add(payload)
    return campaign_id


def delete_campaign_record(campaign_id):
    # delete one campaign by campaign_id
    docs = firestore_db.collection("campaigns").where("campaign_id", "==", campaign_id).limit(1).stream()
    doc = next(docs, None)
    if doc:
        doc.reference.delete()
        return True
    return False


app = Flask(__name__, template_folder="templates", static_folder="static")  # initialize Flask app
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")


ROUTES = {
    "/": "index.html",
    "/awareness": "awareness.html",
    "/campaign": "create_campaign.html",
    "/create_campaign": "create_campaign.html",
    "/dashboard": "dashboard.html",
    "/results": "results.html",
    "/simulate": "simulate.html",
    "/simulation_link_form": "simulation_link_form.html",
}


def _is_phishing_scenario(scenario_name):
    # scenarios listed here are treated as legitimate/safe simulations
    safe_scenarios = {
        "Team Lunch Invite",
        "IT Maintenance Notice",
        "Quarterly Town Hall",
        "Training Reminder",
        "Security Patch Advisory",
        "Facilities Access Notice",
        "Project Kickoff Invite",
        "Payroll Schedule Update",
    }
    return (scenario_name or "") not in safe_scenarios


def _is_correct_simulation_action(campaign_name, action):
    # correctness depends on whether the scenario is phishing or legitimate
    action = (action or "").strip()
    if not action:
        return False

    if _is_phishing_scenario(campaign_name):
        return action == "Reported"

    return action == "Completed Legitimate Form"


def _build_simulation_payload(campaign):
    # build scenario-specific email payload used by the simulation templates
    scenario = campaign.get("scenario", "Simulation")
    phishing = _is_phishing_scenario(scenario)

    phishing_details = {
        "Password Reset": {
            "sender": "Microsoft 365 Security <no-reply@msreset-security.com>",
            "reply_to": "identity-ops@msreset-security.com",
            "subject": "Action Required: Password expires in 45 minutes",
            "body": [
                "Hi,",
                "Our automated security review detected a sign-in from a new location and temporarily limited mailbox access.",
                "To prevent account suspension before payroll processing, you must complete password verification immediately.",
                "If this is not completed within 45 minutes, your mailbox and Teams access will be disabled.",
            ],
            "display_link": "https://security-m365-verify.com/recover",
            "link": "https://security-m365-verify.com/recover",
            "attachment": None,
            "closing": "Security Operations Center",
            "signature": "Microsoft 365 Identity Protection",
        },
        "Invoice Scam": {
            "sender": "Accounts Payable <invoices@vendor-payments.net>",
            "reply_to": "finance-escalations@vendor-payments.net",
            "subject": "Outstanding Invoice INV-88431 - Immediate Review Needed",
            "body": [
                "Hello Finance Team,",
                "Our records show invoice INV-88431 remains unpaid and is now in late status.",
                "Please review the attached remittance notice and submit confirmation today to avoid service interruption.",
                "If payment was already sent, verify bank details through the secure portal link below.",
            ],
            "display_link": "https://vendor-payment-confirmation.com/portal",
            "link": "https://vendor-payment-confirmation.com/portal",
            "attachment": "INV-88431-Remittance.pdf",
            "closing": "Regards,",
            "signature": "Vendor Billing Desk",
        },
        "Delivery Notice": {
            "sender": "DHL Dispatch <alerts@dhl-track-shipment.co>",
            "reply_to": "dhl-case@dhl-track-shipment.co",
            "subject": "Delivery Attempt Failed - Confirm Address Today",
            "body": [
                "Dear Recipient,",
                "Your package could not be delivered due to incomplete location details.",
                "A redelivery fee may apply if the address is not confirmed before end of business.",
                "Use the verification page below to confirm your details and release shipment hold.",
            ],
            "display_link": "https://dhl-redelivery-check.com/confirm",
            "link": "https://dhl-redelivery-check.com/confirm",
            "attachment": None,
            "closing": "Thank you,",
            "signature": "DHL Delivery Support",
        },
        "MFA Expiration": {
            "sender": "Identity Team <mfa-admin@company-it-security.com>",
            "reply_to": "mfa-helpdesk@company-it-security.com",
            "subject": "Multi-Factor Token Expiring Today - Re-Register Required",
            "body": [
                "Hi,",
                "Your MFA token is flagged as expired after the latest security policy update.",
                "To avoid being locked out of Outlook, VPN, and HR systems, complete token re-registration now.",
                "The re-registration link is valid for a single use and expires in 30 minutes.",
            ],
            "display_link": "https://mfa-revalidation-portal.com/register",
            "link": "https://mfa-revalidation-portal.com/register",
            "attachment": None,
            "closing": "Security Identity Operations",
            "signature": "IT Access Management",
        },
        "Shared Document": {
            "sender": "DocuShare <noreply@docs-collab-secure.com>",
            "reply_to": "share-support@docs-collab-secure.com",
            "subject": "[External] You were mentioned in Q2 Budget Revisions",
            "body": [
                "Hello,",
                "A confidential document has been shared with you and requires acknowledgment before the board review meeting.",
                "Your comments are requested by 3:30 PM today to avoid escalation to your line manager.",
                "Open the secure document link below to review and approve.",
            ],
            "display_link": "https://secure-doc-reviewer.com/open",
            "link": "https://secure-doc-reviewer.com/open",
            "attachment": None,
            "closing": "Best regards,",
            "signature": "Document Collaboration Service",
        },
        "HR Policy Update": {
            "sender": "HR Compliance <policy-update@hr-compliance-notice.com>",
            "reply_to": "hr-escalations@hr-compliance-notice.com",
            "subject": "Mandatory Policy Acknowledgement Needed Before 5 PM",
            "body": [
                "Dear Employee,",
                "A revised remote work and data handling policy was published and requires immediate acknowledgment.",
                "Employees who do not acknowledge before 5 PM may lose remote access privileges.",
                "Please review and sign using the policy link below.",
            ],
            "display_link": "https://hr-policy-review-now.com/acknowledge",
            "link": "https://hr-policy-review-now.com/acknowledge",
            "attachment": "Policy-Revision-Summary.pdf",
            "closing": "HR Compliance Office",
            "signature": "People Operations",
        },
        "CEO Wire Request": {
            "sender": "Emma (CEO) <ceo.office@exec-prioritymail.com>",
            "reply_to": "executive-desk@exec-prioritymail.com",
            "subject": "Confidential: Need urgent transfer before 2 PM",
            "body": [
                "I am in an external meeting and need this handled discreetly.",
                "Process an urgent supplier transfer today and confirm once complete.",
                "Do not call me right now; share confirmation through the secure link only.",
                "This is time-sensitive and must be completed before 2 PM.",
            ],
            "display_link": "https://exec-payment-instructions.com/secure",
            "link": "https://exec-payment-instructions.com/secure",
            "attachment": "Beneficiary-Bank-Details.pdf",
            "closing": "Thanks,",
            "signature": "Emma",
        },
        "Benefits Enrollment": {
            "sender": "Benefits Team <benefits@open-enrollment-alerts.com>",
            "reply_to": "benefits-admin@open-enrollment-alerts.com",
            "subject": "Final Reminder: Benefits enrollment closes tonight",
            "body": [
                "Hi,",
                "Your health and pension selections are currently incomplete in the enrollment system.",
                "If not finalized by midnight, your default coverage will be applied for the full year.",
                "Complete your selections now through the enrollment portal below.",
            ],
            "display_link": "https://benefits-enroll-now.com/login",
            "link": "https://benefits-enroll-now.com/login",
            "attachment": None,
            "closing": "Benefits Administration",
            "signature": "People Services",
        },
    }

    safe_details = {
        "sender": "HR Team <hr@company.com>",
        "reply_to": "hr@company.com",
        "subject": scenario,
        "body": [
            "Hi Team,",
            "This is a normal internal communication related to your day-to-day work.",
            "Please review the information and complete any required action using the intranet link below.",
        ],
        "display_link": "https://intranet.company.com",
        "link": "https://intranet.company.com",
        "attachment": None,
        "closing": "Thanks,",
        "signature": "HR Team",
    }

    selected = phishing_details.get(scenario, safe_details if not phishing else {
        "sender": "IT Security Alerts <security-update@company-security-mail.com>",
        "reply_to": "security-escalation@company-security-mail.com",
        "subject": f"Urgent Action Required: {scenario}",
        "body": [
            "Hello,",
            "A high-priority security event requires immediate verification from your account.",
            "Complete the requested action now to avoid temporary restrictions.",
        ],
        "display_link": "https://secure-account-check.com/verify",
        "link": "https://secure-account-check.com/verify",
        "attachment": None,
        "closing": "Security Operations",
        "signature": "IT Security Team",
    })

    return {
        "sender": selected["sender"],
        "reply_to": selected["reply_to"],
        "recipient": session.get("email") or "employee@company.com",
        "received_time": "Today 09:12",
        "subject": selected["subject"],
        "body": selected["body"],
        "display_link": selected["display_link"],
        "link": selected["link"],
        "attachment": selected["attachment"],
        "closing": selected["closing"],
        "signature": selected["signature"],
        "red_flags": [
            "Urgent tone requesting immediate action",
            "Suspicious external reply-to address",
            "Link domain does not match company domain",
        ] if phishing else [],
    }


def _build_admin_context(message=None):
    # build admin dashboard data including campaign stats and recent interactions
    campaigns_raw = fetch_all_campaigns(descending=True)
    campaigns = [
        SimpleNamespace(id=c.get("campaign_id"), scenario=c.get("scenario", "Unknown"))
        for c in campaigns_raw
    ]

    all_results = fetch_all_simulation_results()  # used to derive per-campaign and recent interaction summaries
    campaign_stats = {}
    for c in campaigns:
        matching = [r for r in all_results if r.get("campaign_id") == c.id]
        employees = {r.get("employee_email") for r in matching if r.get("employee_email")}
        reported = sum(1 for r in matching if (r.get("action") or "").strip().lower() == "reported")
        campaign_stats[c.id] = SimpleNamespace(total=len(matching), employees=len(employees), reported=reported)

    recent_interactions = []
    for r in all_results[:20]:
        action = r.get("action") or "-"
        campaign_name = r.get("campaign") or ""
        simulation_type_label = "Phishing" if _is_phishing_scenario(campaign_name) else "Legitimate"

        if action == "-":
            status_label, status_class, score, score_label = "N/A", "status-correct", None, "N/A"
        elif _is_correct_simulation_action(campaign_name, action):
            status_label, status_class, score, score_label = "Correct", "status-correct", 100, "100"
        else:
            status_label, status_class, score, score_label = "Incorrect", "status-incorrect", 0, "0"

        recent_interactions.append(
            SimpleNamespace(
                employee_email=r.get("employee_email"),
                campaign=r.get("campaign"),
                simulation_type_label=simulation_type_label,
                action=action,
                status_label=status_label,
                status_class=status_class,
                awareness_score=score,
                awareness_score_label=score_label,
            )
        )

    return {
        "campaigns": campaigns,
        "campaign_stats": campaign_stats,
        "recent_interactions": recent_interactions,
        "message": message,
    }


def _build_employee_context(message=None, employee_email=None):
    # build employee dashboard data: available campaigns, completed campaign ids, and score table
    campaigns_raw = fetch_all_campaigns(descending=False)
    campaigns = [
        SimpleNamespace(id=c.get("campaign_id"), scenario=c.get("scenario", "Unknown"))
        for c in campaigns_raw
    ]

    completed_campaign_ids = set()  # marks campaigns already done by this employee
    employee_results = []
    overall_total_completed = 0
    overall_right_count = 0
    overall_wrong_count = 0
    overall_right_pct = 0
    overall_wrong_pct = 0

    if employee_email:
        employee_email = _normalize_email(employee_email)
        employee_raw_results = _sort_by_date(
            fetch_results_by_employee(employee_email),
            lambda r: r.get("created_at") or "",
            reverse=True,
        )

        # Use the latest action per campaign to compute a fair overall score.
        latest_by_campaign = {}
        for r in employee_raw_results:
            cid_latest = r.get("campaign_id")
            try:
                cid_latest = int(cid_latest)
            except (TypeError, ValueError):
                continue
            if cid_latest not in latest_by_campaign:
                latest_by_campaign[cid_latest] = (
                    (r.get("action") or "").strip(),
                    r.get("campaign") or "",
                )

        overall_total_completed = len(latest_by_campaign)
        if overall_total_completed:
            for latest_action, latest_campaign in latest_by_campaign.values():
                if _is_correct_simulation_action(latest_campaign, latest_action):
                    overall_right_count += 1
                else:
                    overall_wrong_count += 1

            overall_right_pct = round((overall_right_count / overall_total_completed) * 100)
            overall_wrong_pct = round((overall_wrong_count / overall_total_completed) * 100)

        for r in employee_raw_results:
            cid = r.get("campaign_id")
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                cid = None
            if cid is not None:
                completed_campaign_ids.add(cid)

            action = (r.get("action") or "").strip()
            campaign_name = r.get("campaign") or ""
            if not action:
                score, score_label, score_class = None, "N/A", "score-na"
            elif _is_correct_simulation_action(campaign_name, action):
                score, score_label, score_class = 100, "100", "score-strong"
            else:
                score, score_label, score_class = 0, "0", "score-low"

            employee_results.append(
                SimpleNamespace(
                    campaign=r.get("campaign") or f"Campaign #{cid if cid is not None else '-'}",
                    action=action or "-",
                    score=score,
                    score_label=score_label,
                    score_class=score_class,
                )
            )

    return {
        "campaigns": campaigns,
        "completed_campaign_ids": completed_campaign_ids,
        "employee_results": employee_results,
        "overall_total_completed": overall_total_completed,
        "overall_right_count": overall_right_count,
        "overall_wrong_count": overall_wrong_count,
        "overall_right_pct": overall_right_pct,
        "overall_wrong_pct": overall_wrong_pct,
        "employee_email": employee_email,
        "message": message,
    }


@app.route("/login", methods=["GET", "POST"])
def handle_login():
    # employee login route with role validation via authenticate_user
    if request.method == "GET":
        return render_template("login.html", role="employee", error=None)

    email = _normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "").strip()
    user, error = authenticate_user(email, password, "employee")
    if error:
        return render_template("login.html", role="employee", error=error)

    session["role"] = "employee"
    session["email"] = _normalize_email(user.get("email") or email)
    return redirect(url_for("employee_dashboard"))


@app.route("/login/admin", methods=["GET", "POST"])
def login_admin():
    # admin login route with role validation via authenticate_user
    if request.method == "GET":
        return render_template("login.html", role="admin", error=None)

    email = _normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "").strip()
    user, error = authenticate_user(email, password, "admin")
    if error:
        return render_template("login.html", role="admin", error=error)

    session["role"] = "admin"
    session["email"] = _normalize_email(user.get("email") or email)
    return redirect(url_for("admin_dashboard"))


@app.route("/login/employee", methods=["GET", "POST"])
def login_employee():
    # alias that maps /login/employee to the same employee login logic
    return handle_login()


@app.route("/admin", methods=["GET"])
def admin_dashboard():
    message = request.args.get("message")
    return render_template("admin.html", **_build_admin_context(message=message))


@app.route("/create", methods=["POST"])
def create_campaign_post():
    # admin create-campaign form submit handler
    scenario = (request.form.get("scenario") or "").strip()
    if scenario:
        try:
            create_campaign_record(scenario)
        except Exception:
            return redirect(url_for("admin_dashboard", message="campaign-not-found"))

    return redirect(url_for("admin_dashboard"))


@app.route("/employee", methods=["GET"])
def employee_dashboard():
    # employee dashboard route showing campaigns and employee result history
    message = request.args.get("message")
    employee_email = _normalize_email(session.get("email") or request.args.get("email"))
    return render_template("employee.html", **_build_employee_context(message=message, employee_email=employee_email))


@app.route("/simulate/<int:campaign_id>", methods=["GET"])
def simulate_campaign(campaign_id):
    # main simulation route used by employee campaign clicks
    campaign = get_campaign_by_id(campaign_id)
    if not campaign:
        return redirect(url_for("employee_dashboard"))

    simulation = _build_simulation_payload(campaign)
    return render_template(
        "simulate.html",
        campaign=SimpleNamespace(id=campaign_id, scenario=campaign.get("scenario", "Unknown")),
        simulation=simulation,
        timer_seconds=60,
    )


@app.route("/simulate/<campaign_ref>", methods=["GET"])
@app.route("/simulate/<campaign_ref>/", methods=["GET"])
def simulate_campaign_compat(campaign_ref):
    # compatibility route to avoid 404 when campaign id arrives as text or with trailing slash
    try:
        campaign_id = int(str(campaign_ref).strip())
    except (TypeError, ValueError):
        return redirect(url_for("employee_dashboard"))
    return redirect(url_for("simulate_campaign", campaign_id=campaign_id))


@app.route("/simulate/<int:campaign_id>/link", methods=["GET", "POST"])
def simulate_campaign_link(campaign_id):
    # simulation link destination page where employee submits the form interaction
    campaign = get_campaign_by_id(campaign_id)
    if not campaign:
        return redirect(url_for("employee_dashboard"))

    simulation = _build_simulation_payload(campaign)
    is_phishing = bool(simulation.get("red_flags"))
    employee_email = _normalize_email(session.get("email") or request.args.get("email") or request.form.get("employee_email"))

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        account_identifier = (request.form.get("account_identifier") or "").strip()
        verification_value = (request.form.get("verification_value") or "").strip()

        if not full_name or not account_identifier or not verification_value:
            return render_template(
                "simulation_link_form.html",
                campaign=SimpleNamespace(id=campaign_id, scenario=campaign.get("scenario", "Unknown")),
                simulation=simulation,
                is_phishing=is_phishing,
                timer_seconds=60,
                error="Please complete all fields.",
            )

        action = "Clicked Link" if is_phishing else "Completed Legitimate Form"
        save_simulation_result(
            full_name=full_name,
            account_identifier=account_identifier,
            verification_value=verification_value,
            campaign_id=campaign_id,
            campaign=campaign.get("scenario"),
            action=action,
            employee_email=employee_email,
        )
        return redirect(url_for("employee_dashboard", message="form-submitted"))

    return render_template(
        "simulation_link_form.html",
        campaign=SimpleNamespace(id=campaign_id, scenario=campaign.get("scenario", "Unknown")),
        simulation=simulation,
        is_phishing=is_phishing,
        timer_seconds=60,
        error=None,
    )


@app.route("/simulate/<int:campaign_id>/timeout", methods=["POST"])
def simulate_campaign_timeout(campaign_id):
    # timer expiration endpoint: records Ignored action
    campaign = get_campaign_by_id(campaign_id)
    if campaign:
        save_employee_action_result(
            campaign=campaign.get("scenario"),
            campaign_id=campaign_id,
            action="Ignored",
            employee_email=_normalize_email(session.get("email") or request.args.get("email") or request.form.get("employee_email")),
        )
    return redirect(url_for("employee_dashboard", message="timed-out"))


@app.route("/report", methods=["POST"])
def report_action():
    # generic report endpoint used by simulation decision form
    campaign_id_raw = request.form.get("campaign_id")
    action = (request.form.get("action") or "").strip() or "Ignored"
    try:
        campaign_id = int(campaign_id_raw)
    except (TypeError, ValueError):
        return redirect(url_for("employee_dashboard"))

    campaign = get_campaign_by_id(campaign_id)
    if campaign:
        save_employee_action_result(
            campaign=campaign.get("scenario"),
            campaign_id=campaign_id,
            action=action,
            employee_email=_normalize_email(session.get("email") or request.form.get("employee_email") or request.args.get("email")),
        )
    return redirect(url_for("employee_dashboard", message="form-submitted"))


@app.route("/create-account", methods=["GET", "POST"])
@app.route("/create_account", methods=["GET", "POST"])
def create_account_alias():
    # account creation route supports both kebab-case and underscore URLs
    if request.method == "GET":
        return render_template("create_account.html", error=None, success=None, selected_role="employee")

    email = _normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    selected_role = (request.form.get("role") or "employee").strip().lower()

    role, error = register_user(email, password, confirm_password, selected_role)
    if error:
        return render_template(
            "create_account.html",
            error=error,
            success=None,
            selected_role=selected_role,
        )

    return render_template(
        "create_account.html",
        error=None,
        success=f"{role.title()} account created successfully.",
        selected_role="employee",
    )


@app.route("/logout")
def logout_session():
    # clear session and send the user back to home
    session.clear()
    return redirect(url_for("index"))


@app.route("/campaign/<int:campaign_id>", methods=["GET"])
def campaign_detail(campaign_id):
    # admin campaign detail view with message preview and campaign-specific result table
    campaign = get_campaign_by_id(campaign_id)
    if not campaign:
        return redirect(url_for("results"))

    data = fetch_results_by_campaign(campaign_id)
    preview = _build_simulation_payload(campaign)
    return render_template(
        "campaign_detail.html",
        campaign=SimpleNamespace(id=campaign_id, scenario=campaign.get("scenario", "Unknown")),
        data=data,
        campaign_preview=preview,
    )


for path, template in ROUTES.items():
    # register static template routes from the ROUTES map
    endpoint = path.lstrip("/") or "index"
    app.add_url_rule(path, endpoint=endpoint, view_func=lambda t=template: render_template(t))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
