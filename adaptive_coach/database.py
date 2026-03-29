import sqlite3
import hashlib
import os
from datetime import date, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "coach_data.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_conn()
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Per-user state
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_state (
            user_id INTEGER PRIMARY KEY,
            goal TEXT DEFAULT 'Master new skills',
            available_time REAL DEFAULT 2.0,
            streak INTEGER DEFAULT 0,
            missed_counts INTEGER DEFAULT 0,
            progress REAL DEFAULT 0.0,
            difficulty_multiplier REAL DEFAULT 1.0,
            status TEXT DEFAULT 'Normal',
            current_logic_msg TEXT DEFAULT 'Welcome! Log your first activity below.',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Per-user subjects
    c.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject_name TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Daily plans (one plan per day per user)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_date TEXT NOT NULL,
            raw_plan_text TEXT,
            day_status TEXT DEFAULT 'pending',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Individual tasks inside a daily plan
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            task_text TEXT NOT NULL,
            resource_link TEXT,
            is_completed INTEGER DEFAULT 0,
            FOREIGN KEY (plan_id) REFERENCES daily_plans(id)
        )
    """)

    # Progress history
    c.execute("""
        CREATE TABLE IF NOT EXISTS progress_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            record_date TEXT NOT NULL,
            progress_value REAL NOT NULL,
            status TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(username: str, password: str, name: str) -> dict:
    """Returns {'ok': True, 'user_id': ...} or {'ok': False, 'error': ...}."""
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, password_hash, name) VALUES (?, ?, ?)",
            (username.strip().lower(), hash_password(password), name.strip())
        )
        user_id = c.lastrowid
        # Seed default state
        c.execute("INSERT INTO user_state (user_id) VALUES (?)", (user_id,))
        # Seed default subjects
        default_subjects = ['Python', 'AWS', 'SQL']
        for s in default_subjects:
            c.execute("INSERT INTO subjects (user_id, subject_name) VALUES (?, ?)", (user_id, s))
        conn.commit()
        return {'ok': True, 'user_id': user_id}
    except sqlite3.IntegrityError:
        return {'ok': False, 'error': 'Username already exists. Please choose a different one.'}
    finally:
        conn.close()


def login_user(username: str, password: str) -> dict:
    """Returns {'ok': True, 'user_id': ..., 'name': ...} or {'ok': False, 'error': ...}."""
    conn = get_conn()
    c = conn.cursor()
    row = c.execute(
        "SELECT id, name, password_hash FROM users WHERE username = ?",
        (username.strip().lower(),)
    ).fetchone()
    conn.close()
    if row is None:
        return {'ok': False, 'error': 'Username not found.'}
    if row['password_hash'] != hash_password(password):
        return {'ok': False, 'error': 'Incorrect password.'}
    return {'ok': True, 'user_id': row['id'], 'name': row['name']}


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def get_user_state(user_id: int) -> dict:
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT * FROM user_state WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}


def update_user_state(user_id: int, updates: dict):
    if not updates:
        return
    conn = get_conn()
    c = conn.cursor()
    cols = ", ".join(f"{k} = ?" for k in updates.keys())
    vals = list(updates.values()) + [user_id]
    c.execute(f"UPDATE user_state SET {cols} WHERE user_id = ?", vals)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Subject helpers
# ---------------------------------------------------------------------------

def get_subjects(user_id: int) -> list:
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute("SELECT subject_name FROM subjects WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return [r['subject_name'] for r in rows]


def set_subjects(user_id: int, subjects: list):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM subjects WHERE user_id = ?", (user_id,))
    for s in subjects:
        c.execute("INSERT INTO subjects (user_id, subject_name) VALUES (?, ?)", (user_id, s.strip()))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Daily Plan helpers
# ---------------------------------------------------------------------------

def get_current_plan(user_id: int) -> int:
    """Gets the active pending plan, or creates a new one for the 'next' sequential date."""
    conn = get_conn()
    c = conn.cursor()
    
    # 1. Check for an active pending plan
    row = c.execute(
        "SELECT id FROM daily_plans WHERE user_id = ? AND day_status = 'pending' ORDER BY plan_date DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    if row:
        conn.close()
        return row['id']
        
    # 2. If no pending plan, find the last recorded plan to increment its date
    latest = c.execute(
        "SELECT plan_date FROM daily_plans WHERE user_id = ? ORDER BY plan_date DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    
    from datetime import timedelta
    if latest:
        try:
            latest_date = date.fromisoformat(latest['plan_date'])
            next_date = (latest_date + timedelta(days=1)).isoformat()
        except ValueError:
            next_date = date.today().isoformat()
    else:
        next_date = date.today().isoformat()
        
    c.execute(
        "INSERT INTO daily_plans (user_id, plan_date, day_status) VALUES (?, ?, 'pending')",
        (user_id, next_date)
    )
    plan_id = c.lastrowid
    conn.commit()
    conn.close()
    return plan_id


def get_plan_date(plan_id: int) -> str:
    """Helper to get the actual date assigned to a plan."""
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT plan_date FROM daily_plans WHERE id = ?", (plan_id,)).fetchone()
    conn.close()
    return row['plan_date'] if row else date.today().isoformat()


def save_plan_tasks(plan_id: int, tasks: list):
    """Replaces all tasks for a plan with a new list of dicts: {task_text, resource_link}."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE plan_id = ?", (plan_id,))
    for t in tasks:
        c.execute(
            "INSERT INTO tasks (plan_id, task_text, resource_link, is_completed) VALUES (?, ?, ?, 0)",
            (plan_id, t.get('task_text', ''), t.get('resource_link', ''))
        )
    conn.commit()
    conn.close()


def get_plan_tasks(plan_id: int) -> list:
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute("SELECT * FROM tasks WHERE plan_id = ?", (plan_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_task_completion(task_id: int, is_completed: bool):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE tasks SET is_completed = ? WHERE id = ?", (1 if is_completed else 0, task_id))
    conn.commit()
    conn.close()


def update_plan_text(plan_id: int, raw_text: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE daily_plans SET raw_plan_text = ? WHERE id = ?", (raw_text, plan_id))
    conn.commit()
    conn.close()


def get_plan_text(plan_id: int) -> str:
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT raw_plan_text FROM daily_plans WHERE id = ?", (plan_id,)).fetchone()
    conn.close()
    return row['raw_plan_text'] if row and row['raw_plan_text'] else ''


def update_plan_status(plan_id: int, status: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE daily_plans SET day_status = ? WHERE id = ?", (status, plan_id))
    conn.commit()
    conn.close()


def get_past_completed_tasks(user_id: int, limit: int = 3) -> list:
    """Return tasks from the last N completed/missed plans (for context injection)."""
    conn = get_conn()
    c = conn.cursor()
    plans = c.execute(
        """SELECT id, plan_date, day_status FROM daily_plans
           WHERE user_id = ? AND day_status != 'pending'
           ORDER BY plan_date DESC LIMIT ?""",
        (user_id, limit)
    ).fetchall()
    result = []
    for plan in plans:
        tasks = c.execute(
            "SELECT task_text FROM tasks WHERE plan_id = ? AND is_completed = 1",
            (plan['id'],)
        ).fetchall()
        result.append({
            'date': plan['plan_date'],
            'status': plan['day_status'],
            'tasks': [t['task_text'] for t in tasks]
        })
    conn.close()
    return result


# ---------------------------------------------------------------------------
# Progress History
# ---------------------------------------------------------------------------

def record_progress(user_id: int, progress_value: float, status: str, record_date: str):
    conn = get_conn()
    c = conn.cursor()
    # Upsert: one record per user per simulated day
    existing = c.execute(
        "SELECT id FROM progress_history WHERE user_id = ? AND record_date = ?",
        (user_id, record_date)
    ).fetchone()
    if existing:
        c.execute(
            "UPDATE progress_history SET progress_value = ?, status = ? WHERE id = ?",
            (progress_value, status, existing['id'])
        )
    else:
        c.execute(
            "INSERT INTO progress_history (user_id, record_date, progress_value, status) VALUES (?, ?, ?, ?)",
            (user_id, record_date, progress_value, status)
        )
    conn.commit()
    conn.close()


def get_progress_history(user_id: int, limit: int = 30) -> list:
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute(
        """SELECT record_date, progress_value, status FROM progress_history
           WHERE user_id = ? ORDER BY record_date DESC LIMIT ?""",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]
