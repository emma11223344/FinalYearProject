from firebase_admin import auth
from werkzeug.security import check_password_hash, generate_password_hash

from src.database import firestore_db
from src.validation import is_strong_password, is_valid_email


def authenticate_user(email, password, expected_role):
    normalized_email = (email or "").strip().lower()
    role = (expected_role or "").strip().lower()

    if not is_valid_email(normalized_email):
        return None, "Please enter a valid email address"

    try:
        user = auth.get_user_by_email(normalized_email)
        profile_doc = firestore_db.collection("users").document(user.uid).get()
        if not profile_doc.exists:
            return None, "Account profile not found. Please contact support."

        profile = profile_doc.to_dict() or {}
        stored_password_hash = profile.get("password_hash", "")
        stored_role = (profile.get("role") or "").strip().lower()

        if not stored_password_hash or not check_password_hash(stored_password_hash, password):
            return None, "Invalid email or password"

        if stored_role != role:
            return None, f"This account is registered as {stored_role or 'unknown'}. Use the correct login page."

        return {"uid": user.uid, "email": normalized_email, "role": stored_role}, None
    except Exception:
        return None, "Invalid email or password"


def register_user(email, password, confirm_password, selected_role):
    normalized_email = (email or "").strip().lower()
    role = (selected_role or "employee").strip().lower()

    if role not in ("admin", "employee"):
        return None, "Please select a valid account role"
    if not is_valid_email(normalized_email):
        return None, "Please enter a valid email address"
    if password != confirm_password:
        return None, "Passwords do not match"
    if not is_strong_password(password):
        return None, "Password must be at least 8 characters and include uppercase, lowercase, a number, and a symbol"

    try:
        user = auth.create_user(email=normalized_email, password=password)
        firestore_db.collection("users").document(user.uid).set(
            {
                "email": normalized_email,
                "role": role,
                "password_hash": generate_password_hash(password),
            }
        )
        return role, None
    except Exception as exc:
        if "EMAIL_EXISTS" in str(exc):
            return None, "An account with this email already exists"
        return None, "Could not create account. Please try again."
