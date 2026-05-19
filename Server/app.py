from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import re
import subprocess
import shlex
import threading
import time
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from flask import (
    Flask,
    Response,
    g,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from logging_client import get_logging_client, init_logging_client

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(__file__).resolve().parents[1] / "Database" / "server.db"

app = Flask(__name__)
app.config["DATABASE"] = str(DB_PATH)
app.config["SECRET_KEY"] = "change-me"

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
init_logging_client('main-api')

RUNNING_PROCESSES: dict[int, subprocess.Popen[str]] = {}
PROCESS_LOCK = threading.Lock()
API_SYSTEM_ENABLED = True
API_SYSTEM_LOCK = threading.Lock()
MODULE_KEYS = ["info", "stats", "arp", "ping", "terminal", "plc"]
STUDENT_CATEGORIES = {"student", "authorized_student", "student_plus"}
TEACHER_CATEGORIES = {"teacher", "authorized_teacher", "teacher_plus"}
SUPER_AUTHOR_USERNAME = "SanderMaes26"
PRIVILEGED_ROLES = {"author", "admin", "iter"}
PLC_IO_STATE: dict[int, list[dict[str, object]]] = {}
PLC_IO_LOCK = threading.Lock()


# Middleware for logging API requests
@app.before_request
def before_request_logging():
    """Record request start time"""
    g.request_start_time = time.time()


@app.after_request
def after_request_logging(response):
    """Log API request after response is sent"""
    if request.path.startswith('/api/'):
        try:
            response_time_ms = (time.time() - g.request_start_time) * 1000
            user_id = session.get('user_id')
            
            metadata = {
                'response_size': len(response.get_data()),
                'user_agent': request.headers.get('User-Agent'),
                'remote_addr': request.remote_addr,
                'catalog_id': 'Succes' if response.status_code < 400 else 'Failed'
            }

            get_logging_client().log_api_request(
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                user_id=user_id,
                metadata=metadata
            )
        except Exception as e:
            logger.debug(f"Error logging request: {e}")
    
    return response


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(app.config["DATABASE"])
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            category TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            theme TEXT NOT NULL,
            layout_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            mac_address TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id INTEGER PRIMARY KEY,
            can_view_devices INTEGER NOT NULL,
            can_manage_devices INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS user_module_permissions (
            user_id INTEGER NOT NULL,
            module_key TEXT NOT NULL,
            allowed INTEGER NOT NULL,
            PRIMARY KEY (user_id, module_key),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS user_device_permissions (
            user_id INTEGER NOT NULL,
            device_id INTEGER NOT NULL,
            allowed INTEGER NOT NULL,
            PRIMARY KEY (user_id, device_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (device_id) REFERENCES devices (id)
        );

        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            parent_id INTEGER,
            FOREIGN KEY (parent_id) REFERENCES groups (id)
        );

        CREATE TABLE IF NOT EXISTS user_groups (
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, group_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (group_id) REFERENCES groups (id)
        );

        CREATE TABLE IF NOT EXISTS user_device_activity (
            user_id INTEGER NOT NULL,
            device_id INTEGER NOT NULL,
            last_seen TEXT NOT NULL,
            PRIMARY KEY (user_id, device_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (device_id) REFERENCES devices (id)
        );

        CREATE TABLE IF NOT EXISTS password_reset_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            handled_at TEXT,
            handled_by_user_id INTEGER,
            FOREIGN KEY (handled_by_user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS plc_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            tag TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(device_id, tag),
            FOREIGN KEY (device_id) REFERENCES devices (id)
        );
        """
    )
    columns = [row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()]
    if "role" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    if "category" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN category TEXT NOT NULL DEFAULT 'student'")
    device_columns = [row[1] for row in db.execute("PRAGMA table_info(devices)").fetchall()]
    if "mac_address" not in device_columns:
        db.execute("ALTER TABLE devices ADD COLUMN mac_address TEXT")
    group_columns = [row[1] for row in db.execute("PRAGMA table_info(groups)").fetchall()]
    if "parent_id" not in group_columns:
        db.execute("ALTER TABLE groups ADD COLUMN parent_id INTEGER")
    db.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        ("test", generate_password_hash("123"), datetime.utcnow().isoformat()),
    )
    db.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        ("SanderMaes26", generate_password_hash("Test123"), datetime.utcnow().isoformat()),
    )
    db.execute("UPDATE users SET role = 'author' WHERE username = ?", (SUPER_AUTHOR_USERNAME,))
    db.execute(
        "UPDATE users SET role = 'admin' WHERE LOWER(username) != LOWER(?) AND role = 'author'",
        (SUPER_AUTHOR_USERNAME,),
    )
    db.commit()
    db.close()


@app.before_request
def ensure_db() -> None:
    if app.config.get("DB_READY"):
        return
    os.makedirs(DB_PATH.parent, exist_ok=True)
    init_db()
    app.config["DB_READY"] = True


def is_admin_user(user_id: int) -> bool:
    db = get_db()
    row = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    return row is not None and row["role"] in PRIVILEGED_ROLES


def is_super_author_user_id(user_id: int) -> bool:
    db = get_db()
    row = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return False
    return str(row["username"]).strip().lower() == SUPER_AUTHOR_USERNAME.lower()


def is_authorized_teacher(user_id: int) -> bool:
    db = get_db()
    row = db.execute("SELECT category FROM users WHERE id = ?", (user_id,)).fetchone()
    return row is not None and row["category"] in {"authorized_teacher", "teacher_plus"}


def normalize_category(category: str) -> str:
    normalized = str(category).strip().lower()
    if normalized == "teacher_plus":
        return "authorized_teacher"
    if normalized == "student_plus":
        return "authorized_student"
    return normalized


def is_student_category(category: str) -> bool:
    return normalize_category(category) in {"student", "authorized_student"}


def can_manage_student_settings(actor_id: int, target_id: int) -> bool:
    if is_admin_user(actor_id):
        return True
    if not is_authorized_teacher(actor_id):
        return False

    db = get_db()
    target = db.execute(
        "SELECT role, category FROM users WHERE id = ?",
        (target_id,),
    ).fetchone()
    if not target:
        return False

    if target["role"] in {"admin", "iter"}:
        return False
    if not is_student_category(target["category"]):
        return False

    allowed_groups = get_authorized_group_ids(actor_id)
    if not allowed_groups:
        return False
    target_groups = db.execute(
        "SELECT group_id FROM user_groups WHERE user_id = ?",
        (target_id,),
    ).fetchall()
    target_group_ids = {row["group_id"] for row in target_groups if row["group_id"]}
    return len(allowed_groups.intersection(target_group_ids)) > 0


def get_authorized_group_ids(user_id: int) -> set[int]:
    db = get_db()
    rows = db.execute(
        "SELECT group_id FROM user_groups WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    base_ids = {row["group_id"] for row in rows if row["group_id"]}
    if not base_ids:
        return set()
    group_rows = db.execute("SELECT id, parent_id FROM groups").fetchall()
    children_map: dict[int, list[int]] = {}
    for row in group_rows:
        parent_id = row["parent_id"] or 0
        children_map.setdefault(parent_id, []).append(row["id"])
    allowed = set(base_ids)
    queue = list(base_ids)
    while queue:
        current = queue.pop()
        for child_id in children_map.get(current, []):
            if child_id in allowed:
                continue
            allowed.add(child_id)
            queue.append(child_id)
    return allowed


def get_group_ancestor_ids(group_id: int) -> list[int]:
    db = get_db()
    rows = db.execute("SELECT id, parent_id FROM groups").fetchall()
    parent_map = {row["id"]: row["parent_id"] for row in rows}
    ancestors: list[int] = []
    current = group_id
    visited: set[int] = set()
    while current and current not in visited:
        visited.add(current)
        parent_id = parent_map.get(current)
        if parent_id:
            ancestors.append(parent_id)
        current = parent_id or 0
    return ancestors


def ensure_user_permissions(user_id: int) -> None:
    db = get_db()
    user_row = db.execute(
        "SELECT role, category FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not user_row:
        return

    role = user_row["role"] or "user"
    category = normalize_category(user_row["category"] or "student")

    default_can_view = 1
    default_can_manage = 1
    if category in {"student", "authorized_student"}:
        default_can_view = 0
        default_can_manage = 0
    if role in PRIVILEGED_ROLES:
        default_can_view = 1
        default_can_manage = 1

    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT OR IGNORE INTO user_permissions (user_id, can_view_devices, can_manage_devices, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, default_can_view, default_can_manage, now),
    )
    db.commit()


def get_allowed_modules(user_id: int) -> set[str]:
    db = get_db()
    rows = db.execute(
        "SELECT module_key, allowed FROM user_module_permissions WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    if not rows:
        category_row = db.execute(
            "SELECT category FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        category = normalize_category(category_row["category"]) if category_row else "student"
        if category in {"student", "authorized_student"}:
            return set()
        return set(MODULE_KEYS)
    category_row = db.execute(
        "SELECT category FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    category = normalize_category(category_row["category"]) if category_row else "student"
    stored_permissions = {}
    for row in rows:
        key = row["module_key"]
        if key == "notes":
            key = "info"
        stored_permissions[key] = bool(row["allowed"])

    if category in {"student", "authorized_student"}:
        return {key for key, allowed in stored_permissions.items() if allowed}

    mapped = set()
    for key in MODULE_KEYS:
        if stored_permissions.get(key, True):
            mapped.add(key)
    return mapped


def get_device_access(user_id: int) -> set[int] | None:
    db = get_db()
    rows = db.execute(
        "SELECT device_id, allowed FROM user_device_permissions WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    if not rows:
        category_row = db.execute(
            "SELECT category FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        category = normalize_category(category_row["category"]) if category_row else "student"
        if category in {"student", "authorized_student"}:
            return set()
        return None
    return {row["device_id"] for row in rows if row["allowed"]}


def get_user_permissions(user_id: int) -> dict[str, object]:
    ensure_user_permissions(user_id)
    db = get_db()
    row = db.execute(
        "SELECT can_view_devices, can_manage_devices FROM user_permissions WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    category_row = db.execute(
        "SELECT category FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    category = normalize_category(category_row["category"]) if category_row else "student"
    can_view_devices = bool(row["can_view_devices"]) if row else category not in {"student", "authorized_student"}
    can_manage_devices = bool(row["can_manage_devices"]) if row else category not in {"student", "authorized_student"}
    allowed_modules = list(get_allowed_modules(user_id))
    device_access = get_device_access(user_id)
    is_admin = is_admin_user(user_id)
    can_view_accounts = is_admin or category == "authorized_teacher"
    can_manage_student_settings = is_admin or category == "authorized_teacher"
    if is_admin:
        can_view_devices = True
        can_manage_devices = True
    return {
        "can_view_devices": can_view_devices,
        "can_manage_devices": can_manage_devices,
        "allowed_modules": allowed_modules,
        "device_access": list(device_access) if device_access is not None else None,
        "is_admin": is_admin,
        "can_view_accounts": can_view_accounts,
        "can_manage_student_settings": can_manage_student_settings,
    }


def log_device_activity(user_id: int, device_id: int) -> None:
    db = get_db()
    log_device_activity(user_id, device_id)


@app.route("/")
def index():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))
    return render_template("dashboard.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            return render_template("login.html", error="Vul alle velden in.")

        db = get_db()
        row = db.execute(
            "SELECT id, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            return render_template("login.html", error="Ongeldige login.")

        session["user_id"] = row["id"]
        return redirect(url_for("index"))

    return render_template("login.html")


@app.get("/wachtwoord-vergeten")
def wachtwoord_vergeten_pagina():
    return render_template("forgot_password.html")


@app.post("/api/auth/wachtwoord-vergeten")
def api_wachtwoord_vergeten():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    if not username:
        return {"error": "Geef een gebruikersnaam op."}, 400

    db = get_db()
    row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO password_reset_requests (username, requested_at, status) VALUES (?, ?, 'pending')",
        (username, now),
    )
    db.commit()
    if row is not None:
        logger.info("Wachtwoord-reset aangevraagd voor gebruiker: %s", username)

    return {
        "ok": True,
        "message": "Als de gebruiker bestaat, is de aanvraag geregistreerd. Contacteer een beheerder om het wachtwoord te resetten.",
    }


@app.get("/api/admin/password-reset-requests/pending-count")
def admin_password_reset_pending_count():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS count FROM password_reset_requests WHERE status = 'pending'"
    ).fetchone()
    return {"count": int(row["count"] if row else 0)}


@app.get("/api/admin/password-reset-requests")
def admin_password_reset_requests():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    status = str(request.args.get("status", "pending")).strip().lower()
    if status not in {"pending", "handled", "all"}:
        return {"error": "invalid status"}, 400

    db = get_db()
    if status == "all":
        rows = db.execute(
            """
            SELECT id, username, requested_at, status, handled_at, handled_by_user_id
            FROM password_reset_requests
            ORDER BY requested_at DESC
            LIMIT 100
            """
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT id, username, requested_at, status, handled_at, handled_by_user_id
            FROM password_reset_requests
            WHERE status = ?
            ORDER BY requested_at DESC
            LIMIT 100
            """,
            (status,),
        ).fetchall()

    return {
        "requests": [
            {
                "id": row["id"],
                "username": row["username"],
                "requested_at": row["requested_at"],
                "status": row["status"],
                "handled_at": row["handled_at"],
                "handled_by_user_id": row["handled_by_user_id"],
            }
            for row in rows
        ]
    }


@app.post("/api/admin/password-reset-requests/<int:request_id>/mark-handled")
def admin_password_reset_mark_handled(request_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(
        """
        UPDATE password_reset_requests
        SET status = 'handled', handled_at = ?, handled_by_user_id = ?
        WHERE id = ?
        """,
        (now, user_id, request_id),
    )
    db.commit()
    return {"ok": True}


@app.post("/api/admin/password-reset-requests/<int:request_id>/reset-password")
def admin_password_reset_set_password(request_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    new_password = str(data.get("new_password", "")).strip()
    if len(new_password) < 6:
        return {"error": "Wachtwoord moet minstens 6 tekens hebben."}, 400

    db = get_db()
    request_row = db.execute(
        "SELECT id, username, status FROM password_reset_requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if request_row is None:
        return {"error": "Aanvraag niet gevonden."}, 404

    user_row = db.execute(
        "SELECT id, username FROM users WHERE username = ?",
        (request_row["username"],),
    ).fetchone()
    if user_row is None:
        return {"error": "Gebruiker niet gevonden."}, 404
    if is_super_author_user_id(user_row["id"]):
        return {"error": "forbidden_super_author"}, 403

    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_row["id"]),
    )
    db.execute(
        """
        UPDATE password_reset_requests
        SET status = 'handled', handled_at = ?, handled_by_user_id = ?
        WHERE id = ?
        """,
        (now, user_id, request_id),
    )
    db.commit()
    return {"ok": True}


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/api/me")
def get_me():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    db = get_db()
    row = db.execute("SELECT id, username, role, category, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return {"error": "unauthorized"}, 401
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "category": row["category"],
        "created_at": row["created_at"],
    }


@app.post("/api/me/change-password")
def change_own_password():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    data = request.get_json(silent=True) or {}
    old_password = str(data.get("old_password", "")).strip()
    new_password = str(data.get("new_password", "")).strip()

    if not old_password or not new_password:
        return {"error": "Beide velden zijn verplicht."}, 400
    if len(new_password) < 6:
        return {"error": "Nieuw wachtwoord moet minstens 6 tekens hebben."}, 400
    if old_password == new_password:
        return {"error": "Nieuw wachtwoord mag niet hetzelfde zijn."}, 400

    db = get_db()
    row = db.execute(
        "SELECT password_hash FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return {"error": "Gebruiker niet gevonden."}, 404

    if not check_password_hash(row["password_hash"], old_password):
        return {"error": "Oud wachtwoord is incorrect."}, 401

    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id),
    )
    db.commit()
    logger.info("User %d changed their password.", user_id)
    return {"ok": True, "message": "Wachtwoord succesvol gewijzigd."}


@app.get("/api/permissions")
def get_permissions():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    return get_user_permissions(user_id)


@app.get("/api/settings")
def get_settings():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    allowed_modules = get_allowed_modules(user_id)

    db = get_db()
    row = db.execute(
        "SELECT theme, layout_json FROM user_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if row is None:
        default_layout = default_layout_json()
        db.execute(
            "INSERT INTO user_settings (user_id, theme, layout_json, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, "light", default_layout, datetime.utcnow().isoformat()),
        )
        db.commit()
        layout = [item for item in json.loads(default_layout) if item.get("key") in allowed_modules]
        return {"theme": "light", "layout": layout}

    layout = [item for item in json.loads(row["layout_json"]) if item.get("key") in allowed_modules]
    return {"theme": row["theme"], "layout": layout}


@app.post("/api/settings")
def save_settings():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    data = request.get_json(silent=True) or {}
    theme = data.get("theme", "light")
    layout = data.get("layout", [])
    allowed_modules = get_allowed_modules(user_id)
    layout = [item for item in layout if item.get("key") in allowed_modules]

    if theme not in {"light", "dark"}:
        return {"error": "invalid theme"}, 400

    layout_json = json.dumps(layout)
    db = get_db()
    db.execute(
        "INSERT INTO user_settings (user_id, theme, layout_json, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET theme = excluded.theme, layout_json = excluded.layout_json, updated_at = excluded.updated_at",
        (user_id, theme, layout_json, datetime.utcnow().isoformat()),
    )
    db.commit()


def resolve_mac_for_ip(ip_address: str) -> str | None:
    try:
        subprocess.run(
            ["ping", "-n", "1", ip_address],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["arp", "-a", ip_address],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None

    output = (result.stdout or result.stderr or "").lower()
    match = re.search(r"([0-9a-f]{2}[:-]){5}[0-9a-f]{2}", output)
    if not match:
        return None
    return match.group(0).replace("-", ":")
    return {"ok": True}


def get_local_ipv4_interfaces() -> list[dict[str, str]]:
    interfaces: list[dict[str, str]] = []
    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        output = result.stdout or result.stderr or ""
        adapter_name = ""
        adapter_connected = True
        ignored_adapter_tokens = {
            "virtual",
            "vmware",
            "vbox",
            "hyper-v",
            "vethernet",
            "loopback",
            "bluetooth",
            "teredo",
            "isatap",
            "wsl",
        }
        for raw_line in output.splitlines():
            line = raw_line.strip()
            lower_line = line.lower()
            if not line:
                continue
            if line.endswith(":") and "adapter" in lower_line:
                adapter_name = lower_line
                adapter_connected = True
                continue
            if "media disconnected" in lower_line:
                adapter_connected = False
                continue
            if "ipv4" not in lower_line:
                continue
            if not adapter_connected:
                continue
            if any(token in adapter_name for token in ignored_adapter_tokens):
                continue
            match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
            if not match:
                continue
            ip_address = match.group(1)
            if ip_address.startswith("127."):
                continue
            if "wi-fi" in adapter_name or "wifi" in adapter_name or "wireless" in adapter_name:
                connection_type = "wifi"
            elif "ethernet" in adapter_name:
                connection_type = "ethernet"
            else:
                connection_type = "onbekend"
            interfaces.append({"ip": ip_address, "adapter": adapter_name, "connection_type": connection_type})
    except Exception:
        return []
    return interfaces


def get_local_ipv4_addresses() -> list[str]:
    candidates: set[str] = {item["ip"] for item in get_local_ipv4_interfaces() if item.get("ip")}

    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        output = result.stdout or result.stderr or ""
        for line in output.splitlines():
            if "IPv4" not in line:
                continue
            match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
            if not match:
                continue
            ip_address = match.group(1)
            if ip_address.startswith("127."):
                continue
            candidates.add(ip_address)
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip_address = item[4][0]
            if ip_address.startswith("127."):
                continue
            candidates.add(ip_address)
    except Exception:
        pass

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip_address = sock.getsockname()[0]
        if ip_address and not ip_address.startswith("127."):
            candidates.add(ip_address)
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass

    return sorted(candidates)


def subnet_prefix_from_ip(ip_address: str) -> str | None:
    parts = ip_address.split(".")
    if len(parts) != 4:
        return None
    return ".".join(parts[:3]) + "."


def parse_arp_output(raw_output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in raw_output.split("\n"):
        row = line.strip()
        if not row or "Interface" in row or "Address" in row or "---" in row:
            continue
        parts = row.split()
        if len(parts) < 3:
            continue
        ip_address = parts[0]
        mac_address = parts[1].replace("-", ":").lower()
        if not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", ip_address):
            continue
        if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", mac_address):
            continue
        entries.append({"ip": ip_address, "mac": mac_address})
    return entries


def discover_subnet_devices(subnet_prefix: str, max_hosts: int, local_ips: set[str], plc_only: bool = False, connection_type: str = "onbekend") -> list[dict[str, str]]:
    host_range = range(1, min(max_hosts, 254) + 1)

    def target_ip(host: int) -> str:
        return f"{subnet_prefix}{host}"

    arp_by_ip: dict[str, str] = {}
    live_ips: set[str] = set()

    def ping_and_check(host: int) -> str | None:
        """Returns the IP if the host actually replied to ping (not just in ARP cache)."""
        ip_address = target_ip(host)
        if ip_address in local_ips:
            return None
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "300", ip_address],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            output = (result.stdout or "").lower()
            # On Windows, a successful ping contains "bytes=" or "ttl=" in the reply
            if "ttl=" in output or "bytes=" in output:
                return ip_address
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=64) as pool:
        for ip in pool.map(ping_and_check, host_range):
            if ip:
                live_ips.add(ip)

    arp_entries: list[dict[str, str]] = []
    try:
        arp_result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        arp_entries = parse_arp_output(arp_result.stdout or arp_result.stderr or "")
    except Exception:
        arp_entries = []

    for entry in arp_entries:
        ip_address = entry.get("ip")
        if ip_address and ip_address.startswith(subnet_prefix):
            arp_by_ip[ip_address] = entry.get("mac") or ""

    plc_ports = list(PLC_PORTS.keys())

    def has_plc_port_open_ip(ip_address: str) -> tuple[str, int] | None:
        if ip_address in local_ips:
            return None
        for port in plc_ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.18 if plc_only else 0.12)
            try:
                if sock.connect_ex((ip_address, port)) == 0:
                    confirm = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    confirm.settimeout(0.18)
                    try:
                        if confirm.connect_ex((ip_address, port)) == 0:
                            return ip_address, port
                    except Exception:
                        pass
                    finally:
                        confirm.close()
                    return ip_address, port
            except Exception:
                pass
            finally:
                sock.close()
        return None

    plc_ports_by_ip: dict[str, set[int]] = {}

    if plc_only:
        candidate_ips = set(live_ips) | set(arp_by_ip.keys())
        with ThreadPoolExecutor(max_workers=72) as pool:
            plc_hits = [item for item in pool.map(has_plc_port_open_ip, candidate_ips) if item]

        if not plc_hits:
            full_scan_candidates = [target_ip(host) for host in host_range if target_ip(host) not in local_ips]
            with ThreadPoolExecutor(max_workers=96) as pool:
                plc_hits = [item for item in pool.map(has_plc_port_open_ip, full_scan_candidates) if item]

        for hit in plc_hits:
            ip_address, open_port = hit
            plc_ports_by_ip.setdefault(ip_address, set()).add(open_port)
        unique_ips = set(plc_ports_by_ip.keys())
    else:
        with ThreadPoolExecutor(max_workers=64) as pool:
            plc_hits = [item for item in pool.map(has_plc_port_open_ip, live_ips) if item]
        for hit in plc_hits:
            ip_address, open_port = hit
            plc_ports_by_ip.setdefault(ip_address, set()).add(open_port)
        unique_ips = set(live_ips) | set(plc_ports_by_ip.keys())

    effective_connection_type = connection_type
    if connection_type == "ethernet" and len(unique_ips) <= 2:
        effective_connection_type = "rechtstreeks (kabel)"

    results: list[dict[str, str]] = []
    for ip_address in sorted(unique_ips):
        if ip_address in local_ips:
            continue
        mac_address = arp_by_ip.get(ip_address) or resolve_mac_for_ip(ip_address) or ""
        found_via: list[str] = []
        if ip_address in live_ips:
            found_via.append("ping")
        if ip_address in arp_by_ip:
            found_via.append("arp")
        for plc_port in sorted(plc_ports_by_ip.get(ip_address, set())):
            found_via.append(f"plc-poort {plc_port}")
        results.append(
            {
                "ip": ip_address,
                "mac": mac_address,
                "subnet": subnet_prefix,
                "connection_type": effective_connection_type,
                "found_via": found_via,
            }
        )
    return results


def discover_lan_devices(max_hosts: int = 254, plc_only: bool = False) -> tuple[str | None, list[dict[str, str]]]:
    local_interfaces = get_local_ipv4_interfaces()
    local_ips = [item["ip"] for item in local_interfaces if item.get("ip")]
    subnet_connection: dict[str, str] = {}
    for item in local_interfaces:
        prefix = subnet_prefix_from_ip(item.get("ip") or "")
        if prefix and prefix not in subnet_connection:
            subnet_connection[prefix] = item.get("connection_type") or "onbekend"

    if not local_ips:
        local_ips = get_local_ipv4_addresses()
    if not local_ips:
        return None, []

    subnets: list[str] = []
    for ip_address in local_ips:
        prefix = subnet_prefix_from_ip(ip_address)
        if prefix and prefix not in subnets:
            subnets.append(prefix)

    if not subnets:
        return None, []

    merged: dict[str, dict[str, str]] = {}
    local_ip_set = set(local_ips)
    for subnet in subnets:
        subnet_results = discover_subnet_devices(
            subnet,
            max_hosts=max_hosts,
            local_ips=local_ip_set,
            plc_only=plc_only,
            connection_type=subnet_connection.get(subnet, "onbekend"),
        )
        for item in subnet_results:
            existing = merged.get(item["ip"])
            if existing is None or (not existing.get("mac") and item.get("mac")):
                merged[item["ip"]] = item

    return subnets[0], sorted(merged.values(), key=lambda item: item["ip"])


PLC_PORTS: dict[int, str] = {
    102: "Siemens S7",
    502: "Modbus/TCP",
    4840: "OPC UA",
    44818: "EtherNet/IP",
}

DEVICE_FINGERPRINT_PORTS: dict[int, str] = {
    80: "HTTP",
    443: "HTTPS",
    22: "SSH",
    53: "DNS",
    554: "RTSP",
    1883: "MQTT",
    445: "SMB",
    139: "NetBIOS",
    3389: "RDP",
    9100: "JetDirect",
}


def resolve_hostname(ip_address: str) -> str | None:
    try:
        host, _, _ = socket.gethostbyaddr(ip_address)
    except Exception:
        return None
    host = (host or "").strip()
    if not host or host == ip_address:
        return None
    return host


def probe_open_ports(ip_address: str, ports: list[int], timeout: float = 0.2) -> list[int]:
    open_ports: list[int] = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            if sock.connect_ex((ip_address, port)) == 0:
                open_ports.append(port)
        except Exception:
            pass
        finally:
            sock.close()
    return open_ports


def classify_network_device(hostname: str | None, open_ports: list[int], mac: str | None) -> tuple[str, float]:
    host = (hostname or "").lower()
    mac_clean = (mac or "").lower().replace("-", ":")
    mac_prefix = mac_clean[0:8]
    port_set = set(open_ports)

    # Raspberry Pi MAC prefixes (Foundation OUIs) — check before PLC to avoid false positives
    if mac_prefix in {"b8:27:eb", "dc:a6:32", "e4:5f:01", "28:cd:c1", "d8:3a:dd", "2c:cf:67"}:
        return "raspberry-pi", 0.92

    if any(token in host for token in ["raspberry", "raspi", "raspberrypi"]):
        return "raspberry-pi", 0.88

    if any(port in PLC_PORTS for port in port_set):
        return "plc", 0.95

    if any(token in host for token in ["iphone", "android", "phone", "galaxy"]):
        return "phone", 0.9

    if 9100 in port_set:
        return "printer", 0.9

    if 554 in port_set:
        return "camera", 0.88

    if 53 in port_set and 80 in port_set:
        return "router", 0.9

    if any(token in host for token in ["router", "gateway", "ap", "modem"]):
        return "router", 0.85

    if any(token in host for token in ["hmi", "scada", "plc", "siemens", "s7", "wago", "codesys"]):
        return "plc", 0.85

    if 1883 in port_set:
        return "iot", 0.75

    if 445 in port_set or 3389 in port_set:
        return "computer", 0.82

    if any(token in host for token in ["desktop", "laptop", "pc", "windows"]):
        return "computer", 0.75

    if 80 in port_set or 443 in port_set:
        return "network-device", 0.6

    if 22 in port_set:
        return "iot", 0.5

    # Common phone/tablet vendors (Apple, Samsung, Huawei, Xiaomi, OnePlus)
    if mac_prefix[:8] in {
        "00:17:f2", "00:1b:63", "00:1c:b3", "00:1e:52", "00:1f:5b",
        "00:23:12", "00:25:00", "00:26:08", "04:0c:ce", "04:15:52",
        "04:48:9a", "04:4b:ed", "08:74:02", "0c:74:c2", "10:40:f3",
        "10:9a:dd", "18:af:61", "1c:ab:a7", "20:7d:74", "24:18:1d",
        "28:6c:07", "2c:1f:23", "34:08:bc", "38:f9:d3", "3c:22:fb",
        "40:83:de", "40:b3:95", "44:00:10", "48:43:7c", "4c:57:ca",
        "50:32:37", "50:55:27", "58:7f:57", "60:f8:1d", "70:3e:ac",
        "74:45:8a", "78:6c:1c", "7c:04:d0", "80:19:34", "80:65:6d",
        "84:38:35", "88:63:df", "8c:85:90", "90:27:e4", "94:65:2d",
        "98:52:b1", "9c:f3:87", "a0:56:f3", "a4:5e:60", "a8:9f:ba",
        "ac:bc:32", "b0:35:8d", "b4:0b:44", "b8:c7:5d", "bc:3b:af",
        "c0:ee:fb", "c4:b3:01", "c8:d0:83", "cc:08:e0", "d0:17:c2",
        "d4:20:b0", "dc:2b:61", "e0:ac:cb", "e4:ce:8f", "e8:04:62",
        "ec:10:7b", "f0:18:98", "f4:0e:11", "f8:e0:79", "fc:25:3f",
    }:
        return "phone", 0.55

    # Printers (HP, Epson, Canon, Brother, Kyocera)
    if mac_prefix[:8] in {
        "00:00:48", "00:04:00", "00:1e:11", "00:1f:29", "00:17:c8",
        "00:18:fe", "00:1b:a9", "00:21:5a", "00:26:73", "28:80:23",
        "30:05:5c", "40:b0:34", "48:9e:bd", "6c:3b:6b", "70:77:81",
        "78:ac:c0", "84:eb:18", "9c:b6:d0", "b4:b6:86", "bc:5f:f4",
        "c4:17:fe", "c8:aa:21", "d8:9e:3f", "e4:1f:13", "f4:81:39",
    }:
        return "printer", 0.6

    # Cisco/network equipment (routers, switches, APs)
    if mac_prefix[:8] in {
        "00:00:0c", "00:00:1c", "00:01:42", "00:01:63", "00:01:96",
        "00:01:97", "00:02:16", "00:02:17", "00:03:6b", "00:04:9a",
        "00:07:eb", "00:08:74", "00:09:7b", "00:0a:41", "00:0b:46",
        "00:0c:85", "00:0d:28", "00:0e:83", "00:0f:90", "00:11:5c",
        "00:12:80", "00:13:19", "00:13:80", "00:14:69", "00:15:63",
        "00:16:47", "00:17:0e", "00:18:18", "00:18:74", "00:19:06",
        "00:1a:2f", "00:1b:0c", "00:1b:d4", "00:1c:57", "00:1d:45",
        "00:1e:13", "00:1e:be", "00:1f:c9", "00:21:a0", "00:22:55",
        "00:22:bd", "00:23:33", "00:23:eb", "00:24:14", "00:24:98",
        "00:25:45", "00:25:84", "00:26:0b", "00:26:cb", "00:27:0d",
        "00:2a:10", "00:50:0f", "00:6b:8e", "04:c5:a4", "08:cc:68",
        "10:bd:18", "18:33:9d", "1c:17:d3", "24:01:c7", "28:94:0f",
        "30:37:a6", "34:a8:4e", "3c:08:f6", "40:f4:ec", "44:ad:d9",
        "48:f8:b3", "4c:e1:75", "50:06:25", "54:78:1a", "58:97:1e",
        "5c:50:15", "64:00:6a", "64:a0:e7", "68:9c:e2", "6c:41:6a",
        "70:10:5c", "74:86:7a", "78:ba:f9", "7c:ad:74", "80:e8:6f",
        "84:b8:02", "88:75:98", "8c:60:4f", "90:b1:1c", "98:5a:eb",
        "9c:5c:8e", "a0:3d:6f", "a4:93:4c", "a8:b4:56", "ac:7e:8a",
        "b0:aa:77", "b4:a9:fc", "b8:be:bf", "bc:16:f5", "c0:4a:00",
        "c4:64:13", "c8:9c:1d", "cc:46:d6", "d0:57:7b", "d4:8c:b5",
        "d8:b1:22", "dc:a5:f4", "e0:1c:41", "e4:aa:5d", "e8:65:d4",
        "ec:44:76", "f0:25:72", "f4:cf:a2", "f8:c2:88", "fc:5b:39",
    }:
        return "router", 0.6

    # If nothing open at all but appeared in ARP, label as unknown
    if not open_ports:
        return "unknown", 0.3

    return "unknown", 0.35


def suggested_device_name(ip_address: str, hostname: str | None, device_type: str) -> str:
    if hostname:
        return hostname
    if device_type == "plc":
        return f"PLC {ip_address}"
    if device_type == "phone":
        return f"Telefoon {ip_address}"
    if device_type == "raspberry-pi":
        return f"Raspberry Pi {ip_address}"
    if device_type == "router":
        return f"Router {ip_address}"
    if device_type == "computer":
        return f"Computer {ip_address}"
    if device_type == "iot":
        return f"IoT {ip_address}"
    if device_type == "printer":
        return f"Printer {ip_address}"
    if device_type == "camera":
        return f"Camera {ip_address}"
    if device_type == "network-device":
        return f"Netwerkapparaat {ip_address}"
    return f"Onbekend apparaat {ip_address}"


def is_plc_like_device(name: str | None, ip_address: str) -> bool:
    device_name = (name or "").lower()
    if any(token in device_name for token in ["plc", "siemens", "s7", "wago", "codesys", "hmi", "scada"]):
        return True
    try:
        open_ports = probe_open_ports(ip_address, list(PLC_PORTS.keys()), timeout=0.12)
    except Exception:
        return False
    return any(port in PLC_PORTS for port in open_ports)


def normalize_plc_io_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in entries:
        tag = str(row.get("tag") or "").strip()
        if not tag:
            continue
        display_name = str(row.get("name") or "").strip()
        io_type_raw = str(row.get("io_type") or row.get("type") or "").strip().lower()
        tag_prefix = tag[:1].upper()
        io_type = "Output" if tag_prefix == "Q" else "Input"
        if tag_prefix == "M":
            io_type = "Input"
        if io_type_raw in {"input", "output"}:
            io_type = io_type_raw.capitalize()
        value = bool(int(row.get("value", 0))) if str(row.get("value", "0")).strip() in {"0", "1"} else bool(row.get("value"))
        writable = bool(row.get("writable", False))
        normalized.append(
            {
                "name": display_name or tag,
                "tag": tag,
                "io_type": io_type,
                "value": 1 if value else 0,
                "writable": writable if io_type == "Input" else False,
            }
        )
    return normalized


PLC_TAG_RE = re.compile(r"[IQMV][0-9]+\.[0-7]", re.IGNORECASE)


def infer_plc_point_type(tag: str) -> str:
    prefix = str(tag or "").strip()[:1].upper()
    return "Output" if prefix == "Q" else "Input"


def is_plc_point_writable(tag: str) -> bool:
    prefix = str(tag or "").strip()[:1].upper()
    return prefix in {"M", "V"}


def get_device_plc_points(device_id: int) -> list[dict[str, object]]:
    db = get_db()
    rows = db.execute(
        "SELECT id, name, tag FROM plc_points WHERE device_id = ? ORDER BY created_at ASC, id ASC",
        (device_id,),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": str(row["name"] or "").strip(),
            "tag": str(row["tag"] or "").strip().upper(),
            "io_type": infer_plc_point_type(str(row["tag"] or "")),
            "writable": is_plc_point_writable(str(row["tag"] or "")),
        }
        for row in rows
    ]


def build_plc_point_entries(device_id: int) -> list[dict[str, object]]:
    return [
        {
            "name": point["name"],
            "tag": point["tag"],
            "io_type": point["io_type"],
            "writable": point["writable"],
            "value": 0,
        }
        for point in get_device_plc_points(device_id)
    ]


def get_plc_bridge_base_url() -> str:
    return str(os.environ.get("PLC_BRIDGE_URL") or "http://127.0.0.1:5000").rstrip("/")


def bridge_fetch_plc_io(ip_address: str) -> tuple[list[dict[str, object]] | None, str | None, bool]:
    base_url = get_plc_bridge_base_url()
    encoded_ip = urllib.parse.quote(ip_address, safe="")
    url = f"{base_url}/plcs/{encoded_ip}/io"
    try:
        with urllib.request.urlopen(url, timeout=1.8) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw)
            if not isinstance(payload, list):
                return None, None, True
            entries = normalize_plc_io_entries(payload)
            return entries, "bridge-api", True
    except Exception:
        return None, None, False


def bridge_sync_plc_points(ip_address: str, points: list[dict[str, object]]) -> bool:
    base_url = get_plc_bridge_base_url()
    encoded_ip = urllib.parse.quote(ip_address, safe="")
    url = f"{base_url}/plcs/{encoded_ip}/io/config"
    payload = json.dumps({"points": points}).encode("utf-8")
    request_obj = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=2.5):
            return True
    except Exception:
        return False


def bridge_toggle_plc_io(ip_address: str, tag: str) -> tuple[bool, bool, str | None]:
    base_url = get_plc_bridge_base_url()
    encoded_ip = urllib.parse.quote(ip_address, safe="")
    encoded_tag = urllib.parse.quote(tag, safe="")
    url = f"{base_url}/plcs/{encoded_ip}/io/{encoded_tag}/toggle"
    request_obj = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(request_obj, timeout=1.8) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw) if raw else {}
            if isinstance(payload, dict):
                if payload.get("ok") is False:
                    return False, True, str(payload.get("error") or "PLC-write mislukt")
                if payload.get("live") is False:
                    return False, True, str(payload.get("error") or "Bridge bereikbaar, maar geen live PLC-write")
            return True, True, None
    except Exception:
        return False, False, None


def bridge_set_plc_io(ip_address: str, tag: str, value: bool) -> tuple[bool, bool, str | None]:
    base_url = get_plc_bridge_base_url()
    encoded_ip = urllib.parse.quote(ip_address, safe="")
    encoded_tag = urllib.parse.quote(tag, safe="")
    url = f"{base_url}/plcs/{encoded_ip}/io/{encoded_tag}/set"
    payload = json.dumps({"value": 1 if value else 0}).encode("utf-8")
    request_obj = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=1.8) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw) if raw else {}
            if isinstance(payload, dict):
                if payload.get("ok") is False:
                    return False, True, str(payload.get("error") or "PLC-write mislukt")
                if payload.get("live") is False:
                    return False, True, str(payload.get("error") or "Bridge bereikbaar, maar geen live PLC-write")
            return True, True, None
    except Exception:
        return False, False, None


def get_or_seed_plc_io_state(device_id: int, ip_address: str) -> list[dict[str, object]]:
    with PLC_IO_LOCK:
        existing = PLC_IO_STATE.get(device_id)
        if existing:
            return [dict(item) for item in existing]

        seeded = build_plc_point_entries(device_id)
        PLC_IO_STATE[device_id] = seeded
        return [dict(item) for item in seeded]


def toggle_local_plc_point(device_id: int, tag: str) -> bool:
    with PLC_IO_LOCK:
        entries = PLC_IO_STATE.get(device_id)
        if not entries:
            return False
        for row in entries:
            if str(row.get("tag")) != tag:
                continue
            if not bool(row.get("writable", True)):
                return False
            row["value"] = 0 if int(row.get("value", 0)) else 1
            return True
    return False


@app.post("/api/arp")
def get_arp_table():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    if "arp" not in get_allowed_modules(user_id):
        return {"error": "forbidden"}, 403

    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {"error": str(exc)}, 500

    output = (result.stdout or result.stderr or "").strip()
    if not output:
        return {"entries": []}

    entries = []
    for line in output.split("\n"):
        line = line.strip()
        if not line or "Interface" in line or "Address" in line or "-" * 10 in line:
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                ip = parts[0]
                mac = parts[1].replace("-", ":")
                status = " ".join(parts[2:])
                entries.append({"ip": ip, "mac": mac, "status": status})
            except (ValueError, IndexError):
                continue

    return {"entries": entries}


@app.post("/api/ping")
def ping_host():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    if "ping" not in get_allowed_modules(user_id):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    host = str(data.get("host", "")).strip()
    if not host:
        return {"error": "host required"}, 400

    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        return {"error": "invalid host"}, 400

    try:
        result = subprocess.run(
            ["ping", "-n", "1", host],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {"error": str(exc)}, 500

    output = (result.stdout or result.stderr or "").strip()
    return {"output": output}


@app.get("/devices/<int:device_id>")
def device_dashboard(device_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    if not is_admin_user(user_id):
        permissions = get_user_permissions(user_id)
        if not permissions["can_view_devices"]:
            return redirect(url_for("index"))
        device_access = permissions["device_access"]
        if device_access is not None and device_id not in device_access:
            return redirect(url_for("index"))

    db = get_db()
    row = db.execute(
        "SELECT id, name, ip_address FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if row is None:
        return redirect(url_for("index"))

    db.execute(
        "INSERT OR REPLACE INTO user_device_activity (user_id, device_id, last_seen) VALUES (?, ?, ?)",
        (user_id, device_id, datetime.utcnow().isoformat()),
    )
    db.commit()

    return render_template(
        "device_dashboard.html",
        device_id=row["id"],
        device_name=row["name"],
        device_ip=row["ip_address"],
    )


@app.post("/api/device/<int:device_id>/ping")
def device_ping(device_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if "ping" not in get_allowed_modules(user_id):
        return {"error": "forbidden"}, 403

    db = get_db()
    row = db.execute(
        "SELECT id, ip_address FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if row is None:
        return {"error": "device not found"}, 404

    log_device_activity(user_id, device_id)

    ip_address = row["ip_address"]
    try:
        result = subprocess.run(
            ["ping", "-n", "1", ip_address],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {"error": str(exc)}, 500

    output = (result.stdout or result.stderr or "").strip()
    return {"output": output}


@app.post("/api/device/<int:device_id>/command")
def device_command(device_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if "terminal" not in get_allowed_modules(user_id):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    command = str(data.get("command", "")).strip().lower()
    if command not in {"ping", "tracert", "nslookup"}:
        return {"error": "command not allowed"}, 400

    db = get_db()
    row = db.execute(
        "SELECT id, ip_address FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if row is None:
        return {"error": "device not found"}, 404

    log_device_activity(user_id, device_id)

    ip_address = row["ip_address"]
    exec_cmd = [command, ip_address]
    try:
        result = subprocess.run(
            exec_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return {"error": str(exc)}, 500

    output = (result.stdout or result.stderr or "").strip()
    return {"output": output}


@app.post("/api/terminal")
def terminal_command():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    if "terminal" not in get_allowed_modules(user_id):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    command = str(data.get("command", "")).strip()
    if not command:
        return {"error": "command required"}, 400

    def is_valid_host(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9.-]+", value))

    def parse_count(value: str) -> int | None:
        try:
            count = int(value)
        except ValueError:
            return None
        if 1 <= count <= 10:
            return count
        return None

    allowed_simple = {
        "ipconfig": ["ipconfig"],
        "ipconfig /all": ["ipconfig", "/all"],
        "arp -a": ["arp", "-a"],
        "arp -g": ["arp", "-g"],
        "tracert": ["tracert"],
        "nslookup": ["nslookup"],
        "netstat": ["netstat", "-an"],
        "netstat -an": ["netstat", "-an"],
        "netstat -ano": ["netstat", "-ano"],
        "uptime": [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime",
        ],
        "whoami": ["whoami"],
        "hostname": ["hostname"],
    }

    try:
        tokens = shlex.split(command)
    except ValueError:
        return {"error": "invalid command"}, 400

    if not tokens:
        return {"error": "command required"}, 400

    cmd = tokens[0].lower()
    exec_cmd: list[str] | None = None

    if cmd == "ping":
        if len(tokens) < 2:
            return {"error": "host required"}, 400
        count = 1
        host = None
        idx = 1
        while idx < len(tokens):
            part = tokens[idx].lower()
            if part in {"-n", "-c"} and idx + 1 < len(tokens):
                parsed = parse_count(tokens[idx + 1])
                if parsed is None:
                    return {"error": "invalid count"}, 400
                count = parsed
                idx += 2
                continue
            host = tokens[idx]
            idx += 1
        if not host or not is_valid_host(host):
            return {"error": "invalid host"}, 400
        exec_cmd = ["ping", "-n", str(count), host]
    elif cmd == "tracert":
        if len(tokens) != 2 or not is_valid_host(tokens[1]):
            return {"error": "invalid host"}, 400
        exec_cmd = ["tracert", tokens[1]]
    elif cmd == "nslookup":
        if len(tokens) != 2 or not is_valid_host(tokens[1]):
            return {"error": "invalid host"}, 400
        exec_cmd = ["nslookup", tokens[1]]
    elif cmd == "netstat":
        if len(tokens) == 1:
            exec_cmd = ["netstat", "-an"]
        elif len(tokens) == 2 and tokens[1].lower() in {"-an", "-ano"}:
            exec_cmd = ["netstat", tokens[1].lower()]
        else:
            return {"error": "invalid netstat args"}, 400
    elif cmd == "ipconfig":
        if len(tokens) == 1:
            exec_cmd = ["ipconfig"]
        elif len(tokens) == 2 and tokens[1].lower() == "/all":
            exec_cmd = ["ipconfig", "/all"]
        else:
            return {"error": "invalid ipconfig args"}, 400
    elif cmd == "arp":
        if len(tokens) == 1:
            exec_cmd = ["arp", "-a"]
        elif len(tokens) == 2 and tokens[1].lower() in {"-a", "-g"}:
            exec_cmd = ["arp", tokens[1].lower()]
        else:
            return {"error": "invalid arp args"}, 400
    else:
        joined = " ".join(tokens).lower()
        exec_cmd = allowed_simple.get(joined)

    if not exec_cmd:
        return {"output": "Command not allowed."}

    with PROCESS_LOCK:
        running = RUNNING_PROCESSES.get(user_id)
        if running and running.poll() is None:
            return {"error": "command already running"}, 409

        process = subprocess.Popen(
            exec_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        RUNNING_PROCESSES[user_id] = process

    try:
        stdout, stderr = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        return {"output": "Command still running. Use stop."}
    except Exception as exc:
        return {"error": str(exc)}, 500
    finally:
        with PROCESS_LOCK:
            if RUNNING_PROCESSES.get(user_id) is process:
                RUNNING_PROCESSES.pop(user_id, None)

    output = (stdout or stderr or "").strip()
    return {"output": output}


@app.post("/api/terminal/stop")
def terminal_stop():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    with PROCESS_LOCK:
        process = RUNNING_PROCESSES.get(user_id)

    if not process or process.poll() is not None:
        return {"ok": True}

    try:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
    finally:
        with PROCESS_LOCK:
            if RUNNING_PROCESSES.get(user_id) is process:
                RUNNING_PROCESSES.pop(user_id, None)

    return {"ok": True}


@app.route("/api/system/status", methods=["GET"])
def get_system_status():
    global API_SYSTEM_ENABLED
    with API_SYSTEM_LOCK:
        api_enabled = API_SYSTEM_ENABLED
    return {
        "api_enabled": api_enabled,
        "bridge_url": os.environ.get("PLC_BRIDGE_URL", "http://127.0.0.1:5000"),
        "timestamp": datetime.now().isoformat(),
    }


@app.route("/api/system/toggle", methods=["POST"])
def toggle_api_system():
    global API_SYSTEM_ENABLED
    
    # Allow localhost (Startup GUI) without auth
    remote_addr = request.remote_addr
    is_localhost = remote_addr in ("127.0.0.1", "localhost", "::1")
    
    if not is_localhost:
        user_id = session.get("user_id")
        if not user_id:
            return {"error": "unauthorized"}, 401
        if not is_admin_user(user_id):
            return {"error": "forbidden"}, 403

    payload = request.get_json(silent=True) or {}
    new_state = payload.get("enabled")
    if new_state is None:
        return {"error": "enabled parameter required"}, 400

    with API_SYSTEM_LOCK:
        API_SYSTEM_ENABLED = bool(new_state)
        current_state = API_SYSTEM_ENABLED

    requester = remote_addr if is_localhost else session.get("user_id")
    logger.info(f"API System toggled to {current_state} by {requester}")
    return {
        "ok": True,
        "api_enabled": current_state,
        "timestamp": datetime.now().isoformat(),
    }


def check_api_enabled():
    """Check if API system is enabled, return error tuple if disabled."""
    global API_SYSTEM_ENABLED
    with API_SYSTEM_LOCK:
        is_enabled = API_SYSTEM_ENABLED
    if not is_enabled:
        return ({"error": "API system is currently disabled"}, 503)
    return None


@app.get("/api/devices")
def list_devices():
    api_error = check_api_enabled()
    if api_error:
        return api_error
    
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    if not is_admin_user(user_id):
        permissions = get_user_permissions(user_id)
        if not permissions["can_view_devices"]:
            return {"error": "forbidden"}, 403
        device_access = permissions["device_access"]
    else:
        device_access = None

    db = get_db()
    if device_access is None:
        rows = db.execute(
            "SELECT id, name, ip_address, mac_address, created_at FROM devices ORDER BY id DESC"
        ).fetchall()
    elif len(device_access) == 0:
        rows = []
    else:
        rows = db.execute(
            "SELECT id, name, ip_address, mac_address, created_at FROM devices WHERE id IN ({}) ORDER BY id DESC".format(
                ",".join(["?"] * len(device_access))
            ),
            tuple(device_access),
        ).fetchall()
    return {
        "devices": [
            {
                "id": row["id"],
                "name": row["name"],
                "ip": row["ip_address"],
                "mac": row["mac_address"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    }


@app.get("/api/devices/discover")
def discover_devices():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    if not is_admin_user(user_id):
        permissions = get_user_permissions(user_id)
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403

    max_hosts_param = request.args.get("max_hosts", "254")
    try:
        max_hosts = max(8, min(254, int(max_hosts_param)))
    except ValueError:
        max_hosts = 64

    plc_only = request.args.get("plc_only", "0") in ("1", "true", "yes")

    subnet_prefix, discovered = discover_lan_devices(max_hosts=max_hosts, plc_only=plc_only)
    if not subnet_prefix:
        return {"error": "local subnet not available"}, 500

    db = get_db()
    existing_rows = db.execute("SELECT id, ip_address, name FROM devices").fetchall()
    existing_by_ip = {row["ip_address"]: row for row in existing_rows}

    def enrich(item: dict[str, str], timeout: float = 0.12) -> dict[str, object]:
        ip_address = item["ip"]
        mac_address = item.get("mac")
        hostname = None if plc_only else resolve_hostname(ip_address)
        probe_ports = list(PLC_PORTS.keys()) if plc_only else list({*PLC_PORTS.keys(), *DEVICE_FINGERPRINT_PORTS.keys()})
        open_ports = probe_open_ports(ip_address, probe_ports, timeout=timeout)
        plc_services = [PLC_PORTS[port] for port in open_ports if port in PLC_PORTS]
        generic_services = [] if plc_only else [DEVICE_FINGERPRINT_PORTS[port] for port in open_ports if port in DEVICE_FINGERPRINT_PORTS]
        all_services = list(dict.fromkeys([*plc_services, *generic_services]))
        device_type, confidence = classify_network_device(hostname, open_ports, mac_address)
        existing = existing_by_ip.get(ip_address)
        return {
            "ip": ip_address,
            "mac": mac_address,
            "hostname": hostname,
            "open_ports": open_ports,
            "services": all_services,
            "plc_services": plc_services,
            "device_type": device_type,
            "confidence": confidence,
            "plc_candidate": bool(plc_services) if plc_only else device_type == "plc",
            "found_via": item.get("found_via") or [],
            "connection_type": item.get("connection_type") or "onbekend",
            "already_added": existing is not None,
            "device_id": existing["id"] if existing else None,
            "suggested_name": existing["name"] if existing else suggested_device_name(ip_address, hostname, device_type),
            "scan_attempts": 1,
        }

    results: list[dict[str, object]] = []
    for item in discovered:
        row = enrich(item, timeout=0.1 if plc_only else 0.12)
        if not plc_only and row.get("device_type") == "unknown":
            best_row = row
            for retry_index in range(1, 4):
                retry_timeout = 0.12 + (retry_index * 0.06)
                retry_row = enrich(item, timeout=retry_timeout)
                retry_row["scan_attempts"] = retry_index + 1
                if retry_row.get("device_type") != "unknown":
                    best_row = retry_row
                    break
                if len(retry_row.get("open_ports") or []) > len(best_row.get("open_ports") or []):
                    best_row = retry_row
            row = best_row
        results.append(row)

    if plc_only:
        results = [r for r in results if r.get("plc_candidate")]
        unique_by_mac: dict[str, dict[str, object]] = {}
        deduped: list[dict[str, object]] = []
        for row in results:
            mac_key = str(row.get("mac") or "").lower()
            if not mac_key:
                deduped.append(row)
                continue
            existing = unique_by_mac.get(mac_key)
            if existing is None:
                unique_by_mac[mac_key] = row
                deduped.append(row)
                continue
            existing_ports = len(existing.get("plc_services") or [])
            current_ports = len(row.get("plc_services") or [])
            if current_ports > existing_ports:
                unique_by_mac[mac_key] = row
                deduped = [item for item in deduped if str(item.get("mac") or "").lower() != mac_key]
                deduped.append(row)
        results = deduped

    results.sort(key=lambda item: (not bool(item["plc_candidate"]), str(item["ip"])))

    return {
        "subnet": subnet_prefix,
        "count": len(results),
        "plc_count": sum(1 for row in results if row.get("plc_candidate")),
        "plc_only": plc_only,
        "devices": results,
    }


@app.get("/api/devices/discover/stream")
def discover_devices_stream():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    if not is_admin_user(user_id):
        permissions = get_user_permissions(user_id)
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403

    max_hosts_param = request.args.get("max_hosts", "254")
    try:
        max_hosts = max(8, min(254, int(max_hosts_param)))
    except ValueError:
        max_hosts = 64

    plc_only = request.args.get("plc_only", "0") in ("1", "true", "yes")

    def event(data: dict[str, object], event_name: str | None = None) -> str:
        payload = json.dumps(data, ensure_ascii=False)
        if event_name:
            return f"event: {event_name}\ndata: {payload}\n\n"
        return f"data: {payload}\n\n"

    @stream_with_context
    def generate():
        try:
            subnet_prefix, discovered = discover_lan_devices(max_hosts=max_hosts, plc_only=plc_only)
            if not subnet_prefix:
                yield event({"error": "local subnet not available"}, "error")
                return

            db = get_db()
            existing_rows = db.execute("SELECT id, ip_address, name FROM devices").fetchall()
            existing_by_ip = {row["ip_address"]: row for row in existing_rows}

            def enrich(item: dict[str, str], timeout: float = 0.12) -> dict[str, object]:
                ip_address = item["ip"]
                mac_address = item.get("mac")
                hostname = None if plc_only else resolve_hostname(ip_address)
                probe_ports = list(PLC_PORTS.keys()) if plc_only else list({*PLC_PORTS.keys(), *DEVICE_FINGERPRINT_PORTS.keys()})
                open_ports = probe_open_ports(ip_address, probe_ports, timeout=timeout)
                plc_services = [PLC_PORTS[port] for port in open_ports if port in PLC_PORTS]
                generic_services = [] if plc_only else [DEVICE_FINGERPRINT_PORTS[port] for port in open_ports if port in DEVICE_FINGERPRINT_PORTS]
                all_services = list(dict.fromkeys([*plc_services, *generic_services]))
                device_type, confidence = classify_network_device(hostname, open_ports, mac_address)
                existing = existing_by_ip.get(ip_address)
                return {
                    "ip": ip_address,
                    "mac": mac_address,
                    "hostname": hostname,
                    "open_ports": open_ports,
                    "services": all_services,
                    "plc_services": plc_services,
                    "device_type": device_type,
                    "confidence": confidence,
                    "plc_candidate": bool(plc_services) if plc_only else device_type == "plc",
                    "found_via": item.get("found_via") or [],
                    "connection_type": item.get("connection_type") or "onbekend",
                    "already_added": existing is not None,
                    "device_id": existing["id"] if existing else None,
                    "suggested_name": existing["name"] if existing else suggested_device_name(ip_address, hostname, device_type),
                    "scan_attempts": 1,
                }

            results: list[dict[str, object]] = []
            seen_macs: set[str] = set()

            total = len(discovered)
            yield event({"phase": "start", "total": total, "subnet": subnet_prefix, "plc_only": plc_only}, "progress")

            for index, item in enumerate(discovered, start=1):
                row = enrich(item, timeout=0.1 if plc_only else 0.12)
                if not plc_only and row.get("device_type") == "unknown":
                    best_row = row
                    for retry_index in range(1, 4):
                        retry_timeout = 0.12 + (retry_index * 0.06)
                        retry_row = enrich(item, timeout=retry_timeout)
                        retry_row["scan_attempts"] = retry_index + 1
                        if retry_row.get("device_type") != "unknown":
                            best_row = retry_row
                            break
                        if len(retry_row.get("open_ports") or []) > len(best_row.get("open_ports") or []):
                            best_row = retry_row
                    row = best_row

                if plc_only and not row.get("plc_candidate"):
                    yield event({"phase": "progress", "processed": index, "total": total}, "progress")
                    continue

                if plc_only:
                    mac_key = str(row.get("mac") or "").lower()
                    if mac_key and mac_key in seen_macs:
                        yield event({"phase": "progress", "processed": index, "total": total}, "progress")
                        continue
                    if mac_key:
                        seen_macs.add(mac_key)

                results.append(row)
                yield event({"phase": "device", "processed": index, "total": total, "device": row}, "device")
                yield event({"phase": "progress", "processed": index, "total": total}, "progress")

            results.sort(key=lambda item: (not bool(item["plc_candidate"]), str(item["ip"])))
            yield event(
                {
                    "phase": "done",
                    "subnet": subnet_prefix,
                    "count": len(results),
                    "plc_count": sum(1 for row in results if row.get("plc_candidate")),
                    "plc_only": plc_only,
                    "devices": results,
                },
                "done",
            )
        except Exception as exc:
            yield event({"error": str(exc)}, "error")

    response = Response(generate(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


@app.post("/api/devices")
def add_device():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    if not is_admin_user(user_id):
        permissions = get_user_permissions(user_id)
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    ip_address = str(data.get("ip", "")).strip()
    mac_address = str(data.get("mac", "")).strip()
    if not name or not ip_address:
        return {"error": "missing fields"}, 400

    if not re.fullmatch(r"[A-Za-z0-9 ._-]+", name):
        return {"error": "invalid name"}, 400

    if not re.fullmatch(r"[0-9.]{7,15}", ip_address):
        return {"error": "invalid ip"}, 400

    if mac_address:
        if not re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac_address):
            return {"error": "invalid mac"}, 400
    else:
        mac_address = None

    db = get_db()
    db.execute(
        "INSERT INTO devices (name, ip_address, mac_address, created_at) VALUES (?, ?, ?, ?)",
        (name, ip_address, mac_address, datetime.utcnow().isoformat()),
    )
    db.commit()
    return {"ok": True}


@app.delete("/api/devices/<int:device_id>")
def delete_device(device_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    if not is_admin_user(user_id):
        permissions = get_user_permissions(user_id)
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403

    db = get_db()
    db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    db.execute("DELETE FROM plc_points WHERE device_id = ?", (device_id,))
    db.execute("DELETE FROM user_device_permissions WHERE device_id = ?", (device_id,))
    db.execute("DELETE FROM user_device_activity WHERE device_id = ?", (device_id,))
    db.commit()
    with PLC_IO_LOCK:
        PLC_IO_STATE.pop(device_id, None)
    return {"ok": True}


@app.post("/api/devices/<int:device_id>/mac")
def update_device_mac(device_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        permissions = get_user_permissions(user_id)
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403

    db = get_db()
    row = db.execute(
        "SELECT id, ip_address FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if row is None:
        return {"error": "device not found"}, 404

    mac = resolve_mac_for_ip(row["ip_address"])
    if not mac:
        return {"error": "mac not found"}, 404

    db.execute(
        "UPDATE devices SET mac_address = ? WHERE id = ?",
        (mac, device_id),
    )
    db.commit()
    return {"ok": True, "mac": mac}


@app.get("/api/device/<int:device_id>/plc/io")
def get_device_plc_io(device_id: int):
    api_error = check_api_enabled()
    if api_error:
        return api_error
    
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    permissions = get_user_permissions(user_id)
    if not is_admin_user(user_id):
        if not permissions["can_view_devices"]:
            return {"error": "forbidden"}, 403
        device_access = permissions["device_access"]
        if device_access is not None and device_id not in device_access:
            return {"error": "forbidden"}, 403

    db = get_db()
    row = db.execute(
        "SELECT id, name, ip_address, mac_address FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if row is None:
        return {"error": "device not found"}, 404

    device_name = str(row["name"] or "")
    ip_address = str(row["ip_address"] or "")
    if not is_plc_like_device(device_name, ip_address):
        return {"error": "device is geen PLC"}, 400

    configured_points = build_plc_point_entries(device_id)
    if not configured_points:
        with PLC_IO_LOCK:
            PLC_IO_STATE[device_id] = []
        return {
            "device": {
                "id": row["id"],
                "name": row["name"],
                "ip": row["ip_address"],
                "mac": row["mac_address"],
            },
            "mode": "config",
            "source": "handmatige-configuratie",
            "io": [],
        }

    bridge_sync_plc_points(ip_address, configured_points)

    bridge_entries, source, bridge_reachable = bridge_fetch_plc_io(ip_address)
    if bridge_entries is not None:
        with PLC_IO_LOCK:
            PLC_IO_STATE[device_id] = [dict(item) for item in bridge_entries]
        io_entries = bridge_entries
        mode = "live"
    elif bridge_reachable:
        io_entries = configured_points
        source = "bridge-api"
        mode = "live"
        with PLC_IO_LOCK:
            PLC_IO_STATE[device_id] = [dict(item) for item in io_entries]
    else:
        io_entries = get_or_seed_plc_io_state(device_id, ip_address)
        source = "lokale-simulatie"
        mode = "simulatie"

    return {
        "device": {
            "id": row["id"],
            "name": row["name"],
            "ip": row["ip_address"],
            "mac": row["mac_address"],
        },
        "mode": mode,
        "source": source,
        "io": io_entries,
    }


@app.get("/api/device/<int:device_id>/plc/points")
def get_device_plc_points_api(device_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    permissions = get_user_permissions(user_id)
    if not is_admin_user(user_id):
        if not permissions["can_view_devices"]:
            return {"error": "forbidden"}, 403
        device_access = permissions["device_access"]
        if device_access is not None and device_id not in device_access:
            return {"error": "forbidden"}, 403

    return {"points": get_device_plc_points(device_id)}


@app.post("/api/device/<int:device_id>/plc/points")
def create_device_plc_point_api(device_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    permissions = get_user_permissions(user_id)
    if not is_admin_user(user_id):
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403
        device_access = permissions["device_access"]
        if device_access is not None and device_id not in device_access:
            return {"error": "forbidden"}, 403

    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    tag = str(payload.get("tag") or "").strip().upper()
    if not name:
        return {"error": "Naam is verplicht"}, 400
    if not PLC_TAG_RE.fullmatch(tag):
        return {"error": "Ongeldig tagformaat. Gebruik bv. I0.0, Q0.1 of M0.0"}, 400

    db = get_db()
    device_row = db.execute("SELECT id FROM devices WHERE id = ?", (device_id,)).fetchone()
    if device_row is None:
        return {"error": "device not found"}, 404

    try:
        cursor = db.execute(
            "INSERT INTO plc_points (device_id, name, tag, created_at) VALUES (?, ?, ?, ?)",
            (device_id, name, tag, datetime.utcnow().isoformat()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return {"error": "Tag bestaat al voor dit apparaat"}, 409

    with PLC_IO_LOCK:
        PLC_IO_STATE.pop(device_id, None)

    return {
        "ok": True,
        "point": {
            "id": int(cursor.lastrowid),
            "name": name,
            "tag": tag,
            "io_type": infer_plc_point_type(tag),
            "writable": is_plc_point_writable(tag),
        },
    }, 201


@app.delete("/api/device/<int:device_id>/plc/points/<int:point_id>")
def delete_device_plc_point_api(device_id: int, point_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    permissions = get_user_permissions(user_id)
    if not is_admin_user(user_id):
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403
        device_access = permissions["device_access"]
        if device_access is not None and device_id not in device_access:
            return {"error": "forbidden"}, 403

    db = get_db()
    cursor = db.execute("DELETE FROM plc_points WHERE id = ? AND device_id = ?", (point_id, device_id))
    db.commit()
    if cursor.rowcount <= 0:
        return {"error": "PLC-punt niet gevonden"}, 404

    with PLC_IO_LOCK:
        PLC_IO_STATE.pop(device_id, None)

    return {"ok": True}


@app.post("/api/device/<int:device_id>/plc/io/<path:tag>/toggle")
def toggle_device_plc_output(device_id: int, tag: str):
    api_error = check_api_enabled()
    if api_error:
        return api_error
    
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    permissions = get_user_permissions(user_id)
    if not is_admin_user(user_id):
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403
        device_access = permissions["device_access"]
        if device_access is not None and device_id not in device_access:
            return {"error": "forbidden"}, 403

    clean_tag = str(tag or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", clean_tag):
        return {"error": "invalid tag"}, 400

    db = get_db()
    row = db.execute(
        "SELECT id, name, ip_address FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if row is None:
        return {"error": "device not found"}, 404

    device_name = str(row["name"] or "")
    ip_address = str(row["ip_address"] or "")
    if not is_plc_like_device(device_name, ip_address):
        return {"error": "device is geen PLC"}, 400

    configured_points = get_device_plc_points(device_id)
    target_point = next((point for point in configured_points if str(point["tag"]).upper() == clean_tag.upper()), None)
    if target_point is None:
        return {"error": "PLC-punt niet geconfigureerd"}, 404
    if not bool(target_point.get("writable", False)):
        return {"error": "PLC-punt is niet schrijfbaar"}, 400

    bridge_sync_plc_points(ip_address, build_plc_point_entries(device_id))

    used_source = "lokale-simulatie"
    bridge_ok, bridge_reachable, bridge_error = bridge_toggle_plc_io(ip_address, clean_tag)
    if bridge_ok:
        used_source = "bridge-api"
        updated, _, _ = bridge_fetch_plc_io(ip_address)
        if updated:
            with PLC_IO_LOCK:
                PLC_IO_STATE[device_id] = [dict(item) for item in updated]
            return {"ok": True, "source": used_source, "io": updated}

    if bridge_reachable:
        return {"error": bridge_error or "Bridge-write faalde"}, 502

    return {
        "error": "Bridge niet bereikbaar. PLC-write niet uitgevoerd.",
    }, 503


@app.post("/api/device/<int:device_id>/plc/io/<path:tag>/set")
def set_device_plc_point(device_id: int, tag: str):
    api_error = check_api_enabled()
    if api_error:
        return api_error
    
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    permissions = get_user_permissions(user_id)
    if not is_admin_user(user_id):
        if not permissions["can_manage_devices"]:
            return {"error": "forbidden"}, 403
        device_access = permissions["device_access"]
        if device_access is not None and device_id not in device_access:
            return {"error": "forbidden"}, 403

    clean_tag = str(tag or "").strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", clean_tag):
        return {"error": "invalid tag"}, 400

    payload = request.get_json(silent=True) or {}
    if "value" not in payload:
        return {"error": "Waarde ontbreekt"}, 400
    target_value = bool(int(payload.get("value", 0))) if str(payload.get("value")).strip() in {"0", "1"} else bool(payload.get("value"))

    db = get_db()
    row = db.execute(
        "SELECT id, name, ip_address FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if row is None:
        return {"error": "device not found"}, 404

    device_name = str(row["name"] or "")
    ip_address = str(row["ip_address"] or "")
    if not is_plc_like_device(device_name, ip_address):
        return {"error": "device is geen PLC"}, 400

    configured_points = get_device_plc_points(device_id)
    target_point = next((point for point in configured_points if str(point["tag"]).upper() == clean_tag), None)
    if target_point is None:
        return {"error": "PLC-punt niet geconfigureerd"}, 404
    if not bool(target_point.get("writable", False)):
        return {"error": "PLC-punt is niet schrijfbaar"}, 400

    bridge_sync_plc_points(ip_address, build_plc_point_entries(device_id))
    bridge_ok, bridge_reachable, bridge_error = bridge_set_plc_io(ip_address, clean_tag, target_value)
    if bridge_ok:
        updated, _, _ = bridge_fetch_plc_io(ip_address)
        if updated:
            with PLC_IO_LOCK:
                PLC_IO_STATE[device_id] = [dict(item) for item in updated]
            return {"ok": True, "source": "bridge-api", "io": updated}
        return {"ok": True, "source": "bridge-api", "io": get_or_seed_plc_io_state(device_id, ip_address)}

    if bridge_reachable:
        return {"error": bridge_error or "Bridge-write faalde"}, 502
    return {"error": "Bridge niet bereikbaar. PLC-write niet uitgevoerd."}, 503


@app.get("/api/admin/users")
def admin_users():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    is_admin = is_admin_user(user_id)
    is_teacher = is_authorized_teacher(user_id)
    if not is_admin and not is_teacher:
        return {"error": "forbidden"}, 403

    db = get_db()
    rows = db.execute(
        """
        SELECT users.id as user_id,
               users.username as username,
               users.role as role,
               users.category as category,
               groups.id as group_id,
               groups.name as group_name
        FROM users
        LEFT JOIN user_groups ON users.id = user_groups.user_id
        LEFT JOIN groups ON groups.id = user_groups.group_id
        ORDER BY users.username
        """
    ).fetchall()

    allowed_groups = None
    if is_teacher and not is_admin:
        allowed_groups = get_authorized_group_ids(user_id)

    grouped: dict[int, dict[str, object]] = {}
    for row in rows:
        if allowed_groups is not None:
            if not row["group_id"] or row["group_id"] not in allowed_groups:
                continue
        entry = grouped.setdefault(
            row["user_id"],
            {
                "id": row["user_id"],
                "username": row["username"],
                "role": row["role"],
                "category": row["category"],
                "is_super_author": is_super_author_user_id(row["user_id"]),
                "groups": [],
            },
        )
        if row["group_id"]:
            entry["groups"].append({"id": row["group_id"], "name": row["group_name"]})

    return {"users": list(grouped.values())}


@app.post("/api/admin/users")
def admin_create_user():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()
    role = str(data.get("role", "user")).strip().lower()
    category = str(data.get("category", "student")).strip().lower()
    group_id = data.get("group_id")

    if not username or not password:
        return {"error": "missing fields"}, 400
    if role not in {"user", "iter", "admin", "author"}:
        return {"error": "invalid role"}, 400
    if role == "author":
        return {"error": "forbidden_super_author"}, 403
    category = normalize_category(category)
    if category not in {"student", "authorized_student", "teacher", "authorized_teacher"}:
        return {"error": "invalid category"}, 400

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO users (username, password_hash, role, category, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, generate_password_hash(password), role, category, datetime.utcnow().isoformat()),
        )
    except sqlite3.IntegrityError:
        return {"error": "username exists"}, 400

    user_id = cursor.lastrowid
    group_id_value = None
    if group_id is not None:
        try:
            parsed_group_id = int(group_id)
        except (TypeError, ValueError):
            parsed_group_id = None
        if parsed_group_id:
            group_id_value = parsed_group_id
            group_ids = [parsed_group_id] + get_group_ancestor_ids(parsed_group_id)
            db.executemany(
                "INSERT OR IGNORE INTO user_groups (user_id, group_id) VALUES (?, ?)",
                [(user_id, group_item) for group_item in group_ids],
            )
    db.commit()
    return {"ok": True, "user_id": user_id, "group_id": group_id_value}


@app.patch("/api/admin/users/<int:target_id>")
def admin_update_user(target_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403
    if is_super_author_user_id(target_id):
        return {"error": "forbidden_super_author"}, 403

    data = request.get_json(silent=True) or {}
    role = data.get("role")
    category = data.get("category")
    password = data.get("password")

    updates = []
    values: list[object] = []
    if role is not None:
        role = str(role).strip().lower()
        if role not in {"user", "iter", "admin", "author"}:
            return {"error": "invalid role"}, 400
        if role == "author":
            return {"error": "forbidden_super_author"}, 403
        updates.append("role = ?")
        values.append(role)
    if category is not None:
        category = normalize_category(category)
        if category not in {"student", "authorized_student", "teacher", "authorized_teacher"}:
            return {"error": "invalid category"}, 400
        updates.append("category = ?")
        values.append(category)
    if password:
        updates.append("password_hash = ?")
        values.append(generate_password_hash(str(password)))

    if not updates:
        return {"ok": True}

    db = get_db()
    values.append(target_id)
    db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(values))
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/users/<int:target_id>")
def admin_delete_user(target_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403
    if target_id == user_id:
        return {"error": "cannot_delete_self"}, 403
    if is_super_author_user_id(target_id):
        return {"error": "forbidden_super_author"}, 403

    db = get_db()
    db.execute("DELETE FROM user_groups WHERE user_id = ?", (target_id,))
    db.execute("DELETE FROM user_permissions WHERE user_id = ?", (target_id,))
    db.execute("DELETE FROM user_module_permissions WHERE user_id = ?", (target_id,))
    db.execute("DELETE FROM user_device_permissions WHERE user_id = ?", (target_id,))
    db.execute("DELETE FROM users WHERE id = ?", (target_id,))
    db.commit()
    return {"ok": True}


@app.get("/api/admin/groups")
def admin_groups():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    is_admin = is_admin_user(user_id)
    is_teacher = is_authorized_teacher(user_id)
    if not is_admin and not is_teacher:
        return {"error": "forbidden"}, 403

    db = get_db()
    rows = db.execute("SELECT id, name, parent_id FROM groups ORDER BY name").fetchall()
    if is_teacher and not is_admin:
        allowed_groups = get_authorized_group_ids(user_id)
        rows = [row for row in rows if row["id"] in allowed_groups]
    return {
        "groups": [
            {"id": row["id"], "name": row["name"], "parent_id": row["parent_id"]}
            for row in rows
        ]
    }


@app.post("/api/admin/groups")
def admin_create_group():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    parent_id = data.get("parent_id")
    if not name:
        return {"error": "missing name"}, 400

    db = get_db()
    try:
        db.execute("INSERT INTO groups (name, parent_id) VALUES (?, ?)", (name, parent_id))
    except sqlite3.IntegrityError:
        return {"error": "group exists"}, 400
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/groups/<int:group_id>")
def admin_delete_group(group_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    db = get_db()
    db.execute("DELETE FROM user_groups WHERE group_id = ?", (group_id,))
    db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    db.commit()
    return {"ok": True}


@app.post("/api/admin/user-groups")
def admin_update_user_groups():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    target_id = int(data.get("user_id", 0))
    group_ids = data.get("group_ids", [])
    if not target_id:
        return {"error": "user_id required"}, 400
    if is_super_author_user_id(target_id):
        return {"error": "forbidden_super_author"}, 403

    db = get_db()
    db.execute("DELETE FROM user_groups WHERE user_id = ?", (target_id,))
    if isinstance(group_ids, list):
        expanded_ids: set[int] = set()
        for group_id in group_ids:
            try:
                parsed_group_id = int(group_id)
            except (TypeError, ValueError):
                continue
            if not parsed_group_id:
                continue
            expanded_ids.add(parsed_group_id)
            expanded_ids.update(get_group_ancestor_ids(parsed_group_id))
        db.executemany(
            "INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)",
            [(target_id, group_item) for group_item in sorted(expanded_ids)],
        )
    db.commit()
    return {"ok": True}


@app.get("/api/admin/device-activity")
def admin_device_activity():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401
    if not is_admin_user(user_id):
        return {"error": "forbidden"}, 403

    db = get_db()
    rows = db.execute(
        """
        SELECT users.id as user_id,
               users.username as username,
               devices.id as device_id,
               devices.name as device_name,
               devices.ip_address as ip_address,
               devices.mac_address as mac_address,
               user_device_activity.last_seen as last_seen
        FROM user_device_activity
        JOIN users ON users.id = user_device_activity.user_id
        JOIN devices ON devices.id = user_device_activity.device_id
        ORDER BY users.username, user_device_activity.last_seen DESC
        """
    ).fetchall()

    grouped: dict[int, dict[str, object]] = {}
    for row in rows:
        entry = grouped.setdefault(
            row["user_id"],
            {"user_id": row["user_id"], "username": row["username"], "devices": []},
        )
        entry["devices"].append(
            {
                "id": row["device_id"],
                "name": row["device_name"],
                "ip": row["ip_address"],
                "mac": row["mac_address"],
                "last_seen": row["last_seen"],
            }
        )

    return {"users": list(grouped.values())}


@app.get("/api/admin/permissions")
def admin_get_permissions():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    target_id = request.args.get("user_id", type=int)
    if not target_id:
        return {"error": "user_id required"}, 400
    if is_super_author_user_id(target_id):
        return {"error": "forbidden_super_author"}, 403
    if not can_manage_student_settings(user_id, target_id):
        return {"error": "forbidden"}, 403

    return get_user_permissions(target_id)


@app.post("/api/admin/permissions")
def admin_set_permissions():
    user_id = session.get("user_id")
    if not user_id:
        return {"error": "unauthorized"}, 401

    data = request.get_json(silent=True) or {}
    target_id = int(data.get("user_id", 0))
    if not target_id:
        return {"error": "user_id required"}, 400
    if target_id == user_id:
        return {"error": "cannot_edit_self"}, 403
    if is_super_author_user_id(target_id):
        return {"error": "forbidden_super_author"}, 403
    if not can_manage_student_settings(user_id, target_id):
        return {"error": "forbidden"}, 403

    allowed_modules = data.get("allowed_modules", MODULE_KEYS)
    allowed_modules = [m for m in allowed_modules if m in MODULE_KEYS]
    can_view_devices = bool(data.get("can_view_devices", True))
    can_manage_devices = bool(data.get("can_manage_devices", True))
    device_access = data.get("device_access")

    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO user_permissions (user_id, can_view_devices, can_manage_devices, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET can_view_devices = excluded.can_view_devices, can_manage_devices = excluded.can_manage_devices, updated_at = excluded.updated_at",
        (target_id, int(can_view_devices), int(can_manage_devices), now),
    )

    db.execute("DELETE FROM user_module_permissions WHERE user_id = ?", (target_id,))
    db.executemany(
        "INSERT INTO user_module_permissions (user_id, module_key, allowed) VALUES (?, ?, ?)",
        [(target_id, key, 1 if key in allowed_modules else 0) for key in MODULE_KEYS],
    )

    db.execute("DELETE FROM user_device_permissions WHERE user_id = ?", (target_id,))
    if isinstance(device_access, list):
        db.executemany(
            "INSERT INTO user_device_permissions (user_id, device_id, allowed) VALUES (?, ?, ?)",
            [(target_id, int(device_id), 1) for device_id in device_access],
        )

    db.commit()
    return {"ok": True}


def default_layout_json() -> str:
    layout = [
        {
            "id": "module-welcome",
            "key": "info",
            "title": "Info / Notities",
            "x": 1,
            "y": 1,
            "w": 3,
            "h": 2,
        },
        {
            "id": "module-status",
            "key": "stats",
            "title": "Status",
            "x": 4,
            "y": 1,
            "w": 3,
            "h": 2,
        },
        {
            "id": "module-arp",
            "key": "arp",
            "title": "ARP Tabel",
            "x": 1,
            "y": 3,
            "w": 6,
            "h": 3,
        },
    ]
    return json.dumps(layout)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000, debug=True)
