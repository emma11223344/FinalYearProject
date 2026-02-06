from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/phishing-email')
def phishing_email():
    return render_template('phishing_email.html')

@app.route('/fake-login')
def fake_login():
    return render_template('fake_login.html')

@app.route('/awareness')
def awareness():
    return render_template('awareness.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/report')
def report():
    return render_template('report.html')

if __name__ == '__main__':
    app.run(debug=True)
