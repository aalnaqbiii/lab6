import os
import sqlite3
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", ""),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
    MAX_CONTENT_LENGTH=64 * 1024,
)
if len(app.config["SECRET_KEY"]) < 32:
    raise RuntimeError("Set SECRET_KEY in .env to a random value of at least 32 characters.")
CSRFProtect(app)
DATABASE = os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "notes.sqlite3"))


def connect_db():
    Path(DATABASE).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    with connect_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)


@app.cli.command("init-db")
def init_db_command():
    "Initialize the SQLite database tables."
    init_db()
    print(f"Database initialized at {DATABASE}")


@app.before_request
def load_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        with connect_db() as db:
            g.user = db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if g.user is None:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.get("/")
def index():
    if g.user:
        return redirect(url_for("notes"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not 3 <= len(username) <= 40 or not username.replace("_", "").replace("-", "").isalnum():
            flash("Use 3–40 letters, numbers, hyphens, or underscores for your username.", "error")
        elif len(password) < 10:
            flash("Choose a password with at least 10 characters.", "error")
        else:
            try:
                with connect_db() as db:
                    cur = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                                     (username, generate_password_hash(password)))
                    session.clear()
                    session["user_id"] = cur.lastrowid
                flash("Your account is ready. Add your first note.", "success")
                return redirect(url_for("notes"))
            except sqlite3.IntegrityError:
                flash("That username is already registered.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with connect_db() as db:
            user = db.execute("SELECT id, username, password_hash FROM users WHERE username = ? COLLATE NOCASE",
                              (username,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Username or password is incorrect.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash("You are signed in.", "success")
            return redirect(url_for("notes"))
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You are signed out.", "success")
    return redirect(url_for("index"))


@app.get("/notes")
@login_required
def notes():
    with connect_db() as db:
        rows = db.execute("SELECT id, title, body, updated_at FROM notes WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
                          (g.user["id"],)).fetchall()
    return render_template("notes.html", notes=rows)


@app.route("/notes/new", methods=["GET", "POST"])
@login_required
def new_note():
    if request.method == "POST":
        title, body = request.form.get("title", "").strip(), request.form.get("body", "").strip()
        if not title or len(title) > 120 or len(body) > 10000:
            flash("Add a title (up to 120 characters); note text can be up to 10,000 characters.", "error")
        else:
            with connect_db() as db:
                db.execute("INSERT INTO notes (user_id, title, body) VALUES (?, ?, ?)", (g.user["id"], title, body))
            flash("Note saved to the database.", "success")
            return redirect(url_for("notes"))
    return render_template("note_form.html", note=None, heading="New note")


def owned_note(note_id):
    with connect_db() as db:
        note = db.execute("SELECT id, title, body FROM notes WHERE id = ? AND user_id = ?",
                          (note_id, g.user["id"])).fetchone()
    if note is None:
        abort(404)
    return note


@app.route("/notes/<int:note_id>/edit", methods=["GET", "POST"])
@login_required
def edit_note(note_id):
    note = owned_note(note_id)
    if request.method == "POST":
        title, body = request.form.get("title", "").strip(), request.form.get("body", "").strip()
        if not title or len(title) > 120 or len(body) > 10000:
            flash("Add a title (up to 120 characters); note text can be up to 10,000 characters.", "error")
        else:
            with connect_db() as db:
                db.execute("UPDATE notes SET title = ?, body = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                           (title, body, note_id, g.user["id"]))
            flash("Note updated.", "success")
            return redirect(url_for("notes"))
    return render_template("note_form.html", note=note, heading="Edit note")


@app.post("/notes/<int:note_id>/delete")
@login_required
def delete_note(note_id):
    owned_note(note_id)
    with connect_db() as db:
        db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, g.user["id"]))
    flash("Note deleted.", "success")
    return redirect(url_for("notes"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=False)
