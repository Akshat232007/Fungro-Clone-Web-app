import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, flash, url_for

app = Flask(__name__)
app.secret_key = "Funngro_secret_key"
DB_NAME = "database.db"

# ==============================================================================
# DATABASE HELPERS
# ==============================================================================

def get_db():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema and creates the default admin user."""
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
            deadline TEXT,
            business_id INTEGER,
            created_at DATE DEFAULT CURRENT_DATE
        );
        CREATE TABLE IF NOT EXISTS applications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id INTEGER,
            status TEXT,
            applied_date TEXT
        );
        CREATE TABLE IF NOT EXISTS submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER,
            work_link TEXT,
            submitted_date TEXT
        );
        CREATE TABLE IF NOT EXISTS earnings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            task_id INTEGER,
            earned_date TEXT
        );
    """)
    
    # Create default admin if not exists
    admin_exists = c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone()
    if not admin_exists:
        c.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            ("Super Admin", "admin@Funngro.com", "admin123", "admin")
        )
        
    conn.commit()
    conn.close()

# ==============================================================================
# AUTHENTICATION ROUTES
# ==============================================================================

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(f"/{session['role']}/home")
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (request.form["email"], request.form["password"])
        ).fetchone()
        conn.close()
        
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(f"/{user['role']}/home")
            
        flash("Invalid credentials", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                (request.form["name"], request.form["email"], request.form["password"], request.form["role"])
            )
            conn.commit()
            flash("Account created! Please login.", "success")
            return redirect("/login")
        except sqlite3.IntegrityError:
            flash("Email already exists.", "error")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ==============================================================================
# TEEN ROUTES
# ==============================================================================

@app.route("/teen/home")
def teen_home():
    if session.get("role") != "teen":
        return redirect("/login")
        
    conn = get_db()
    
    # Get available tasks not already applied for
    tasks_query = """
        SELECT t.*, u.name as business 
        FROM tasks t 
        JOIN users u ON t.business_id = u.id 
        WHERE date(t.deadline) >= date('now') 
        AND t.id NOT IN (SELECT task_id FROM applications WHERE user_id = ?)
    """
    tasks = conn.execute(tasks_query, (session["user_id"],)).fetchall()
    
    # Get user's current applications
    apps_query = """
        SELECT a.*, t.title, t.payment 
        FROM applications a 
        JOIN tasks t ON a.task_id = t.id 
        WHERE a.user_id = ?
    """
    apps = conn.execute(apps_query, (session["user_id"],)).fetchall()
    
    # Calculate total earnings
    earnings = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM earnings WHERE user_id=?", 
        (session["user_id"],)
    ).fetchone()[0]
    
    conn.close()
    return render_template("teen_home.html", tasks=tasks, apps=apps, earnings=earnings)

@app.route("/teen/apply/<int:task_id>")
def apply_task(task_id):
    conn = get_db()
    conn.execute(
        "INSERT INTO applications (user_id, task_id, status, applied_date) VALUES (?, ?, ?, ?)",
        (session["user_id"], task_id, "Pending", datetime.now().date())
    )
    conn.commit()
    flash("Mission Accepted!", "success")
    return redirect("/teen/home")

@app.route("/teen/submit/<int:app_id>", methods=["GET", "POST"])
def submit_task(app_id):
    conn = get_db()
    if request.method == "POST":
        conn.execute(
            "INSERT INTO submissions (application_id, work_link, submitted_date) VALUES (?, ?, ?)",
            (app_id, request.form["work_link"], datetime.now().date())
        )
        conn.execute("UPDATE applications SET status='Submitted' WHERE id=?", (app_id,))
        conn.commit()
        flash("Mission Accomplished!", "success")
        return redirect("/teen/home")
        
    app_data = conn.execute(
        "SELECT a.*, t.title, t.description, t.payment FROM applications a JOIN tasks t ON a.task_id=t.id WHERE a.id=?",
        (app_id,)
    ).fetchone()
    conn.close()
    return render_template("submit_task.html", app=app_data)

# ==============================================================================
# BUSINESS ROUTES
# ==============================================================================

@app.route("/business/home")
def business_home():
    if session.get("role") != "business":
        return redirect("/login")
        
    conn = get_db()
    apps_query = """
        SELECT a.*, t.title, u.name as teen, s.work_link 
        FROM applications a 
        JOIN tasks t ON a.task_id = t.id 
        JOIN users u ON a.user_id = u.id 
        LEFT JOIN submissions s ON s.application_id = a.id 
        WHERE t.business_id = ?
    """
    apps = conn.execute(apps_query, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("business_home.html", apps=apps)

@app.route("/business/tasks")
def business_tasks():
    conn = get_db()
    tasks = conn.execute(
        "SELECT * FROM tasks WHERE business_id=? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    return render_template("business_tasks.html", tasks=tasks)

@app.route("/business/post", methods=["GET", "POST"])
def post_task():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "INSERT INTO tasks (title, description, payment, deadline, business_id) VALUES (?, ?, ?, ?, ?)",
            (request.form["title"], request.form["description"], request.form["payment"], request.form["deadline"], session["user_id"])
        )
        conn.commit()
        return redirect("/business/tasks")
    return render_template("post_task.html")

@app.route("/business/approve/<int:app_id>")
def approve_task(app_id):
    conn = get_db()
    data = conn.execute(
        "SELECT a.user_id, t.payment, t.id FROM applications a JOIN tasks t ON a.task_id=t.id WHERE a.id=?",
        (app_id,)
    ).fetchone()
    
    conn.execute("UPDATE applications SET status='Approved' WHERE id=?", (app_id,))
    conn.execute(
        "INSERT INTO earnings (user_id, amount, task_id, earned_date) VALUES (?, ?, ?, ?)",
        (data["user_id"], data["payment"], data["id"], datetime.now().date())
    )
    conn.commit()
    return redirect("/business/home")

# ==============================================================================
# ADMIN ROUTES
# ==============================================================================

@app.route("/admin/home")
def admin_home():
    if session.get("role") != "admin":
        return redirect("/login")
        
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    tasks = conn.execute(
        "SELECT t.*, u.name as business_name FROM tasks t JOIN users u ON t.business_id = u.id"
    ).fetchall()
    apps = conn.execute("""
        SELECT a.*, t.title, u.name as teen_name, t.payment 
        FROM applications a 
        JOIN tasks t ON a.task_id = t.id 
        JOIN users u ON a.user_id = u.id
    """).fetchall()
    
    return render_template("admin.html", users=users, tasks=tasks, applications=apps)

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    init_db()
    app.run(debug=True)