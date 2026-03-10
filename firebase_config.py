
import firebase_admin
from firebase_admin import credentials, auth

#initialize firebase authorisation
cred = credentials.Certificate("fyp-2026-47ce8-firebase-adminsdk-fbsvc-8a46a9f49d.json")

#check if firebase app is already initialized
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

print("Firebase Auth initialized")