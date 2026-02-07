from flask import Flask, request, jsonify
import sqlite3
import hashlib
from datetime import datetime

app = Flask(__name__)
DB_FILE = "finance.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    hashed = hashlib.sha256(password.encode()).hexdigest()
    
    try:
        conn = get_db()
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        conn.commit()
        return jsonify({"message": "User created"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username exists"}), 400

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    hashed = hashlib.sha256(password.encode()).hexdigest()
    
    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE username=? AND password=?", (username, hashed)).fetchone()
    if user:
        return jsonify({"user_id": user['id'], "username": username}), 200
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/balance/<int:user_id>', methods=['GET'])
def get_balance(user_id):
    conn = get_db()
    row = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM balances WHERE user_id=?", (user_id,)).fetchone()
    return jsonify({"balance": row['total']})

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    data = request.json
    conn = get_db()
    conn.execute("INSERT INTO balances (user_id, amount, label, timestamp) VALUES (?, ?, ?, ?)",
                 (data['user_id'], data['amount'], data['label'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    return jsonify({"message": "Success"}), 201

if __name__ == '__main__':
    app.run(debug=True, port=5000)