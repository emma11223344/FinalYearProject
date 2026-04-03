from firebase import db

print("Starting Firebase test...")

db.collection("test").add({
    "name": "Emma",
    "project": "Final Year"
})

print("Data added to Firebase")