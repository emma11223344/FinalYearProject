
import json
import os

import firebase_admin
from firebase_admin import credentials, auth

# initialize firebase authorization from Render env var
cred_raw = os.getenv("FIREBASE_CREDENTIALS") or os.getenv("FIREBASE_CREDENTIALS_JSON")
if not cred_raw:
    raise RuntimeError("Missing Firebase credentials env var. Set FIREBASE_CREDENTIALS or FIREBASE_CREDENTIALS_JSON on Render.")

cred = credentials.Certificate(json.loads(cred_raw))

#check if firebase app is already initialized
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

print("Firebase Auth initialized")