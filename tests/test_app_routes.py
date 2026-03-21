import pytest
import json
from pathlib import Path
from app import app, db, Campaign, Result


@pytest.fixture
def client():
    app.config["TESTING"] = True #enable testing mode to provide better error messages and disable error catching
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context(): #create an application context to allow database operations and other app-related tasks to work properly during testing
        db.create_all()

    with app.test_client() as client: #create a test client to simulate HTTP requests to the application without running the server allowing us to test routes and functionality in isolation
        yield client

    with app.app_context(): #clean up the database after tests are done to ensure a clean state for future tests and prevent data from one test affecting another
        db.drop_all()


def test_home_page(client): #test that the home page loads successfully and returns a 200 status code indicating that the page is accessible
    response = client.get("/") #simulate a GET request to the home page route and store the response for further assertions
    assert response.status_code == 200 #assert that the response status code is 200 indicating that the page loaded successfully without any errors


def test_admin_redirect_if_not_logged_in(client):
    response = client.get("/admin")
    assert response.status_code == 302 #assert that the response status code is 302 indicating that the user is redirected to the login page


def test_employee_redirect_if_not_logged_in(client):
    response = client.get("/employee")
    assert response.status_code == 302 #assert that the response status code is 302 indicating that the user is redirected to the login page


def test_create_campaign(client): #test that an admin can create a new campaign and that it is stored in the database correctly
    with client.session_transaction() as session: #simulate an admin user being logged in by setting the session variables to indicate that the user has an admin role
        session["role"] = "admin"

    response = client.post("/create", data={"scenario": "Password Reset"}) #simulate a POST request to the campaign creation route with form data containing the scenario name for the new campaign and store the response for further assertions
    assert response.status_code == 302 #assert that the response status code is 302 indicating that the user is redirected to the login page

    

def test_report_requires_employee_login(client): #test that the report route requires an employee to be logged in and redirects to the login page if not
    response = client.post("/report", data={"campaign_id": 1, "action": "Reported"}) #simulate a POST request to the report route with form data containing the campaign ID and action for reporting a phishing simulation result and store the response for further assertions
    assert response.status_code == 302 #assert that the response status code is 302 indicating that the user is redirected to the login page


def test_report_creates_result(client): #test that when an employee reports a phishing simulation result, a new Result entry is created in the database with the correct employee email and action
    with app.app_context(): #create a campaign in the database to link the report to and ensure that the campaign ID exists for the test
        campaign = Campaign(scenario="Invoice Scam") #create a new Campaign instance with the scenario name "Invoice Scam" to represent a phishing campaign in the database
        db.session.add(campaign) #add the new campaign to the database session to prepare it for insertion into the database
        db.session.commit() #commit the session to save the new campaign to the database and make it available for querying during the test

    with client.session_transaction() as session: #simulate an employee user being logged in by setting the session variables to indicate that the user has an employee role and an email address
        session["role"] = "employee" #set the session variable "role" to "employee" to indicate that the user has an employee role which is required to report phishing simulation results
        session["email"] = "alice@example.com" #set the session variable "email" to "alice@example.com" to represent the email address of the logged-in employee which will be stored in the Result entry when reporting a phishing simulation result

    client.post("/report", data={"campaign_id": 1, "action": "Reported"}) #simulate a POST request to the report route with form data containing the campaign ID and action for reporting a phishing simulation result and store the response for further assertions

    with app.app_context():  #query the database for the first Result entry to verify that it was created correctly with the expected employee email and action values after reporting a phishing simulation result
        result = Result.query.first()  #query the database for the first Result entry which should have been created as a result of the report action and store it in the variable "result" for further assertions
        assert result.employee_email == "alice@example.com"   #assert that the employee_email field of the Result entry matches the email address of the logged-in employee who reported the phishing simulation result to verify that the correct employee information is stored in the database
        assert result.action == "Reported"  #assert that the action field of the Result entry matches the expected action value "Reported" to verify that the correct action information is stored in the database when reporting a phishing simulation result


def test_report_is_generated_after_five_responses(client, tmp_path):
    app.config["REPORTS_DIR"] = str(tmp_path)

    with app.app_context():
        campaign = Campaign(scenario="Password Reset")
        db.session.add(campaign)
        db.session.commit()
        campaign_id = campaign.id

    response_actions = ["Reported", "Clicked Link", "Ignored", "Reported", "Ignored"]
    response_emails = [
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
        "dave@example.com",
        "eve@example.com",
    ]

    for email, action in zip(response_emails, response_actions):
        with client.session_transaction() as session:
            session["role"] = "employee"
            session["email"] = email

        client.post("/report", data={"campaign_id": campaign_id, "action": action})

    report_file = Path(tmp_path) / f"campaign_{campaign_id}_report.json"
    assert report_file.exists()

    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert payload["response_count"] == 5
    assert payload["campaign"]["id"] == campaign_id
    assert payload["summary"].get("Reported", 0) == 2
    assert payload["summary"].get("Ignored", 0) == 2
    assert payload["summary"].get("Clicked Link", 0) == 1


def test_phishing_link_interaction_requires_details_and_records_clicked_link(client):
    with app.app_context():
        campaign = Campaign(scenario="Password Reset")
        db.session.add(campaign)
        db.session.commit()
        campaign_id = campaign.id

    with client.session_transaction() as session:
        session["role"] = "employee"
        session["email"] = "alice@example.com"

    get_response = client.get(f"/simulate/{campaign_id}/link")
    assert get_response.status_code == 200

    invalid_submit = client.post(
        f"/simulate/{campaign_id}/link",
        data={"full_name": "", "account_identifier": "alice@example.com", "verification_value": "123456"},
    )
    assert invalid_submit.status_code == 200

    valid_submit = client.post(
        f"/simulate/{campaign_id}/link",
        data={"full_name": "Alice Example", "account_identifier": "alice@example.com", "verification_value": "Password123!"},
    )
    assert valid_submit.status_code == 302

    with app.app_context():
        result = Result.query.filter_by(campaign_id=campaign_id, employee_email="alice@example.com").first()
        assert result is not None
        assert result.action == "Clicked Link"


def test_legitimate_link_interaction_records_legitimate_form_completion(client):
    with app.app_context():
        campaign = Campaign(scenario="Team Lunch Invite")
        db.session.add(campaign)
        db.session.commit()
        campaign_id = campaign.id

    with client.session_transaction() as session:
        session["role"] = "employee"
        session["email"] = "bob@example.com"

    valid_submit = client.post(
        f"/simulate/{campaign_id}/link",
        data={"full_name": "Bob Example", "account_identifier": "EMP-9191", "verification_value": "RSVP-OK"},
    )
    assert valid_submit.status_code == 302

    with app.app_context():
        result = Result.query.filter_by(campaign_id=campaign_id, employee_email="bob@example.com").first()
        assert result is not None
        assert result.action == "Completed Legitimate Form"


def test_logout(client):  #test that the logout route clears the session and redirects to the home page
    with client.session_transaction() as session: #simulate an admin user being logged in by setting the session variables to indicate that the user has an admin role and an email address to verify that the logout route properly clears these session variables
        session["role"] = "admin"   #set the session variable "role" to "admin" to indicate that the user has an admin role which will be cleared by the logout route
        session["email"] = "admin@example.com"      #set the session variable "email" to "

    response = client.get("/logout")   #simulate a GET request to the logout route to trigger the logout functionality and store the response for further assertions
    assert response.status_code == 302

    with client.session_transaction() as session: #after logging out, check the session variables to ensure that they have been cleared properly by the logout route to verify that the user is effectively logged out and cannot access protected routes without logging in again
        assert "role" not in session #assert that the session variable "role" has been removed from the session to verify that the user's role information has been cleared during logout
        assert "email" not in session   #assert that the session variable "email" has been removed from the session to verify that the user's email information has been cleared during logout