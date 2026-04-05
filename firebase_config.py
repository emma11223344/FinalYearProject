
import json
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, auth

# initialize firebase authorization from Render env var
cred_raw = os.getenv("FIREBASE_CREDENTIALS") or os.getenv("FIREBASE_CREDENTIALS_JSON")
if not cred_raw:
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in ("FIREBASE_CREDENTIALS", "FIREBASE_CREDENTIALS_JSON"):
                cred_raw = value
                break

if not cred_raw:
    raise RuntimeError("Missing Firebase credentials env var. Set FIREBASE_CREDENTIALS or FIREBASE_CREDENTIALS_JSON on Render.")

cred = credentials.Certificate(json.loads(cred_raw))

#check if firebase app is already initialized
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

print("Firebase Auth initialized")