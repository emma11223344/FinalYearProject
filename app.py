from types import SimpleNamespace
from firebase_admin import firestore
import firebase_config  # ensures Firebase is initialized before we use Firestore

# Firestore client
firestore_db = firestore.client()  # makes firestore_db importable from other modules like auth.py

#result
def _result_from_doc(doc):
    payload = doc.to_dict() or {}
    return SimpleNamespace(
        id=doc.id,
        campaign=payload.get("campaign", ""),  # store campaign name in result for easier reporting without needing to join with campaign collection
        campaign_id=payload.get("campaign_id"),
        action=payload.get("action", ""),
        employee_email=payload.get("employee_email"),
        full_name=payload.get("full_name"),
        account_identifier=payload.get("account_identifier"),
        verification_value=payload.get("verification_value"),
        created_at=payload.get("created_at"),
    )

#campaign
def _campaign_from_doc(doc):
    payload = doc.to_dict() or {}
    return SimpleNamespace(
        id=payload.get("campaign_id"),  # store campaign_id as id for easier referencing in results
        scenario=payload.get("scenario", ""),
        created_at=payload.get("created_at"),  # store created_at for sorting campaigns by creation date in admin view 
        firestore_doc_id=doc.id,
    )

#simulation result functions
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
    firestore_db_local = firestore_db
    payload = {
        "full_name": full_name,
        "account_identifier": account_identifier,
        "verification_value": verification_value,
        "campaign_id": campaign_id,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    if campaign is not None:
        payload["campaign"] = campaign
    if action is not None:
        payload["action"] = action
    if employee_email is not None:
        payload["employee_email"] = employee_email

    try:
        firestore_db_local.collection("simulation_results").add(payload)
    except Exception as exc:
        if logger and not testing:
            logger.warning("Failed to save simulation_result to Firestore: %s", exc)

def save_employee_action_result(campaign, campaign_id, action, employee_email, logger=None, testing=False):   # this function is used to save the result of an employee's action during a phishing simulation
    firestore_db_local = firestore_db
    payload = {
        "campaign": campaign,
        "campaign_id": campaign_id,
        "action": action,
        "employee_email": employee_email,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    try:
        firestore_db_local.collection("simulation_results").add(payload)
    except Exception as exc:
        if logger and not testing:
            logger.warning("Failed to save employee action to Firestore: %s", exc)

def fetch_all_simulation_results():  # fetch all simulation results from Firestore, used to display results in the admin interface and for reporting purposes
    firestore_db_local = firestore_db
    docs = firestore_db_local.collection("simulation_results").stream()
    results = [_result_from_doc(doc) for doc in docs]
    results.sort(key=lambda r: ((r.created_at is not None), r.created_at or ""), reverse=True)
    return results

def fetch_results_by_campaign(campaign_id): # fetch all simulation results for a specific campaign based on the campaign_id, used to display results for a particular phishing simulation campaign in the admin interface
    firestore_db_local = firestore_db
    docs = firestore_db_local.collection("simulation_results").where("campaign_id", "==", campaign_id).stream()
    results = [_result_from_doc(doc) for doc in docs]
    results.sort(key=lambda r: ((r.created_at is not None), r.created_at or ""), reverse=True)
    return results

def fetch_results_by_employee(employee_email): # fetch all simulation results for a specific employee based on their email address
    firestore_db_local = firestore_db
    docs = firestore_db_local.collection("simulation_results").where("employee_email", "==", employee_email).stream()
    return [_result_from_doc(doc) for doc in docs]

def has_result_for_employee_campaign(employee_email, campaign_id): # check if there is already a simulation result for a specific employee and campaign combination, used to prevent duplicate entries when an employee completes the same campaign multiple times.
    # queries the "simulation_results" collection in Firestore for any documents matching the provided employee_email and campaign_id returning True if a result exists and False otherwise
    firestore_db_local = firestore_db
    docs = (
        firestore_db_local.collection("simulation_results")
        .where("employee_email", "==", employee_email)
        .where("campaign_id", "==", campaign_id)
        .limit(1)
        .stream()
    )
    return next(docs, None) is not None

def delete_results_by_campaign(campaign_id):  # delete all simulation results associated with a specific campaign_id from Firestore, used when an admin deletes a campaign to ensure that all related results are also removed from the database
    firestore_db_local = firestore_db
    docs = firestore_db_local.collection("simulation_results").where("campaign_id", "==", campaign_id).stream()
    for doc in docs:
        doc.reference.delete()

#campaign functions 
def fetch_all_campaigns(descending=False):
    firestore_db_local = firestore_db
    docs = firestore_db_local.collection("campaigns").stream()
    campaigns = [_campaign_from_doc(doc) for doc in docs]
    campaigns.sort(key=lambda c: (c.id is not None, c.id or 0), reverse=descending)
    return campaigns

def get_campaign_by_id(campaign_id): # fetch a single campaign by its ID, returning None if not found
    firestore_db_local = firestore_db
    docs = firestore_db_local.collection("campaigns").where("campaign_id", "==", campaign_id).limit(1).stream()
    doc = next(docs, None)
    if not doc:
        return None
    return _campaign_from_doc(doc)

def get_next_campaign_id():
    campaigns = fetch_all_campaigns(descending=True)
    if not campaigns:
        return 1
    return (campaigns[0].id or 0) + 1

def create_campaign_record(scenario): # create a new campaign record in Firestore with a unique campaign_id, the provided scenario name, and a timestamp for when it was created 
    # function is used when an admin creates a new phishing simulation campaign, allowing us to track and manage campaigns effectively in the database
    firestore_db_local = firestore_db
    campaign_id = get_next_campaign_id()
    payload = {
        "campaign_id": campaign_id,
        "scenario": scenario,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    firestore_db_local.collection("campaigns").add(payload)
    return campaign_id

def delete_campaign_record(campaign_id): # delete a campaign record from Firestore based on the provided campaign_id. 
    # this function is used when an admin deletes a phishing simulation campaign, ensuring that the campaign is removed from the database 
    firestore_db_local = firestore_db
    docs = firestore_db_local.collection("campaigns").where("campaign_id", "==", campaign_id).limit(1).stream()
    doc = next(docs, None)
    if not doc:
        return False
    doc.reference.delete()
    return True

app = Flask(__name__)  

#your existing routes
@app.route("/")
def home():
    return "Hello, Phishing Simulator!"

#bind to Render's PORT environment variable
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)