from firebase_admin import auth
import firebase_config

try:
    # create a new user
    user = auth.create_user(
        email="emma@example.com",
        password="password123"
    )

    print("User created:", user.uid)

except Exception as e:
    print("Error creating user:", e)