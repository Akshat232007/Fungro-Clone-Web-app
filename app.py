import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "Funngro_secret_key"
DB_NAME = "database.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            payment REAL,
            deadline DATE,
            business_id INTEGER,
            created_at DATE DEFAULT CURRENT_DATE
        );
        CREATE TABLE IF NOT EXISTS applications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id INTEGER,
            status TEXT,
            applied_date DATE
        );
        CREATE TABLE IF NOT EXISTS submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER,
            work_link TEXT,
            submitted_date DATE
        );
        CREATE TABLE IF NOT EXISTS earnings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            task_id INTEGER,
            earned_date DATE
        );
    """)
    admin = c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone()
    if not admin:
        c.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                 ("Super Admin", "admin@funngro.com", generate_password_hash("Admin@123"), "admin"))
    conn.commit()
    conn.close()

# --- AUTH ---
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for(f"{session['role']}_home"))
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (request.form["email"],)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], request.form["password"]):
            session.clear()
            session["user_id"], session["name"], session["role"] = user["id"], user["name"], user["role"]
            return redirect(url_for(f"{user['role']}_home"))
        flash("Invalid credentials", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            conn = get_db()
            conn.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                        (request.form["name"], request.form["email"], 
                         generate_password_hash(request.form["password"]), request.form["role"]))
            conn.commit()
            conn.close()
            flash("Account created! Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already exists", "error")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- TEEN ROUTES ---
@app.route("/teen/home")
def teen_home():
    if session.get("role") != "teen": return redirect(url_for("login"))
    conn = get_db()
    tasks = conn.execute("""SELECT t.*, u.name AS business FROM tasks t JOIN users u ON t.business_id = u.id 
                            WHERE date(t.deadline) >= date('now') 
                            AND t.id NOT IN (SELECT task_id FROM applications WHERE user_id=?)""", 
                         (session["user_id"],)).fetchall()
    apps = conn.execute("""SELECT a.*, t.title, t.payment FROM applications a 
                           JOIN tasks t ON a.task_id = t.id WHERE a.user_id=?""", 
                        (session["user_id"],)).fetchall()
    earnings = conn.execute("SELECT COALESCE(SUM(amount),0) FROM earnings WHERE user_id=?", 
                            (session["user_id"],)).fetchone()[0]
    conn.close()
    return render_template("teen_home.html", tasks=tasks, apps=apps, earnings=earnings)

@app.route("/teen/apply/<int:task_id>")
def apply_task(task_id):
    if session.get("role") != "teen": return redirect(url_for("login"))
    conn = get_db()
    conn.execute("INSERT INTO applications (user_id, task_id, status, applied_date) VALUES (?,?,?,?)",
                (session["user_id"], task_id, "Pending", datetime.now().date()))
    conn.commit()
    conn.close()
    flash("Mission Accepted!", "success")
    return redirect(url_for("teen_home"))

@app.route("/teen/submit/<int:app_id>", methods=["GET", "POST"])
def submit_task(app_id):
    if session.get("role") != "teen": return redirect(url_for("login"))
    conn = get_db()
    if request.method == "POST":
        conn.execute("INSERT INTO submissions (application_id, work_link, submitted_date) VALUES (?,?,?)",
                    (app_id, request.form["work_link"], datetime.now().date()))
        conn.execute("UPDATE applications SET status='Submitted' WHERE id=?", (app_id,))
        conn.commit()
        conn.close()
        flash("Work submitted!", "success")
        return redirect(url_for("teen_home"))
    
    app_data = conn.execute("SELECT a.*, t.title, t.description, t.payment FROM applications a JOIN tasks t ON a.task_id=t.id WHERE a.id=?", (app_id,)).fetchone()
    conn.close()
    return render_template("submit_task.html", app=app_data)

# --- BUSINESS ROUTES ---
@app.route("/business/home")
def business_home():
    if session.get("role") != "business": return redirect(url_for("login"))
    conn = get_db()
    apps = conn.execute("""SELECT a.*, t.title, u.name AS teen, s.work_link FROM applications a 
                           JOIN tasks t ON a.task_id=t.id JOIN users u ON a.user_id=u.id 
                           LEFT JOIN submissions s ON s.application_id=a.id WHERE t.business_id=?""", 
                        (session["user_id"],)).fetchall()
    conn.close()
    return render_template("business_home.html", apps=apps)

@app.route("/business/post", methods=["GET", "POST"])
def post_task():
    if session.get("role") != "business": return redirect(url_for("login"))
    if request.method == "POST":
        conn = get_db()
        conn.execute("INSERT INTO tasks (title, description, payment, deadline, business_id) VALUES (?,?,?,?,?)",
                    (request.form["title"], request.form["description"], request.form["payment"], 
                     request.form["deadline"], session["user_id"]))
        conn.commit()
        conn.close()
        flash("Mission Launched!", "success")
        return redirect(url_for("business_home"))
    return render_template("post_task.html")

@app.route("/business/tasks")
def business_tasks():
    if session.get("role") != "business": return redirect(url_for("login"))
    conn = get_db()
    tasks = conn.execute("SELECT * FROM tasks WHERE business_id=?", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("business_tasks.html", tasks=tasks)

@app.route("/business/approve/<int:app_id>")
def approve_task(app_id):
    conn = get_db()
    data = conn.execute("SELECT a.user_id, t.payment, t.id FROM applications a JOIN tasks t ON a.task_id=t.id WHERE a.id=?", (app_id,)).fetchone()
    conn.execute("UPDATE applications SET status='Approved' WHERE id=?", (app_id,))
    conn.execute("INSERT INTO earnings (user_id, amount, task_id, earned_date) VALUES (?,?,?,?)",
                (data["user_id"], data["payment"], data["id"], datetime.now().date()))
    conn.commit()
    conn.close()
    flash("Payment released!", "success")
    return redirect(url_for("business_home"))

# --- ADMIN ROUTES ---
@app.route("/admin/home")
def admin_home():
    if session.get("role") != "admin": return redirect(url_for("login"))
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    tasks = conn.execute("SELECT t.*, u.name AS business_name FROM tasks t JOIN users u ON t.business_id=u.id").fetchall()
    apps = conn.execute("SELECT a.*, t.title, u.name AS teen_name FROM applications a JOIN tasks t ON a.task_id=t.id JOIN users u ON a.user_id=u.id").fetchall()
    conn.close()
    return render_template("admin.html", users=users, tasks=tasks, applications=apps)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
