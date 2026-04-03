import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("fyp-2026-47ce8-firebase-adminsdk-fbsvc-8a46a9f49d.json")

firebase_admin.initialize_app(cred)

db = firestore.client()