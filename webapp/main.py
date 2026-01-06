from __future__ import annotations

import hashlib
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from mysql.connector import errors, pooling

app = FastAPI(title="Light Admin Panel", version="0.2.0")

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SESSION_COOKIE = "session_user"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_env_file() -> None:
    """Minimal .env parser to load DB settings without extra deps."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@lru_cache(maxsize=1)
def db_config() -> Dict[str, object]:
    load_env_file()
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "cloudauth"),
        "port": int(os.getenv("DB_PORT", "3306")),
    }


@lru_cache(maxsize=1)
def get_db_pool() -> pooling.MySQLConnectionPool:
    cfg = db_config()
    try:
        return pooling.MySQLConnectionPool(pool_name="cloudauth_pool", pool_size=5, **cfg)
    except errors.Error as exc:
        raise RuntimeError(f"Database connection failed: {exc}") from exc


def get_connection():
    try:
        return get_db_pool().get_connection()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Database unavailable.") from exc


def get_user(username: str) -> Optional[Dict[str, object]]:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username=%s", (username,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        cur.close()
        conn.close()


def list_users() -> List[Dict[str, object]]:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT username, is_admin, created_at FROM users ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def list_users_with_ids() -> List[Dict[str, object]]:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY id DESC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def admin_count() -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE is_admin=1")
        (count,) = cur.fetchone()
        return int(count)
    finally:
        cur.close()
        conn.close()


@lru_cache(maxsize=1)
def ensure_login_events_table() -> None:
    """Create the login_events table once at runtime if it is missing."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS login_events (
              id INT AUTO_INCREMENT PRIMARY KEY,
              username VARCHAR(100) NOT NULL,
              logged_in_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              INDEX idx_login_events_logged_in_at (logged_in_at)
            )
            """
        )
        conn.commit()
    except errors.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to initialize login history: {exc}") from exc
    finally:
        cur.close()
        conn.close()


def record_login_event(username: str) -> None:
    ensure_login_events_table()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO login_events (username) VALUES (%s)", (username,))
        conn.commit()
    except errors.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to record login event: {exc}") from exc
    finally:
        cur.close()
        conn.close()


def list_login_events(limit: int = 50) -> List[Dict[str, object]]:
    ensure_login_events_table()
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, username, logged_in_at FROM login_events ORDER BY logged_in_at DESC LIMIT %s",
            (int(limit),),
        )
        return [dict(row) for row in cur.fetchall()]
    except errors.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read login history: {exc}") from exc
    finally:
        cur.close()
        conn.close()


def list_login_events_admin(limit: int = 200) -> List[Dict[str, object]]:
    return list_login_events(limit=limit)


def parse_timestamp(value: str) -> str:
    cleaned = value.strip()
    cleaned = cleaned.replace("T", " ")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid timestamp format.") from exc
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def update_login_event(event_id: int, username: str, logged_in_at: str) -> None:
    ensure_login_events_table()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM login_events WHERE id=%s", (event_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Login event not found.")
        cur.execute(
            "UPDATE login_events SET username=%s, logged_in_at=%s WHERE id=%s",
            (username, parse_timestamp(logged_in_at), event_id),
        )
        conn.commit()
    except HTTPException:
        raise
    except errors.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update login event: {exc}") from exc
    finally:
        cur.close()
        conn.close()


def delete_login_event(event_id: int) -> None:
    ensure_login_events_table()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM login_events WHERE id=%s", (event_id,))
        conn.commit()
    except errors.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete login event: {exc}") from exc
    finally:
        cur.close()
        conn.close()


def create_user(username: str, password: str, is_admin: bool) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)",
            (username, hash_password(password), is_admin),
        )
        conn.commit()
    except errors.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="User already exists.") from exc
    except errors.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {exc}") from exc
    finally:
        cur.close()
        conn.close()


def set_admin_flag(username: str, is_admin: bool) -> None:
    """Update a user's admin flag with guardrails to avoid losing all admins."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_admin FROM users WHERE username=%s", (username,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")

        current_admin = bool(row[0])
        # Do not remove the last remaining admin account.
        if current_admin and not is_admin:
            cur.execute("SELECT COUNT(*) FROM users WHERE is_admin=1")
            (admin_total,) = cur.fetchone()
            if int(admin_total) <= 1:
                raise HTTPException(status_code=400, detail="Cannot remove the last admin.")

        if current_admin == is_admin:
            return

        cur.execute("UPDATE users SET is_admin=%s WHERE username=%s", (is_admin, username))
        conn.commit()
    except HTTPException:
        raise
    except errors.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update admin flag: {exc}") from exc
    finally:
        cur.close()
        conn.close()


def update_user_record(user_id: int, username: str, is_admin: bool, new_password: Optional[str]) -> None:
    """Admin-only edit of user fields with guardrails."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, username, is_admin FROM users WHERE id=%s", (user_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")

        current_admin = bool(row["is_admin"])
        if current_admin and not is_admin:
            cur.execute("SELECT COUNT(*) FROM users WHERE is_admin=1")
            (admin_total,) = cur.fetchone()
            if int(admin_total) <= 1:
                raise HTTPException(status_code=400, detail="Cannot remove the last admin.")

        params = [username, int(is_admin)]
        set_clauses = ["username=%s", "is_admin=%s"]

        if new_password:
            params.append(hash_password(new_password))
            set_clauses.append("password_hash=%s")

        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE id=%s"
        cur.execute(sql, tuple(params))
        conn.commit()
    except HTTPException:
        raise
    except errors.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="Username already exists.") from exc
    except errors.Error as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update user: {exc}") from exc
    finally:
        cur.close()
        conn.close()


def current_user(request: Request) -> Optional[Dict[str, object]]:
    username = request.cookies.get(SESSION_COOKIE)
    if not username:
        return None
    return get_user(username)


def render_page(title: str, body: str, user: Optional[Dict[str, object]] = None) -> HTMLResponse:
    navbar = f"""
    <header class="nav">
      <div class="logo">CloudAuth</div>
      <nav>
        <a href="/">Home</a>
        <a href="/logins">Login history</a>
        {'<a href="/admin">Admin</a>' if user and user.get('is_admin') else ''}
        {'<a href="/logout">Logout</a>' if user else '<a href="/login">Login</a>'}
        {'<a class="ghost" href="/register">Create account</a>' if not user else ''}
      </nav>
    </header>
    """
    html = f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>{title}</title>
      <style>
        :root {{
          --bg: #f7f8fb;
          --card: #ffffff;
          --text: #1d1f27;
          --muted: #6b7280;
          --primary: #2563eb;
          --accent: #10b981;
          --border: #e5e7eb;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
          background: radial-gradient(circle at 20% 20%, #eef2ff, #f7f8fb 35%), radial-gradient(circle at 80% 0%, #ecfdf3, #f7f8fb 40%), var(--bg);
          color: var(--text);
          min-height: 100vh;
        }}
        .nav {{
          position: sticky;
          top: 0;
          backdrop-filter: blur(10px);
          background: rgba(255,255,255,0.8);
          border-bottom: 1px solid var(--border);
          padding: 14px 28px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
        }}
        .nav a {{
          color: var(--text);
          text-decoration: none;
          margin-left: 14px;
          font-weight: 600;
          transition: color 0.15s ease, transform 0.15s ease;
        }}
        .nav a:hover {{ color: var(--primary); transform: translateY(-1px); }}
        .nav .ghost {{
          border: 1px solid var(--border);
          padding: 6px 12px;
          border-radius: 10px;
          background: linear-gradient(120deg, rgba(37,99,235,0.08), rgba(16,185,129,0.08));
        }}
        .logo {{ font-weight: 800; letter-spacing: 0.5px; }}
        .wrap {{
          max-width: 960px;
          margin: 0 auto;
          padding: 32px 24px 48px;
        }}
        .card {{
          background: var(--card);
          border: 1px solid var(--border);
          border-radius: 16px;
          padding: 24px;
          box-shadow: 0 15px 40px rgba(0,0,0,0.04);
          margin-top: 18px;
        }}
        h1 {{ font-size: 28px; margin-bottom: 12px; }}
        h2 {{ font-size: 22px; margin: 18px 0 8px; }}
        p {{ color: var(--muted); line-height: 1.6; margin-bottom: 12px; }}
        form {{
          display: grid;
          gap: 12px;
          margin-top: 12px;
        }}
        label {{ font-weight: 600; color: var(--text); display: block; margin-bottom: 6px; }}
        input, select {{
          padding: 12px;
          border-radius: 12px;
          border: 1px solid var(--border);
          background: #f9fafb;
          font-size: 15px;
        }}
        button {{
          padding: 12px 16px;
          border: none;
          border-radius: 12px;
          background: linear-gradient(120deg, var(--primary), #3b82f6);
          color: white;
          font-weight: 700;
          cursor: pointer;
          transition: transform 0.12s ease, box-shadow 0.12s ease;
          box-shadow: 0 8px 20px rgba(37,99,235,0.22);
        }}
        button:hover {{ transform: translateY(-1px); box-shadow: 0 10px 24px rgba(37,99,235,0.25); }}
        .pill {{
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 8px 12px;
          border-radius: 999px;
          background: rgba(16,185,129,0.12);
          color: #065f46;
          font-weight: 700;
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }}
        .error {{
          padding: 10px 12px;
          border-radius: 12px;
          background: rgba(239,68,68,0.08);
          color: #b91c1c;
          border: 1px solid rgba(248,113,113,0.5);
        }}
        .success {{
          padding: 10px 12px;
          border-radius: 12px;
          background: rgba(16,185,129,0.1);
          color: #065f46;
          border: 1px solid rgba(16,185,129,0.4);
        }}
        .user-actions {{
          margin-top: 12px;
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          align-items: center;
        }}
        .login-list {{
          display: flex;
          flex-direction: column;
          gap: 10px;
          margin-top: 12px;
        }}
        .login-row {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px;
          border-radius: 12px;
          border: 1px solid var(--border);
          background: #f9fafb;
        }}
        .table {{
          display: flex;
          flex-direction: column;
          gap: 12px;
        }}
        .table-row {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 12px;
          align-items: end;
          padding: 12px;
          border-radius: 14px;
          border: 1px solid var(--border);
          background: #f9fafb;
        }}
        .row-actions {{
          display: flex;
          gap: 8px;
          align-items: center;
        }}
        .ghost-btn {{
          background: transparent;
          color: var(--text);
          border: 1px dashed var(--border);
          box-shadow: none;
        }}
        .danger {{
          background: linear-gradient(120deg, #ef4444, #dc2626);
          box-shadow: 0 8px 20px rgba(239,68,68,0.2);
        }}
        .muted {{ color: var(--muted); }}
      </style>
    </head>
    <body>
      {navbar}
      <main class="wrap">
        {body}
      </main>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.get("/", response_class=HTMLResponse)
def landing(request: Request, user: Optional[Dict[str, object]] = Depends(current_user)) -> HTMLResponse:
    hero = f"""
    <section class="card">
      <div class="pill">Light theme</div>
      <h1>Welcome to your admin panel</h1>
      <p>Manage users with a MariaDB backend. The first account becomes admin automatically.</p>
      {"<p><strong>Signed in as:</strong> " + user["username"] + (" (admin)" if user.get("is_admin") else "") + "</p>" if user else "<p>Sign in or create an account to get started.</p>"}
    </section>
    """
    if user and user.get("is_admin"):
        hero += """
        <section class="card">
          <h2>Admin shortcuts</h2>
          <p>Visit the admin panel to review accounts.</p>
          <a href="/admin"><button>Open admin panel</button></a>
        </section>
        """
    return render_page("Home", hero, user)


@app.get("/logins", response_class=HTMLResponse)
def login_history(request: Request, user: Optional[Dict[str, object]] = Depends(current_user)) -> HTMLResponse:
    events = list_login_events()
    event_items = "".join(
        f"""
        <div class="login-row">
          <div>
            <strong>{e["username"]}</strong>
            <div class="muted">Signed in at {e["logged_in_at"]}</div>
          </div>
        </div>
        """
        for e in events
    )
    body = f"""
    <section class="card">
      <div class="pill">Audit</div>
      <h1>Recent logins</h1>
      <p>Latest successful logins across all users (most recent first).</p>
      <div class="login-list">
        {event_items if event_items else "<p class='muted'>No logins recorded yet.</p>"}
      </div>
    </section>
    """
    return render_page("Login history", body, user)


@app.get("/login", response_class=HTMLResponse)
def login_view(request: Request, user: Optional[Dict[str, object]] = Depends(current_user), error: str = "") -> HTMLResponse:
    if user:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    body = f"""
    <section class="card">
      <h1>Login</h1>
      {'<div class="error">' + error + '</div>' if error else ''}
      <form method="post" action="/login">
        <div>
          <label for="username">Username</label>
          <input id="username" name="username" placeholder="jane" required />
        </div>
        <div>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" placeholder="******" required />
        </div>
        <button type="submit">Sign in</button>
      </form>
    </section>
    """
    return render_page("Login", body, None)


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    user = get_user(username)
    if not user or user["password_hash"] != hash_password(password):
        return RedirectResponse("/login?error=Invalid%20credentials", status_code=status.HTTP_303_SEE_OTHER)
    record_login_event(username)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(SESSION_COOKIE, username, httponly=True, samesite="lax")
    return response


@app.get("/register", response_class=HTMLResponse)
def register_view(request: Request, user: Optional[Dict[str, object]] = Depends(current_user), error: str = "") -> HTMLResponse:
    if user:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    body = f"""
    <section class="card">
      <h1>Create account</h1>
      <p>The first user becomes an admin automatically.</p>
      {'<div class="error">' + error + '</div>' if error else ''}
      <form method="post" action="/register">
        <div>
          <label for="username">Username</label>
          <input id="username" name="username" placeholder="jane" required />
        </div>
        <div>
          <label for="password">Password</label>
          <input id="password" name="password" type="password" placeholder="Choose a strong password" required />
        </div>
        <button type="submit">Create account</button>
      </form>
    </section>
    """
    return render_page("Register", body, None)


@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    if get_user(username):
        return RedirectResponse("/register?error=User%20already%20exists", status_code=status.HTTP_303_SEE_OTHER)

    is_first_admin = admin_count() == 0
    try:
        create_user(username, password, is_first_admin)
    except HTTPException as exc:
        if exc.status_code == 400:
            return RedirectResponse("/register?error=User%20already%20exists", status_code=status.HTTP_303_SEE_OTHER)
        raise

    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(SESSION_COOKIE, username, httponly=True, samesite="lax")
    return response


@app.get("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/admin", response_class=HTMLResponse)
def admin_panel(
    request: Request,
    user: Optional[Dict[str, object]] = Depends(current_user),
    error: str = "",
    success: str = "",
) -> HTMLResponse:
    if not user:
        return RedirectResponse("/login?error=Login%20required", status_code=status.HTTP_303_SEE_OTHER)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")

    users = list_users()
    alerts = ""
    if error:
        alerts += f'<div class="error">{error}</div>'
    if success:
        alerts += f'<div class="success">{success}</div>'
    user_cards = "".join(
        f"""
        <div class="card">
          <h2>{u['username']}</h2>
          <p>Status: {"Admin" if u.get("is_admin") else "User"}</p>
          <p>Created: {u.get("created_at")}</p>
          <form class="user-actions" method="post" action="/admin/role">
            <input type="hidden" name="username" value="{u['username']}"/>
            <input type="hidden" name="is_admin" value="{0 if u.get("is_admin") else 1}"/>
            <button type="submit">{'Remove admin' if u.get('is_admin') else 'Make admin'}</button>
          </form>
        </div>
        """
        for u in users
    )
    body = f"""
    <section class="card">
      <div class="pill">Admin</div>
      <h1>Admin panel</h1>
      <p>Review who has access. Backed by MariaDB database <code>{db_config().get("database")}</code>.</p>
      <div class="user-actions">
        <a href="/admin/editor"><button class="ghost-btn">Open table editor</button></a>
      </div>
      {alerts}
    </section>
    {user_cards if user_cards else "<p>No users yet.</p>"}
    """
    return render_page("Admin", body, user)


@app.get("/admin/editor", response_class=HTMLResponse)
def table_editor(
    request: Request,
    user: Optional[Dict[str, object]] = Depends(current_user),
    error: str = "",
    success: str = "",
) -> HTMLResponse:
    if not user:
        return RedirectResponse("/login?error=Login%20required", status_code=status.HTTP_303_SEE_OTHER)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")

    users = list_users_with_ids()
    events = list_login_events_admin()

    alerts = ""
    if error:
        alerts += f'<div class="error">{error}</div>'
    if success:
        alerts += f'<div class="success">{success}</div>'

    user_rows = "".join(
        f"""
        <form class="table-row" method="post" action="/admin/editor/users/update">
          <input type="hidden" name="user_id" value="{u['id']}"/>
          <div>
            <label>Username</label>
            <input name="username" value="{u['username']}" required />
          </div>
          <div>
            <label>Role</label>
            <select name="is_admin">
              <option value="1" {"selected" if u["is_admin"] else ""}>Admin</option>
              <option value="0" {"selected" if not u["is_admin"] else ""}>User</option>
            </select>
          </div>
          <div>
            <label>New password</label>
            <input name="new_password" placeholder="Leave blank to keep" />
          </div>
          <div class="row-actions">
            <button type="submit">Save</button>
          </div>
        </form>
        """
        for u in users
    )

    def format_ts(ts_value: object) -> str:
        if hasattr(ts_value, "strftime"):
            return ts_value.strftime("%Y-%m-%dT%H:%M:%S")
        return str(ts_value).replace(" ", "T")

    event_rows = "".join(
        f"""
        <form class="table-row" method="post" action="/admin/editor/login/update">
          <input type="hidden" name="event_id" value="{e['id']}"/>
          <div>
            <label>User</label>
            <input name="username" value="{e['username']}" required />
          </div>
          <div>
            <label>Logged in at</label>
            <input type="datetime-local" name="logged_in_at" value="{format_ts(e['logged_in_at'])}" required />
          </div>
          <div class="row-actions">
            <button type="submit">Save</button>
            <button type="submit" class="ghost-btn danger" formaction="/admin/editor/login/delete" formnovalidate>Delete</button>
          </div>
        </form>
        """
        for e in events
    )

    body = f"""
    <section class="card">
      <div class="pill">Admin</div>
      <h1>Table editor</h1>
      <p>Directly view and edit database rows for users and login events. Admins only.</p>
      {alerts}
    </section>

    <section class="card">
      <h2>Users</h2>
      <p class="muted">Edit username, admin flag, or set a new password (leave blank to keep).</p>
      <div class="table">
        {user_rows if user_rows else "<p class='muted'>No users found.</p>"}
      </div>
    </section>

    <section class="card">
      <h2>Login events</h2>
      <p class="muted">Adjust or remove login records. Time uses your local timezone.</p>
      <div class="table">
        {event_rows if event_rows else "<p class='muted'>No login events found.</p>"}
      </div>
    </section>
    """
    return render_page("Table editor", body, user)


@app.post("/admin/role")
def update_admin_role(
    username: str = Form(...),
    is_admin: int = Form(...),
    user: Optional[Dict[str, object]] = Depends(current_user),
) -> RedirectResponse:
    if not user:
        return RedirectResponse("/login?error=Login%20required", status_code=status.HTTP_303_SEE_OTHER)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")

    try:
        set_admin_flag(username, bool(int(is_admin)))
    except HTTPException as exc:
        err = str(exc.detail)
        return RedirectResponse(f"/admin?error={quote(err)}", status_code=status.HTTP_303_SEE_OTHER)

    return RedirectResponse(f"/admin?success={quote(f'Updated admin access for {username}.')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/editor/users/update")
def admin_edit_user(
    user_id: int = Form(...),
    username: str = Form(...),
    is_admin: int = Form(...),
    new_password: str = Form(""),
    user: Optional[Dict[str, object]] = Depends(current_user),
) -> RedirectResponse:
    if not user:
        return RedirectResponse("/login?error=Login%20required", status_code=status.HTTP_303_SEE_OTHER)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    try:
        update_user_record(user_id, username, bool(int(is_admin)), new_password.strip() or None)
    except HTTPException as exc:
        return RedirectResponse(f"/admin/editor?error={quote(str(exc.detail))}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/admin/editor?success=User%20updated", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/editor/login/update")
def admin_edit_login_event(
    event_id: int = Form(...),
    username: str = Form(...),
    logged_in_at: str = Form(...),
    user: Optional[Dict[str, object]] = Depends(current_user),
) -> RedirectResponse:
    if not user:
        return RedirectResponse("/login?error=Login%20required", status_code=status.HTTP_303_SEE_OTHER)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    try:
        update_login_event(event_id, username, logged_in_at)
    except HTTPException as exc:
        return RedirectResponse(f"/admin/editor?error={quote(str(exc.detail))}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/admin/editor?success=Login%20event%20updated", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/editor/login/delete")
def admin_delete_login_event(
    event_id: int = Form(...),
    user: Optional[Dict[str, object]] = Depends(current_user),
) -> RedirectResponse:
    if not user:
        return RedirectResponse("/login?error=Login%20required", status_code=status.HTTP_303_SEE_OTHER)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    try:
        delete_login_event(event_id)
    except HTTPException as exc:
        return RedirectResponse(f"/admin/editor?error={quote(str(exc.detail))}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/admin/editor?success=Login%20event%20deleted", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/health")
def health() -> Dict[str, str]:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        return {"status": "ok", "db": "ok"}
    except Exception:  # noqa: BLE001
        return {"status": "degraded", "db": "error"}


# For local development: run via run.cmd or uvicorn main:app --reload --app-dir webapp
