import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional
from flask import Flask, abort, g, make_response, render_template, request, redirect, url_for

APP_TZ = timezone(timedelta(hours=5, minutes=30))  # Asia/Colombo
DB_PATH = "drinks.db"
ADMIN_KEY = os.getenv("ADMIN_KEY", "changeme")

app = Flask(__name__)

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_: Optional[BaseException] = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db() -> None:
    db = get_db()
    db.execute(
        '''CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            drink TEXT NOT NULL,
            session TEXT NOT NULL,
            qty INTEGER NOT NULL,
            ts_utc TEXT NOT NULL,
            local_date TEXT NOT NULL
        )'''
    )
    db.commit()

with app.app_context():
    init_db()

@app.route('/', methods=['GET'])
def index():
    names = ["Abiru", "Anushka", "Bimal", "Chathuri", "Damayanthi", "Dilshan", "Gayan",
             "Ishara", "Kamal", "Kavindi", "Lakshitha", "Malini", "Nuwan", "Panduka", "Tharindu"]
    drinks = ["Tea", "Coffee", "Milk Tea", "Milk Coffee"]
    return render_template('index.html', names=names, drinks=drinks)

@app.route('/submit', methods=['POST'])
def submit():
    name = request.form.get("name", "").strip()
    drink = request.form.get("drink", "").strip()
    session = request.form.get("session", "").strip()
    qty_raw = request.form.get("qty", "1").strip()

    if not name or not drink or session not in ("AM", "PM"):
        return "Missing or invalid fields.", 400
    try:
        qty = int(qty_raw)
        if qty < 1 or qty > 10:
            raise ValueError()
    except ValueError:
        return "Quantity must be 1-10.", 400

    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    local_date = datetime.now(APP_TZ).strftime("%Y-%m-%d")

    db = get_db()
    db.execute(
        "INSERT INTO entries (name, drink, session, qty, ts_utc, local_date) VALUES (?, ?, ?, ?, ?, ?)",
        (name, drink, session, qty, now_utc, local_date)
    )
    db.commit()
    return redirect(url_for('thanks'))

@app.route('/thanks')
def thanks():
    return render_template('thanks.html')

def require_admin():
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        abort(403)

@app.route('/summary')
def summary():
    require_admin()
    date_q = request.args.get("date") or datetime.now(APP_TZ).strftime("%Y-%m-%d")

    db = get_db()
    grouped = db.execute(
        "SELECT drink, session, SUM(qty) as total FROM entries WHERE local_date = ? GROUP BY drink, session ORDER BY session, drink",
        (date_q,)
    ).fetchall()
    per_person = db.execute(
        "SELECT name, drink, session, SUM(qty) as total FROM entries WHERE local_date = ? GROUP BY name, drink, session ORDER BY name",
        (date_q,)
    ).fetchall()
    total_today = db.execute(
        "SELECT SUM(qty) FROM entries WHERE local_date = ?",
        (date_q,)
    ).fetchone()[0] or 0

    return render_template('summary.html', date=date_q, grouped=grouped, per_person=per_person, total_today=total_today)

@app.route('/export.csv')
def export_csv():
    require_admin()
    date_from = request.args.get("from", "1970-01-01")
    date_to = request.args.get("to", "2100-01-01")
    db = get_db()
    rows = db.execute(
        "SELECT id, local_date, ts_utc, name, drink, session, qty FROM entries WHERE local_date BETWEEN ? AND ? ORDER BY local_date, id",
        (date_from, date_to)
    ).fetchall()

    header = ["id", "local_date", "ts_utc", "name", "drink", "session", "qty"]
    lines = [",".join(header)]
    for r in rows:
        lines.append(",".join([str(r[c]) for c in header]))

    resp = make_response("\n".join(lines))
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=drinks.csv"
    return resp

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
