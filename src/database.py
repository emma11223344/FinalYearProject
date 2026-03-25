from types import SimpleNamespace

from firebase_admin import firestore

firestore_db = firestore.client()


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
        firestore_db.collection("simulation_results").add(payload)
    except Exception as exc:
        if logger and not testing:
            logger.warning("Failed to save simulation_result to Firestore: %s", exc)


def save_employee_action_result(campaign, campaign_id, action, employee_email, logger=None, testing=False):
    payload = {
        "campaign": campaign,
        "campaign_id": campaign_id,
        "action": action,
        "employee_email": employee_email,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    try:
        firestore_db.collection("simulation_results").add(payload)
    except Exception as exc:
        if logger and not testing:
            logger.warning("Failed to save employee action to Firestore: %s", exc)


def _result_from_doc(doc):
    payload = doc.to_dict() or {}
    return SimpleNamespace(
        id=doc.id,
        campaign=payload.get("campaign", ""),
        campaign_id=payload.get("campaign_id"),
        action=payload.get("action", ""),
        employee_email=payload.get("employee_email"),
        full_name=payload.get("full_name"),
        account_identifier=payload.get("account_identifier"),
        verification_value=payload.get("verification_value"),
        created_at=payload.get("created_at"),
    )


def fetch_all_simulation_results():
    docs = firestore_db.collection("simulation_results").stream()
    results = [_result_from_doc(doc) for doc in docs]
    results.sort(key=lambda r: ((r.created_at is not None), r.created_at or ""), reverse=True)
    return results


def fetch_results_by_campaign(campaign_id):
    docs = firestore_db.collection("simulation_results").where("campaign_id", "==", campaign_id).stream()
    results = [_result_from_doc(doc) for doc in docs]
    results.sort(key=lambda r: ((r.created_at is not None), r.created_at or ""), reverse=True)
    return results


def fetch_results_by_employee(employee_email):
    docs = firestore_db.collection("simulation_results").where("employee_email", "==", employee_email).stream()
    return [_result_from_doc(doc) for doc in docs]


def has_result_for_employee_campaign(employee_email, campaign_id):
    docs = (
        firestore_db.collection("simulation_results")
        .where("employee_email", "==", employee_email)
        .where("campaign_id", "==", campaign_id)
        .limit(1)
        .stream()
    )
    return next(docs, None) is not None


def delete_results_by_campaign(campaign_id):
    docs = firestore_db.collection("simulation_results").where("campaign_id", "==", campaign_id).stream()
    for doc in docs:
        doc.reference.delete()


def _campaign_from_doc(doc):
    payload = doc.to_dict() or {}
    return SimpleNamespace(
        id=payload.get("campaign_id"),
        scenario=payload.get("scenario", ""),
        created_at=payload.get("created_at"),
        firestore_doc_id=doc.id,
    )


def fetch_all_campaigns(descending=False):
    docs = firestore_db.collection("campaigns").stream()
    campaigns = [_campaign_from_doc(doc) for doc in docs]
    campaigns.sort(key=lambda c: (c.id is not None, c.id or 0), reverse=descending)
    return campaigns


def get_campaign_by_id(campaign_id):
    docs = firestore_db.collection("campaigns").where("campaign_id", "==", campaign_id).limit(1).stream()
    doc = next(docs, None)
    if not doc:
        return None
    return _campaign_from_doc(doc)


def get_next_campaign_id():
    campaigns = fetch_all_campaigns(descending=True)
    if not campaigns:
        return 1
    return (campaigns[0].id or 0) + 1


def create_campaign_record(scenario):
    campaign_id = get_next_campaign_id()
    payload = {
        "campaign_id": campaign_id,
        "scenario": scenario,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    firestore_db.collection("campaigns").add(payload)
    return campaign_id


def delete_campaign_record(campaign_id):
    docs = firestore_db.collection("campaigns").where("campaign_id", "==", campaign_id).limit(1).stream()
    doc = next(docs, None)
    if not doc:
        return False
    doc.reference.delete()
    return True
