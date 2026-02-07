# main.py
import sqlite3
import hashlib
import csv
from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivy.uix.popup import Popup
from kivy.uix.label import Label

DB_FILE = "finance.db"


# ---------------- Database helpers ----------------
def get_conn():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            label TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER NOT NULL,
            to_user INTEGER NOT NULL,
            amount REAL NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(from_user) REFERENCES users(id),
            FOREIGN KEY(to_user) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def popup(title: str, text: str):
    Popup(title=title, content=Label(text=text), size_hint=(0.8, 0.4)).open()


# ---------------- Screens ----------------
class LoginScreen(Screen):
    def do_login(self):
        uname = self.ids.login_username.text.strip()
        pw = self.ids.login_password.text.strip()
        if not uname or not pw:
            popup("Error", "Enter username and password")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE username=?", (uname,))
        row = c.fetchone()
        conn.close()
        if not row or row[1] != hash_pw(pw):
            popup("Error", "Invalid credentials")
            return
        app = App.get_running_app()
        app.user_id, app.username = row[0], uname
        app.refresh_menu()
        app.root.current = "menu"

    def goto_register(self):
        self.manager.current = "register"

    def goto_forgot(self):
        self.manager.current = "forgot"


class RegisterScreen(Screen):
    def do_register(self):
        uname = self.ids.reg_username.text.strip()
        pw = self.ids.reg_password.text.strip()
        if not uname or not pw:
            popup("Error", "Enter username and password")
            return
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users(username, password) VALUES(?,?)", (uname, hash_pw(pw)))
            conn.commit()
            popup("Success", "Registered — please login")
            self.manager.current = "login"
        except sqlite3.IntegrityError:
            popup("Error", "Username already exists")
        finally:
            conn.close()


class ForgotPasswordScreen(Screen):
    def reset_pw(self):
        uname = self.ids.forgot_username.text.strip()
        new_pw = self.ids.forgot_newpw.text.strip()
        if not uname or not new_pw:
            popup("Error", "Enter username and new password")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE username=?", (hash_pw(new_pw), uname))
        if c.rowcount == 0:
            popup("Error", "Username not found")
        else:
            popup("Success", "Password reset successfully")
            self.manager.current = "login"
        conn.commit()
        conn.close()


class MenuScreen(Screen):
    pass


class AddBalanceScreen(Screen):
    def save_balance(self):
        amt_text = self.ids.add_amount.text.strip()
        label = self.ids.add_label.text.strip() or "Deposit"
        if not amt_text:
            popup("Error", "Enter amount")
            return
        try:
            amt = float(amt_text)
            if amt <= 0:
                raise ValueError
        except ValueError:
            popup("Error", "Invalid amount")
            return
        app = App.get_running_app()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_conn()
        conn.execute("INSERT INTO balances(user_id, amount, label, timestamp) VALUES(?,?,?,?)",
                     (app.user_id, amt, label, ts))
        conn.commit()
        conn.close()
        popup("Success", f"₹{amt:.2f} added")
        app.refresh_menu()
        self.ids.add_amount.text = ""
        self.ids.add_label.text = ""


class TransferScreen(Screen):
    def do_transfer(self):
        to_uname = self.ids.to_username.text.strip()
        amt_text = self.ids.transfer_amount.text.strip()
        if not to_uname or not amt_text:
            popup("Error", "Enter recipient and amount")
            return
        try:
            amt = float(amt_text)
            if amt <= 0:
                raise ValueError
        except ValueError:
            popup("Error", "Invalid amount")
            return
        app = App.get_running_app()
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (to_uname,))
        row = c.fetchone()
        if not row:
            popup("Error", "Recipient not found")
            conn.close()
            return
        to_id = row[0]
        if to_id == app.user_id:
            popup("Error", "Cannot transfer to yourself")
            conn.close()
            return
        c.execute("SELECT COALESCE(SUM(amount),0) FROM balances WHERE user_id=?", (app.user_id,))
        balance = c.fetchone()[0]
        if amt > balance:
            popup("Error", "Insufficient balance")
            conn.close()
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO balances(user_id, amount, label, timestamp) VALUES(?,?,?,?)",
                  (app.user_id, -amt, f"Sent to {to_uname}", ts))
        c.execute("INSERT INTO balances(user_id, amount, label, timestamp) VALUES(?,?,?,?)",
                  (to_id, amt, f"Received from {app.username}", ts))
        conn.commit()
        conn.close()
        popup("Success", f"₹{amt:.2f} sent to {to_uname}")
        app.refresh_menu()
        self.ids.to_username.text = ""
        self.ids.transfer_amount.text = ""


class HistoryScreen(Screen):
    def on_pre_enter(self):
        self.load_history()

    def load_history(self):
        app = App.get_running_app()
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, amount, label, timestamp FROM balances WHERE user_id=? ORDER BY id ASC", (app.user_id,))
        rows = c.fetchall()
        conn.close()
        container = self.ids.history_list
        container.clear_widgets()
        header = Label(text="No | Name | Deposit/Received | Date/Time",
                       bold=True, size_hint_y=None, height=30)
        container.add_widget(header)
        for r in rows:
            no, amt, label, ts = r
            txt = f"{no} | {label} | ₹{amt:.2f} | {ts}"
            container.add_widget(Label(text=txt, size_hint_y=None, height=25))

    def export_csv(self):
        app = App.get_running_app()
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, amount, label, timestamp FROM balances WHERE user_id=? ORDER BY id ASC", (app.user_id,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            popup("Info", "No data to export")
            return
        out_dir = Path.cwd() / "exports"
        out_dir.mkdir(exist_ok=True)
        filename = out_dir / f"{app.username}_history.csv"
        with open(filename, "w", newline='', encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["No", "Label", "Amount", "Date/Time"])
            for no, amt, label, ts in rows:
                writer.writerow([no, label, amt, ts])
        popup("Exported", f"CSV saved at:\n{filename}")


# ---------------- Main App ----------------
class FinanceApp(App):
    user_id = None
    username = None

    def build(self):
        init_db()
        self.sm = Builder.load_file("main.kv")
        return self.sm

    def refresh_menu(self):
        if not self.user_id:
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(amount),0) FROM balances WHERE user_id=?", (self.user_id,))
        bal = c.fetchone()[0]
        conn.close()
        menu = self.sm.get_screen("menu")
        menu.ids.welcome_label.text = f"Welcome, {self.username}"
        menu.ids.balance_label.text = f"Balance: ₹{bal:.2f}"

    def logout(self):
        self.user_id = None
        self.username = None
        self.sm.current = "login"


if __name__ == "__main__":
    FinanceApp().run()
