from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_HASH_NAME = "pbkdf2_sha256"
_HASH_ITERATIONS = 600_000
_SALT_BYTES = 16
_SESSION_TOKEN_BYTES = 32
_SCHEMA_VERSION = 3
_MAX_FAILED_LOGIN_ATTEMPTS = 5
_ACCOUNT_LOCK_MINUTES = 15


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    created_at: str
    last_login_at: str | None = None
    role: str = "user"
    is_active: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
            "role": self.role,
            "is_admin": self.is_admin,
            "is_active": self.is_active,
        }


@dataclass(frozen=True)
class AuthSession:
    token: str
    expires_at: str


class UserExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AccountLockedError(Exception):
    pass


class AuthStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._initialized = False

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._raw_connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL,
                        username_normalized TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'user',
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        last_login_at TEXT
                    );

                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token_hash TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        last_seen_at TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
                    CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

                    CREATE TABLE IF NOT EXISTS password_reset_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        username TEXT NOT NULL,
                        username_normalized TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        requested_ip TEXT NOT NULL DEFAULT '',
                        user_agent TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        resolved_at TEXT,
                        resolved_by_user_id INTEGER,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                        FOREIGN KEY (resolved_by_user_id) REFERENCES users(id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_password_reset_status
                        ON password_reset_requests(status);
                    CREATE INDEX IF NOT EXISTS idx_password_reset_username
                        ON password_reset_requests(username_normalized);
                    CREATE INDEX IF NOT EXISTS idx_password_reset_user_id
                        ON password_reset_requests(user_id);
                    CREATE INDEX IF NOT EXISTS idx_password_reset_created_at
                        ON password_reset_requests(created_at);

                    CREATE TABLE IF NOT EXISTS usage_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        endpoint_path TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        image_count INTEGER NOT NULL DEFAULT 0,
                        saved_bytes INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_usage_events_user_id ON usage_events(user_id);
                    CREATE INDEX IF NOT EXISTS idx_usage_events_created_at ON usage_events(created_at);

                    CREATE TABLE IF NOT EXISTS result_feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        rating TEXT NOT NULL,
                        reason TEXT NOT NULL DEFAULT '',
                        prompt TEXT NOT NULL DEFAULT '',
                        mode TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        saved_image_path TEXT NOT NULL DEFAULT '',
                        saved_image_url TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_result_feedback_user_id ON result_feedback(user_id);
                    CREATE INDEX IF NOT EXISTS idx_result_feedback_rating ON result_feedback(rating);
                    CREATE INDEX IF NOT EXISTS idx_result_feedback_created_at ON result_feedback(created_at);

                    CREATE TABLE IF NOT EXISTS bug_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        title TEXT NOT NULL DEFAULT '',
                        description TEXT NOT NULL,
                        contact TEXT NOT NULL DEFAULT '',
                        page_url TEXT NOT NULL DEFAULT '',
                        user_agent TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'open',
                        notification_status TEXT NOT NULL DEFAULT 'not_configured',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_bug_reports_user_id ON bug_reports(user_id);
                    CREATE INDEX IF NOT EXISTS idx_bug_reports_created_at ON bug_reports(created_at);
                    CREATE INDEX IF NOT EXISTS idx_bug_reports_status ON bug_reports(status);

                    CREATE TABLE IF NOT EXISTS shared_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender_user_id INTEGER NOT NULL,
                        recipient_user_id INTEGER NOT NULL,
                        prompt TEXT NOT NULL DEFAULT '',
                        mode TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        rating TEXT NOT NULL DEFAULT '',
                        saved_image_path TEXT NOT NULL DEFAULT '',
                        saved_image_url TEXT NOT NULL DEFAULT '',
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        read_at TEXT,
                        FOREIGN KEY (sender_user_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (recipient_user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_shared_results_sender ON shared_results(sender_user_id);
                    CREATE INDEX IF NOT EXISTS idx_shared_results_recipient ON shared_results(recipient_user_id);
                    CREATE INDEX IF NOT EXISTS idx_shared_results_created_at ON shared_results(created_at);

                    CREATE TABLE IF NOT EXISTS user_preferences (
                        user_id INTEGER PRIMARY KEY,
                        default_model TEXT NOT NULL DEFAULT '',
                        default_responses_model TEXT NOT NULL DEFAULT '',
                        default_size TEXT NOT NULL DEFAULT '',
                        default_quality TEXT NOT NULL DEFAULT '',
                        default_output_format TEXT NOT NULL DEFAULT '',
                        default_image_transport TEXT NOT NULL DEFAULT '',
                        logo_overlay_enabled INTEGER NOT NULL DEFAULT 1,
                        auto_copyright_check_enabled INTEGER NOT NULL DEFAULT 1,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS generation_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id TEXT NOT NULL DEFAULT '',
                        user_id INTEGER,
                        username TEXT NOT NULL DEFAULT '',
                        endpoint_path TEXT NOT NULL,
                        mode TEXT NOT NULL DEFAULT '',
                        transport TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'started',
                        prompt TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        size TEXT NOT NULL DEFAULT '',
                        sample_count INTEGER NOT NULL DEFAULT 1,
                        logo_requested INTEGER NOT NULL DEFAULT 0,
                        image_count INTEGER NOT NULL DEFAULT 0,
                        saved_bytes INTEGER NOT NULL DEFAULT 0,
                        error_code TEXT NOT NULL DEFAULT '',
                        error_message TEXT NOT NULL DEFAULT '',
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        elapsed_ms REAL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_generation_jobs_user_id ON generation_jobs(user_id);
                    CREATE INDEX IF NOT EXISTS idx_generation_jobs_request_id ON generation_jobs(request_id);
                    CREATE INDEX IF NOT EXISTS idx_generation_jobs_started_at ON generation_jobs(started_at);
                    CREATE INDEX IF NOT EXISTS idx_generation_jobs_status ON generation_jobs(status);

                    CREATE TABLE IF NOT EXISTS generated_images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id INTEGER NOT NULL,
                        user_id INTEGER,
                        candidate_index INTEGER NOT NULL DEFAULT 0,
                        mode TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        prompt TEXT NOT NULL DEFAULT '',
                        saved_image_path TEXT NOT NULL DEFAULT '',
                        saved_image_url TEXT NOT NULL DEFAULT '',
                        saved_image_name TEXT NOT NULL DEFAULT '',
                        saved_metadata_path TEXT NOT NULL DEFAULT '',
                        saved_metadata_url TEXT NOT NULL DEFAULT '',
                        saved_image_mime TEXT NOT NULL DEFAULT '',
                        saved_image_width INTEGER,
                        saved_image_height INTEGER,
                        saved_image_bytes INTEGER NOT NULL DEFAULT 0,
                        logo_requested INTEGER NOT NULL DEFAULT 0,
                        logo_overlay_applied INTEGER NOT NULL DEFAULT 0,
                        first_served_at TEXT,
                        last_served_at TEXT,
                        served_count INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (job_id) REFERENCES generation_jobs(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_generated_images_job_id ON generated_images(job_id);
                    CREATE INDEX IF NOT EXISTS idx_generated_images_user_id ON generated_images(user_id);
                    CREATE INDEX IF NOT EXISTS idx_generated_images_url ON generated_images(saved_image_url);
                    CREATE INDEX IF NOT EXISTS idx_generated_images_path ON generated_images(saved_image_path);

                    CREATE TABLE IF NOT EXISTS image_delivery_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        generated_image_id INTEGER,
                        user_id INTEGER,
                        saved_image_url TEXT NOT NULL DEFAULT '',
                        relative_path TEXT NOT NULL DEFAULT '',
                        status_code INTEGER NOT NULL DEFAULT 200,
                        client_host TEXT NOT NULL DEFAULT '',
                        user_agent TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (generated_image_id) REFERENCES generated_images(id) ON DELETE SET NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_image_delivery_image_id ON image_delivery_events(generated_image_id);
                    CREATE INDEX IF NOT EXISTS idx_image_delivery_user_id ON image_delivery_events(user_id);
                    CREATE INDEX IF NOT EXISTS idx_image_delivery_created_at ON image_delivery_events(created_at);
                    """
                )
                self._run_schema_migrations(conn)
            self._initialized = True

    def create_user(self, username: str, password: str, *, role: str = "user", is_active: bool = True) -> AuthUser:
        now = _now_text()
        normalized = normalize_username(username)
        normalized_role = normalize_role(role)
        with self._lock, self._connect() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        username,
                        username_normalized,
                        password_hash,
                        role,
                        is_active,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        username.strip(),
                        normalized,
                        hash_password(password),
                        normalized_role,
                        1 if is_active else 0,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise UserExistsError(username) from exc
            user_id = _require_lastrowid(cursor)
            return AuthUser(
                id=user_id,
                username=username.strip(),
                created_at=now,
                role=normalized_role,
                is_active=is_active,
            )

    def ensure_admin_user(self, username: str, password: str) -> AuthUser:
        if not password:
            raise ValueError("管理员密码不能为空")
        now = _now_text()
        normalized = normalize_username(username)
        clean_username = username.strip()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, created_at, last_login_at
                FROM users
                WHERE username_normalized = ?
                """,
                (normalized,),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        username,
                        username_normalized,
                        password_hash,
                        role,
                        is_active,
                        created_at
                    )
                    VALUES (?, ?, ?, 'admin', 1, ?)
                    """,
                    (clean_username, normalized, hash_password(password), now),
                )
                return AuthUser(
                    id=_require_lastrowid(cursor),
                    username=clean_username,
                    created_at=now,
                    role="admin",
                    is_active=True,
                )
            conn.execute(
                """
                UPDATE users
                SET username = ?, password_hash = ?, role = 'admin', is_active = 1
                WHERE id = ?
                """,
                (clean_username, hash_password(password), row["id"]),
            )
            return AuthUser(
                id=int(row["id"]),
                username=clean_username,
                created_at=str(row["created_at"]),
                last_login_at=row["last_login_at"],
                role="admin",
                is_active=True,
            )

    def authenticate(self, username: str, password: str) -> AuthUser:
        normalized = normalize_username(username)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    username,
                    password_hash,
                    role,
                    is_active,
                    created_at,
                    last_login_at,
                    failed_login_count,
                    locked_until
                FROM users
                WHERE username_normalized = ?
                """,
                (normalized,),
            ).fetchone()
            if row is None or not bool(row["is_active"]):
                raise InvalidCredentialsError(username)
            now_dt = _now()
            locked_until = _parse_datetime_text(row["locked_until"])
            if locked_until is not None and locked_until > now_dt:
                raise AccountLockedError(username)
            if not verify_password(password, str(row["password_hash"])):
                failed_count = int(row["failed_login_count"] or 0) + 1
                lock_until_text = ""
                if failed_count >= _MAX_FAILED_LOGIN_ATTEMPTS:
                    lock_until_text = _datetime_text(now_dt + timedelta(minutes=_ACCOUNT_LOCK_MINUTES))
                conn.execute(
                    """
                    UPDATE users
                    SET failed_login_count = ?, locked_until = ?
                    WHERE id = ?
                    """,
                    (failed_count, lock_until_text or None, row["id"]),
                )
                conn.commit()
                raise InvalidCredentialsError(username)
            now = _now_text()
            conn.execute(
                """
                UPDATE users
                SET last_login_at = ?, failed_login_count = 0, locked_until = NULL
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            return AuthUser(
                id=int(row["id"]),
                username=str(row["username"]),
                created_at=str(row["created_at"]),
                last_login_at=now,
                role=str(row["role"]),
                is_active=bool(row["is_active"]),
            )

    def request_password_reset(
        self,
        username: str,
        *,
        client_host: str = "",
        user_agent: str = "",
    ) -> dict[str, Any]:
        normalized = normalize_username(username)
        clean_username = username.strip()
        now = _now_text()
        with self._lock, self._connect() as conn:
            user_row = conn.execute(
                """
                SELECT id, username
                FROM users
                WHERE username_normalized = ?
                """,
                (normalized,),
            ).fetchone()
            user_id = int(user_row["id"]) if user_row is not None else None
            display_username = str(user_row["username"] or clean_username) if user_row is not None else clean_username
            existing = conn.execute(
                """
                SELECT id
                FROM password_reset_requests
                WHERE username_normalized = ? AND status = 'pending'
                ORDER BY id DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if existing is not None:
                request_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE password_reset_requests
                    SET
                        user_id = ?,
                        username = ?,
                        requested_ip = ?,
                        user_agent = ?,
                        created_at = ?
                    WHERE id = ?
                    """,
                    (
                        user_id,
                        display_username[:64],
                        client_host.strip()[:128],
                        user_agent.strip()[:512],
                        now,
                        request_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO password_reset_requests (
                        user_id,
                        username,
                        username_normalized,
                        requested_ip,
                        user_agent,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        display_username[:64],
                        normalized,
                        client_host.strip()[:128],
                        user_agent.strip()[:512],
                        now,
                    ),
                )
                request_id = _require_lastrowid(cursor)
        return {
            "id": request_id,
            "user_id": user_id,
            "username": display_username[:64],
            "username_normalized": normalized,
            "status": "pending",
            "matched_user": user_id is not None,
            "requested_ip": client_host.strip()[:128],
            "user_agent": user_agent.strip()[:512],
            "created_at": now,
        }

    def list_password_reset_requests(self, *, status: str = "pending", limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        clean_status = status.strip().lower()
        where_clause = ""
        params: tuple[Any, ...]
        if clean_status and clean_status != "all":
            where_clause = "WHERE r.status = ?"
            params = (clean_status, bounded_limit)
        else:
            params = (bounded_limit,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    r.id,
                    r.user_id,
                    r.username,
                    r.username_normalized,
                    r.status,
                    r.requested_ip,
                    r.user_agent,
                    r.created_at,
                    r.resolved_at,
                    r.resolved_by_user_id,
                    u.username AS matched_username,
                    resolver.username AS resolved_by_username
                FROM password_reset_requests r
                LEFT JOIN users u ON u.id = r.user_id
                LEFT JOIN users resolver ON resolver.id = r.resolved_by_user_id
                {where_clause}
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_password_reset_request_row_to_dict(row) for row in rows]

    def reset_user_password(self, *, user_id: int, password: str, admin_user_id: int) -> AuthUser | None:
        now = _now_text()
        new_hash = hash_password(password)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, role, is_active, created_at, last_login_at, username_normalized
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE users
                SET
                    password_hash = ?,
                    password_changed_at = ?,
                    failed_login_count = 0,
                    locked_until = NULL
                WHERE id = ?
                """,
                (new_hash, now, user_id),
            )
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute(
                """
                UPDATE password_reset_requests
                SET
                    status = 'resolved',
                    resolved_at = ?,
                    resolved_by_user_id = ?
                WHERE status = 'pending'
                  AND (user_id = ? OR username_normalized = ?)
                """,
                (now, admin_user_id, user_id, str(row["username_normalized"])),
            )
        return AuthUser(
            id=int(row["id"]),
            username=str(row["username"]),
            created_at=str(row["created_at"]),
            last_login_at=row["last_login_at"],
            role=str(row["role"]),
            is_active=bool(row["is_active"]),
        )

    def change_user_password(
        self,
        *,
        user_id: int,
        current_password: str,
        new_password: str,
        current_session_token: str = "",
    ) -> AuthUser:
        now = _now_text()
        token_hash = hash_session_token(current_session_token) if current_session_token else ""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, role, is_active, created_at, last_login_at, password_hash
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None or not bool(row["is_active"]):
                raise InvalidCredentialsError("inactive")
            if not verify_password(current_password, str(row["password_hash"])):
                raise InvalidCredentialsError("current_password")
            conn.execute(
                """
                UPDATE users
                SET
                    password_hash = ?,
                    password_changed_at = ?,
                    failed_login_count = 0,
                    locked_until = NULL
                WHERE id = ?
                """,
                (hash_password(new_password), now, user_id),
            )
            if token_hash:
                conn.execute(
                    """
                    DELETE FROM sessions
                    WHERE user_id = ? AND token_hash != ?
                    """,
                    (user_id, token_hash),
                )
            else:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return AuthUser(
            id=int(row["id"]),
            username=str(row["username"]),
            created_at=str(row["created_at"]),
            last_login_at=row["last_login_at"],
            role=str(row["role"]),
            is_active=bool(row["is_active"]),
        )

    def create_session(self, user_id: int, *, days: int) -> AuthSession:
        token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
        created_at = _now()
        expires_at = created_at + timedelta(days=days)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (user_id, token_hash, created_at, expires_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    hash_session_token(token),
                    _datetime_text(created_at),
                    _datetime_text(expires_at),
                    _datetime_text(created_at),
                ),
            )
        return AuthSession(token=token, expires_at=_datetime_text(expires_at))

    def user_for_session(self, token: str) -> AuthUser | None:
        if not token:
            return None
        now = _now_text()
        token_hash = hash_session_token(token)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.role, u.is_active, u.created_at, u.last_login_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1
                """,
                (token_hash, now),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (now, token_hash))
            conn.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now, row["id"]))
            return AuthUser(
                id=int(row["id"]),
                username=str(row["username"]),
                created_at=str(row["created_at"]),
                last_login_at=row["last_login_at"],
                role=str(row["role"]),
                is_active=bool(row["is_active"]),
            )

    def create_generation_job(
        self,
        *,
        request_id: str,
        user_id: int | None,
        username: str = "",
        endpoint_path: str,
        mode: str = "",
        transport: str = "",
        prompt: str = "",
        model: str = "",
        size: str = "",
        sample_count: int = 1,
        logo_requested: bool = False,
    ) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO generation_jobs (
                    request_id,
                    user_id,
                    username,
                    endpoint_path,
                    mode,
                    transport,
                    prompt,
                    model,
                    size,
                    sample_count,
                    logo_requested,
                    started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id.strip()[:128],
                    user_id,
                    username.strip()[:128],
                    endpoint_path.strip()[:128],
                    mode.strip()[:64],
                    transport.strip()[:64],
                    prompt.strip()[:32_000],
                    model.strip()[:128],
                    size.strip()[:64],
                    max(1, int(sample_count or 1)),
                    1 if logo_requested else 0,
                    _now_text(),
                ),
            )
            return _require_lastrowid(cursor)

    def complete_generation_job(
        self,
        *,
        job_id: int,
        result: dict[str, Any],
        elapsed_ms: float,
        status: str = "succeeded",
        error_code: str = "",
        error_message: str = "",
    ) -> list[dict[str, Any]]:
        images = _result_images_for_db(result)
        image_count = len(images)
        saved_bytes = sum(max(0, int(image.get("saved_image_bytes") or 0)) for image in images)
        now = _now_text()
        created: list[dict[str, Any]] = []
        with self._lock, self._connect() as conn:
            job_row = conn.execute("SELECT user_id FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
            job_user_id = int(job_row["user_id"]) if job_row is not None and job_row["user_id"] is not None else None
            conn.execute(
                """
                UPDATE generation_jobs
                SET
                    status = ?,
                    image_count = ?,
                    saved_bytes = ?,
                    error_code = ?,
                    error_message = ?,
                    completed_at = ?,
                    elapsed_ms = ?
                WHERE id = ?
                """,
                (
                    status.strip()[:64] or "succeeded",
                    image_count,
                    saved_bytes,
                    error_code.strip()[:128],
                    error_message.strip()[:1000],
                    now,
                    float(elapsed_ms),
                    job_id,
                ),
            )
            for index, image in enumerate(images):
                cursor = conn.execute(
                    """
                    INSERT INTO generated_images (
                        job_id,
                        user_id,
                        candidate_index,
                        mode,
                        model,
                        prompt,
                        saved_image_path,
                        saved_image_url,
                        saved_image_name,
                        saved_metadata_path,
                        saved_metadata_url,
                        saved_image_mime,
                        saved_image_width,
                        saved_image_height,
                        saved_image_bytes,
                        logo_requested,
                        logo_overlay_applied,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        job_user_id,
                        int(image.get("candidate_index", index) or 0),
                        str(result.get("mode") or image.get("mode") or "")[:64],
                        str(result.get("model") or image.get("model") or "")[:128],
                        str(result.get("prompt") or image.get("prompt") or "")[:32_000],
                        str(image.get("saved_image_path") or "")[:1024],
                        str(image.get("saved_image_url") or "")[:1024],
                        str(image.get("saved_image_name") or "")[:255],
                        str(image.get("saved_metadata_path") or "")[:1024],
                        str(image.get("saved_metadata_url") or "")[:1024],
                        str(image.get("saved_image_mime") or "")[:128],
                        _optional_int(image.get("saved_image_width")),
                        _optional_int(image.get("saved_image_height")),
                        max(0, int(image.get("saved_image_bytes") or 0)),
                        1 if result.get("logo_requested") else 0,
                        1 if image.get("logo_overlay_applied") else 0,
                        now,
                    ),
                )
                created.append({"id": _require_lastrowid(cursor), "candidate_index": index})
        return created

    def fail_generation_job(
        self,
        *,
        job_id: int,
        elapsed_ms: float,
        error_code: str = "",
        error_message: str = "",
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE generation_jobs
                SET status = 'failed', error_code = ?, error_message = ?, completed_at = ?, elapsed_ms = ?
                WHERE id = ?
                """,
                (error_code.strip()[:128], error_message.strip()[:1000], _now_text(), float(elapsed_ms), job_id),
            )

    def generated_image_for_user(self, *, generated_image_id: int, user_id: int) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    job_id,
                    user_id,
                    candidate_index,
                    mode,
                    model,
                    prompt,
                    saved_image_path,
                    saved_image_url,
                    saved_image_name,
                    saved_metadata_path,
                    saved_metadata_url,
                    saved_image_mime,
                    saved_image_width,
                    saved_image_height,
                    saved_image_bytes,
                    logo_requested,
                    logo_overlay_applied,
                    created_at
                FROM generated_images
                WHERE id = ? AND user_id = ?
                """,
                (generated_image_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return _generated_image_row_to_dict(row)

    def replace_generated_image_asset(
        self,
        *,
        generated_image_id: int,
        user_id: int,
        image: dict[str, Any],
        logo_overlay_applied: bool = False,
    ) -> dict[str, Any]:
        now = _now_text()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, user_id
                FROM generated_images
                WHERE id = ? AND user_id = ?
                """,
                (generated_image_id, user_id),
            ).fetchone()
            if row is None:
                raise PermissionError("无权更新这张图片")
            conn.execute(
                """
                UPDATE generated_images
                SET
                    saved_image_path = ?,
                    saved_image_url = ?,
                    saved_image_name = ?,
                    saved_metadata_path = ?,
                    saved_metadata_url = ?,
                    saved_image_mime = ?,
                    saved_image_width = ?,
                    saved_image_height = ?,
                    saved_image_bytes = ?,
                    logo_overlay_applied = ?
                WHERE id = ?
                """,
                (
                    str(image.get("saved_image_path") or "")[:1024],
                    str(image.get("saved_image_url") or "")[:1024],
                    str(image.get("saved_image_name") or "")[:255],
                    str(image.get("saved_metadata_path") or "")[:1024],
                    str(image.get("saved_metadata_url") or "")[:1024],
                    str(image.get("saved_image_mime") or "")[:128],
                    _optional_int(image.get("saved_image_width")),
                    _optional_int(image.get("saved_image_height")),
                    max(0, int(image.get("saved_image_bytes") or 0)),
                    1 if logo_overlay_applied else 0,
                    generated_image_id,
                ),
            )
            updated = conn.execute(
                """
                SELECT
                    id,
                    job_id,
                    user_id,
                    candidate_index,
                    mode,
                    model,
                    prompt,
                    saved_image_path,
                    saved_image_url,
                    saved_image_name,
                    saved_metadata_path,
                    saved_metadata_url,
                    saved_image_mime,
                    saved_image_width,
                    saved_image_height,
                    saved_image_bytes,
                    logo_requested,
                    logo_overlay_applied,
                    created_at
                FROM generated_images
                WHERE id = ?
                """,
                (generated_image_id,),
            ).fetchone()
            conn.execute(
                """
                UPDATE generation_jobs
                SET completed_at = COALESCE(completed_at, ?)
                WHERE id = ?
                """,
                (now, int(updated["job_id"]) if updated is not None else 0),
            )
        if updated is None:
            raise RuntimeError("更新后的图片记录不存在")
        return _generated_image_row_to_dict(updated)

    def record_image_delivery(
        self,
        *,
        relative_path: str,
        user_id: int | None = None,
        status_code: int = 200,
        client_host: str = "",
        user_agent: str = "",
    ) -> None:
        cleaned_path = relative_path.strip().lstrip("/")
        saved_url = f"files/{cleaned_path}"
        now = _now_text()
        with self._lock, self._connect() as conn:
            image = conn.execute(
                """
                SELECT id
                FROM generated_images
                WHERE saved_image_url IN (?, ?) OR saved_image_path IN (?, ?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (saved_url, f"/{saved_url}", cleaned_path, f"/{cleaned_path}"),
            ).fetchone()
            generated_image_id = int(image["id"]) if image is not None else None
            conn.execute(
                """
                INSERT INTO image_delivery_events (
                    generated_image_id,
                    user_id,
                    saved_image_url,
                    relative_path,
                    status_code,
                    client_host,
                    user_agent,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generated_image_id,
                    user_id,
                    saved_url,
                    cleaned_path,
                    int(status_code),
                    client_host.strip()[:128],
                    user_agent.strip()[:512],
                    now,
                ),
            )
            if generated_image_id is not None and 200 <= int(status_code) < 400:
                conn.execute(
                    """
                    UPDATE generated_images
                    SET
                        served_count = served_count + 1,
                        first_served_at = COALESCE(first_served_at, ?),
                        last_served_at = ?
                    WHERE id = ?
                    """,
                    (now, now, generated_image_id),
                )

    def get_user_preferences(self, *, user_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    default_model,
                    default_responses_model,
                    default_size,
                    default_quality,
                    default_output_format,
                    default_image_transport,
                    logo_overlay_enabled,
                    auto_copyright_check_enabled,
                    updated_at
                FROM user_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return _default_user_preferences(user_id)
        return _user_preferences_from_row(user_id, row)

    def update_user_preferences(
        self,
        *,
        user_id: int,
        default_model: str = "",
        default_responses_model: str = "",
        default_size: str = "",
        default_quality: str = "",
        default_output_format: str = "",
        default_image_transport: str = "",
        logo_overlay_enabled: bool = True,
        auto_copyright_check_enabled: bool = True,
    ) -> dict[str, Any]:
        now = _now_text()
        values = {
            "user_id": user_id,
            "default_model": default_model.strip()[:128],
            "default_responses_model": default_responses_model.strip()[:128],
            "default_size": default_size.strip()[:64],
            "default_quality": default_quality.strip()[:64],
            "default_output_format": default_output_format.strip()[:64],
            "default_image_transport": default_image_transport.strip()[:64],
            "logo_overlay_enabled": 1 if logo_overlay_enabled else 0,
            "auto_copyright_check_enabled": 1 if auto_copyright_check_enabled else 0,
            "updated_at": now,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (
                    user_id,
                    default_model,
                    default_responses_model,
                    default_size,
                    default_quality,
                    default_output_format,
                    default_image_transport,
                    logo_overlay_enabled,
                    auto_copyright_check_enabled,
                    updated_at
                )
                VALUES (
                    :user_id,
                    :default_model,
                    :default_responses_model,
                    :default_size,
                    :default_quality,
                    :default_output_format,
                    :default_image_transport,
                    :logo_overlay_enabled,
                    :auto_copyright_check_enabled,
                    :updated_at
                )
                ON CONFLICT(user_id) DO UPDATE SET
                    default_model = excluded.default_model,
                    default_responses_model = excluded.default_responses_model,
                    default_size = excluded.default_size,
                    default_quality = excluded.default_quality,
                    default_output_format = excluded.default_output_format,
                    default_image_transport = excluded.default_image_transport,
                    logo_overlay_enabled = excluded.logo_overlay_enabled,
                    auto_copyright_check_enabled = excluded.auto_copyright_check_enabled,
                    updated_at = excluded.updated_at
                """,
                values,
            )
        return {
            "user_id": user_id,
            "default_model": values["default_model"],
            "default_responses_model": values["default_responses_model"],
            "default_size": values["default_size"],
            "default_quality": values["default_quality"],
            "default_output_format": values["default_output_format"],
            "default_image_transport": values["default_image_transport"],
            "logo_overlay_enabled": bool(logo_overlay_enabled),
            "auto_copyright_check_enabled": bool(auto_copyright_check_enabled),
            "updated_at": now,
        }

    def record_feedback(
        self,
        *,
        user_id: int,
        rating: str,
        reason: str = "",
        prompt: str = "",
        mode: str = "",
        model: str = "",
        saved_image_path: str = "",
        saved_image_url: str = "",
        generated_image_id: int | None = None,
    ) -> dict[str, Any]:
        normalized_rating = normalize_feedback_rating(rating)
        now = _now_text()
        clean_reason = reason.strip()[:1000]
        clean_prompt = prompt.strip()[:32_000]
        clean_mode = mode.strip()[:64]
        clean_model = model.strip()[:128]
        clean_path = saved_image_path.strip()[:1024]
        clean_url = saved_image_url.strip()[:1024]
        with self._lock, self._connect() as conn:
            if generated_image_id is not None:
                owner = conn.execute(
                    "SELECT id FROM generated_images WHERE id = ? AND user_id = ?",
                    (generated_image_id, user_id),
                ).fetchone()
                if owner is None:
                    raise PermissionError("无权反馈这张图片")
            cursor = conn.execute(
                """
                INSERT INTO result_feedback (
                    user_id,
                    generated_image_id,
                    rating,
                    reason,
                    prompt,
                    mode,
                    model,
                    saved_image_path,
                    saved_image_url,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    generated_image_id,
                    normalized_rating,
                    clean_reason,
                    clean_prompt,
                    clean_mode,
                    clean_model,
                    clean_path,
                    clean_url,
                    now,
                ),
            )
            feedback_id = _require_lastrowid(cursor)
        return {
            "id": feedback_id,
            "user_id": user_id,
            "generated_image_id": generated_image_id,
            "rating": normalized_rating,
            "reason": clean_reason,
            "prompt": clean_prompt,
            "mode": clean_mode,
            "model": clean_model,
            "saved_image_path": clean_path,
            "saved_image_url": clean_url,
            "created_at": now,
        }

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_session_token(token),))

    def record_usage(
        self,
        *,
        user_id: int,
        endpoint_path: str,
        mode: str,
        image_count: int,
        saved_bytes: int,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (user_id, endpoint_path, mode, image_count, saved_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, endpoint_path, mode, max(0, image_count), max(0, saved_bytes), _now_text()),
            )

    def usage_summary(self, user_id: int | None = None) -> list[dict[str, Any]]:
        where_clause = ""
        params: tuple[Any, ...] = ()
        if user_id is not None:
            where_clause = "WHERE u.id = ?"
            params = (user_id,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                WITH usage_totals AS (
                    SELECT
                        user_id,
                        COUNT(id) AS request_count,
                        COALESCE(SUM(image_count), 0) AS image_count,
                        COALESCE(SUM(saved_bytes), 0) AS saved_bytes,
                        MAX(created_at) AS last_used_at
                    FROM usage_events
                    GROUP BY user_id
                ),
                image_totals AS (
                    SELECT
                        user_id,
                        COUNT(id) AS generated_image_count,
                        COALESCE(SUM(CASE WHEN served_count > 0 THEN 1 ELSE 0 END), 0) AS delivered_image_count
                    FROM generated_images
                    GROUP BY user_id
                )
                SELECT
                    u.id,
                    u.username,
                    u.role,
                    u.is_active,
                    u.created_at,
                    u.last_login_at,
                    COALESCE(ut.request_count, 0) AS request_count,
                    COALESCE(ut.image_count, 0) AS image_count,
                    COALESCE(ut.saved_bytes, 0) AS saved_bytes,
                    ut.last_used_at,
                    COALESCE(it.generated_image_count, 0) AS generated_image_count,
                    COALESCE(it.delivered_image_count, 0) AS delivered_image_count
                FROM users u
                LEFT JOIN usage_totals ut ON ut.user_id = u.id
                LEFT JOIN image_totals it ON it.user_id = u.id
                {where_clause}
                ORDER BY image_count DESC, request_count DESC, u.username COLLATE NOCASE ASC
                """,
                params,
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "role": str(row["role"]),
                "is_admin": str(row["role"]) == "admin",
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
                "last_login_at": row["last_login_at"],
                "request_count": int(row["request_count"] or 0),
                "image_count": int(row["image_count"] or 0),
                "saved_bytes": int(row["saved_bytes"] or 0),
                "last_used_at": row["last_used_at"],
                "generated_image_count": int(row["generated_image_count"] or 0),
                "delivered_image_count": int(row["delivered_image_count"] or 0),
            }
            for row in rows
        ]

    def list_active_users(self, *, exclude_user_id: int | None = None) -> list[dict[str, Any]]:
        where_clause = "WHERE is_active = 1"
        params: tuple[Any, ...] = ()
        if exclude_user_id is not None:
            where_clause = "WHERE is_active = 1 AND id != ?"
            params = (exclude_user_id,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, username, role, is_active, created_at, last_login_at
                FROM users
                {where_clause}
                ORDER BY username COLLATE NOCASE ASC
                """,
                params,
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "role": str(row["role"]),
                "is_admin": str(row["role"]) == "admin",
                "is_active": bool(row["is_active"]),
                "created_at": str(row["created_at"]),
                "last_login_at": row["last_login_at"],
            }
            for row in rows
        ]

    def feedback_summary(self, *, limit: int = 50) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 200))
        with self._lock, self._connect() as conn:
            rating_rows = conn.execute(
                """
                SELECT rating, COUNT(*) AS count
                FROM result_feedback
                GROUP BY rating
                """
            ).fetchall()
            recent_rows = conn.execute(
                """
                SELECT
                    f.id,
                    f.user_id,
                    f.generated_image_id,
                    u.username,
                    f.rating,
                    f.reason,
                    f.prompt,
                    f.mode,
                    f.model,
                    f.saved_image_path,
                    f.saved_image_url,
                    f.created_at
                FROM result_feedback f
                JOIN users u ON u.id = f.user_id
                ORDER BY f.created_at DESC, f.id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        totals = {"good": 0, "ok": 0, "bad": 0}
        for row in rating_rows:
            rating = str(row["rating"])
            if rating in totals:
                totals[rating] = int(row["count"] or 0)
        total_count = sum(totals.values())
        satisfaction_rate = round(totals["good"] / total_count, 4) if total_count else 0.0
        return {
            "totals": totals,
            "total_count": total_count,
            "satisfaction_rate": satisfaction_rate,
            "recent": [
                {
                    "id": int(row["id"]),
                    "user_id": int(row["user_id"]),
                    "generated_image_id": int(row["generated_image_id"]) if row["generated_image_id"] else None,
                    "username": str(row["username"]),
                    "rating": str(row["rating"]),
                    "reason": str(row["reason"] or ""),
                    "prompt": str(row["prompt"] or ""),
                    "mode": str(row["mode"] or ""),
                    "model": str(row["model"] or ""),
                    "saved_image_path": str(row["saved_image_path"] or ""),
                    "saved_image_url": str(row["saved_image_url"] or ""),
                    "created_at": str(row["created_at"]),
                }
                for row in recent_rows
            ],
        }

    def record_bug_report(
        self,
        *,
        user_id: int,
        title: str,
        description: str,
        contact: str = "",
        page_url: str = "",
        user_agent: str = "",
    ) -> dict[str, Any]:
        clean_description = description.strip()[:4000]
        if not clean_description:
            raise ValueError("问题描述不能为空")
        clean_title = title.strip()[:160] or clean_description[:80]
        clean_contact = contact.strip()[:256]
        clean_page_url = page_url.strip()[:1024]
        clean_user_agent = user_agent.strip()[:512]
        now = _now_text()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO bug_reports (
                    user_id,
                    title,
                    description,
                    contact,
                    page_url,
                    user_agent,
                    status,
                    notification_status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'open', 'not_configured', ?)
                """,
                (
                    user_id,
                    clean_title,
                    clean_description,
                    clean_contact,
                    clean_page_url,
                    clean_user_agent,
                    now,
                ),
            )
            report_id = _require_lastrowid(cursor)
        return {
            "id": report_id,
            "user_id": user_id,
            "title": clean_title,
            "description": clean_description,
            "contact": clean_contact,
            "page_url": clean_page_url,
            "status": "open",
            "notification_status": "not_configured",
            "created_at": now,
        }

    def update_bug_report_notification_status(self, report_id: int, status: str) -> bool:
        clean_status = status.strip()[:64] or "unknown"
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE bug_reports SET notification_status = ? WHERE id = ?",
                (clean_status, report_id),
            )
            return bool(cursor.rowcount)

    def list_bug_reports(self, *, limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.user_id,
                    u.username,
                    b.title,
                    b.description,
                    b.contact,
                    b.page_url,
                    b.status,
                    b.notification_status,
                    b.created_at
                FROM bug_reports b
                JOIN users u ON u.id = b.user_id
                ORDER BY b.created_at DESC, b.id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "username": str(row["username"]),
                "title": str(row["title"] or ""),
                "description": str(row["description"] or ""),
                "contact": str(row["contact"] or ""),
                "page_url": str(row["page_url"] or ""),
                "status": str(row["status"] or ""),
                "notification_status": str(row["notification_status"] or ""),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def create_result_shares(
        self,
        *,
        sender_user_id: int,
        recipient_ids: list[int],
        prompt: str = "",
        mode: str = "",
        model: str = "",
        rating: str = "",
        saved_image_path: str = "",
        saved_image_url: str = "",
        generated_image_id: int | None = None,
        note: str = "",
    ) -> list[dict[str, Any]]:
        unique_recipient_ids = [user_id for user_id in dict.fromkeys(recipient_ids) if user_id != sender_user_id]
        if not unique_recipient_ids:
            raise ValueError("请选择至少一个分享对象")
        clean_rating = normalize_optional_feedback_rating(rating)
        clean_prompt = prompt.strip()[:32_000]
        clean_mode = mode.strip()[:64]
        clean_model = model.strip()[:128]
        clean_path = saved_image_path.strip()[:1024]
        clean_url = saved_image_url.strip()[:1024]
        clean_note = note.strip()[:1000]
        now = _now_text()
        placeholders = ",".join("?" for _ in unique_recipient_ids)
        with self._lock, self._connect() as conn:
            if generated_image_id is not None:
                image = conn.execute(
                    """
                    SELECT
                        saved_image_path,
                        saved_image_url,
                        prompt,
                        mode,
                        model
                    FROM generated_images
                    WHERE id = ? AND user_id = ?
                    """,
                    (generated_image_id, sender_user_id),
                ).fetchone()
                if image is None:
                    raise PermissionError("无权分享这张图片")
                clean_path = str(image["saved_image_path"] or "")[:1024]
                clean_url = str(image["saved_image_url"] or "")[:1024]
                clean_prompt = str(image["prompt"] or "")[:32_000]
                clean_mode = str(image["mode"] or "")[:64]
                clean_model = str(image["model"] or "")[:128]
            recipient_rows = conn.execute(
                f"""
                SELECT id, username
                FROM users
                WHERE is_active = 1 AND id IN ({placeholders})
                """,
                tuple(unique_recipient_ids),
            ).fetchall()
            recipients = {int(row["id"]): str(row["username"]) for row in recipient_rows}
            missing = [user_id for user_id in unique_recipient_ids if user_id not in recipients]
            if missing:
                raise ValueError("分享对象不存在或已停用")
            created: list[dict[str, Any]] = []
            for recipient_id in unique_recipient_ids:
                cursor = conn.execute(
                    """
                    INSERT INTO shared_results (
                        sender_user_id,
                        recipient_user_id,
                        generated_image_id,
                        prompt,
                        mode,
                        model,
                        rating,
                        saved_image_path,
                        saved_image_url,
                        note,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sender_user_id,
                        recipient_id,
                        generated_image_id,
                        clean_prompt,
                        clean_mode,
                        clean_model,
                        clean_rating,
                        clean_path,
                        clean_url,
                        clean_note,
                        now,
                    ),
                )
                created.append(
                    {
                        "id": _require_lastrowid(cursor),
                        "sender_user_id": sender_user_id,
                        "recipient_user_id": recipient_id,
                        "generated_image_id": generated_image_id,
                        "recipient_username": recipients[recipient_id],
                        "prompt": clean_prompt,
                        "mode": clean_mode,
                        "model": clean_model,
                        "rating": clean_rating,
                        "saved_image_path": clean_path,
                        "saved_image_url": clean_url,
                        "note": clean_note,
                        "created_at": now,
                        "read_at": None,
                    }
                )
        return created

    def list_shared_results_for_user(self, *, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id,
                    s.sender_user_id,
                    sender.username AS sender_username,
                    s.recipient_user_id,
                    recipient.username AS recipient_username,
                    s.generated_image_id,
                    s.prompt,
                    s.mode,
                    s.model,
                    s.rating,
                    s.saved_image_path,
                    s.saved_image_url,
                    s.note,
                    s.created_at,
                    s.read_at
                FROM shared_results s
                JOIN users sender ON sender.id = s.sender_user_id
                JOIN users recipient ON recipient.id = s.recipient_user_id
                WHERE s.recipient_user_id = ?
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ?
                """,
                (user_id, bounded_limit),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "sender_user_id": int(row["sender_user_id"]),
                "sender_username": str(row["sender_username"]),
                "recipient_user_id": int(row["recipient_user_id"]),
                "recipient_username": str(row["recipient_username"]),
                "generated_image_id": int(row["generated_image_id"]) if row["generated_image_id"] else None,
                "prompt": str(row["prompt"] or ""),
                "mode": str(row["mode"] or ""),
                "model": str(row["model"] or ""),
                "rating": str(row["rating"] or ""),
                "saved_image_path": str(row["saved_image_path"] or ""),
                "saved_image_url": str(row["saved_image_url"] or ""),
                "note": str(row["note"] or ""),
                "created_at": str(row["created_at"]),
                "read_at": row["read_at"],
            }
            for row in rows
        ]

    def delete_user(self, user_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return bool(cursor.rowcount)

    def user_count(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
            return int(row["count"] if row is not None else 0)

    def prune_expired_sessions(self) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (_now_text(),))
            return int(cursor.rowcount or 0)

    @staticmethod
    def _run_schema_migrations(conn: sqlite3.Connection) -> None:
        _ensure_columns(conn, "users", {
            "role": "TEXT NOT NULL DEFAULT 'user'",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "display_name": "TEXT NOT NULL DEFAULT ''",
            "real_name": "TEXT NOT NULL DEFAULT ''",
            "wechat": "TEXT NOT NULL DEFAULT ''",
            "phone": "TEXT NOT NULL DEFAULT ''",
            "email": "TEXT NOT NULL DEFAULT ''",
            "team": "TEXT NOT NULL DEFAULT ''",
            "note": "TEXT NOT NULL DEFAULT ''",
            "created_source": "TEXT NOT NULL DEFAULT 'self_register'",
            "last_seen_at": "TEXT",
            "password_changed_at": "TEXT",
            "failed_login_count": "INTEGER NOT NULL DEFAULT 0",
            "locked_until": "TEXT",
            "disabled_reason": "TEXT NOT NULL DEFAULT ''",
        })
        _ensure_columns(conn, "result_feedback", {
            "generated_image_id": "INTEGER",
        })
        _ensure_columns(conn, "shared_results", {
            "generated_image_id": "INTEGER",
        })
        _ensure_columns(conn, "user_preferences", {
            "default_model": "TEXT NOT NULL DEFAULT ''",
            "default_responses_model": "TEXT NOT NULL DEFAULT ''",
            "default_size": "TEXT NOT NULL DEFAULT ''",
            "default_quality": "TEXT NOT NULL DEFAULT ''",
            "default_output_format": "TEXT NOT NULL DEFAULT ''",
            "default_image_transport": "TEXT NOT NULL DEFAULT ''",
            "logo_overlay_enabled": "INTEGER NOT NULL DEFAULT 1",
            "auto_copyright_check_enabled": "INTEGER NOT NULL DEFAULT 1",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        })
        conn.execute("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''")
        conn.execute("UPDATE users SET is_active = 1 WHERE is_active IS NULL")
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (_SCHEMA_VERSION, "password_reset_requests", _now_text()),
        )

    def _connect(self) -> sqlite3.Connection:
        self.initialize()
        return self._raw_connect()

    def _raw_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def normalize_username(username: str) -> str:
    cleaned = username.strip()
    if len(cleaned) < 2 or len(cleaned) > 64:
        raise ValueError("用户名长度必须在 2 到 64 个字符之间")
    if any(char.isspace() for char in cleaned):
        raise ValueError("用户名不能包含空白字符")
    if any(ord(char) < 32 for char in cleaned):
        raise ValueError("用户名包含非法字符")
    return cleaned.casefold()


def normalize_role(role: str) -> str:
    cleaned = role.strip().lower()
    if cleaned not in {"admin", "user"}:
        raise ValueError("未知用户角色")
    return cleaned


def normalize_feedback_rating(rating: str) -> str:
    cleaned = rating.strip().lower()
    if cleaned not in {"good", "ok", "bad"}:
        raise ValueError("未知反馈评分")
    return cleaned


def normalize_optional_feedback_rating(rating: str) -> str:
    cleaned = rating.strip().lower()
    if not cleaned:
        return ""
    return normalize_feedback_rating(cleaned)


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _result_images_for_db(result: dict[str, Any]) -> list[dict[str, Any]]:
    images = result.get("images")
    if isinstance(images, list):
        return [
            image
            for image in images
            if isinstance(image, dict) and (image.get("saved_image_url") or image.get("saved_image_path"))
        ]
    if result.get("saved_image_url") or result.get("saved_image_path"):
        return [result]
    return []


def _generated_image_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "generated_image_id": int(row["id"]),
        "job_id": int(row["job_id"]),
        "user_id": int(row["user_id"]) if row["user_id"] is not None else None,
        "candidate_index": int(row["candidate_index"] or 0),
        "mode": str(row["mode"] or ""),
        "model": str(row["model"] or ""),
        "prompt": str(row["prompt"] or ""),
        "saved_image_path": str(row["saved_image_path"] or ""),
        "saved_image_url": str(row["saved_image_url"] or ""),
        "saved_image_name": str(row["saved_image_name"] or ""),
        "saved_metadata_path": str(row["saved_metadata_path"] or ""),
        "saved_metadata_url": str(row["saved_metadata_url"] or ""),
        "saved_image_mime": str(row["saved_image_mime"] or ""),
        "saved_image_width": _optional_int(row["saved_image_width"]),
        "saved_image_height": _optional_int(row["saved_image_height"]),
        "saved_image_bytes": max(0, int(row["saved_image_bytes"] or 0)),
        "logo_requested": bool(row["logo_requested"]),
        "logo_overlay_applied": bool(row["logo_overlay_applied"]),
        "created_at": str(row["created_at"]),
    }


def _password_reset_request_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    user_id = int(row["user_id"]) if row["user_id"] is not None else None
    resolver_id = int(row["resolved_by_user_id"]) if row["resolved_by_user_id"] is not None else None
    return {
        "id": int(row["id"]),
        "user_id": user_id,
        "username": str(row["username"] or ""),
        "username_normalized": str(row["username_normalized"] or ""),
        "matched_user": user_id is not None,
        "matched_username": str(row["matched_username"] or "") if row["matched_username"] is not None else "",
        "status": str(row["status"] or ""),
        "requested_ip": str(row["requested_ip"] or ""),
        "user_agent": str(row["user_agent"] or ""),
        "created_at": str(row["created_at"]),
        "resolved_at": row["resolved_at"],
        "resolved_by_user_id": resolver_id,
        "resolved_by_username": (
            str(row["resolved_by_username"] or "") if row["resolved_by_username"] is not None else ""
        ),
    }


def _default_user_preferences(user_id: int) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "default_model": "",
        "default_responses_model": "",
        "default_size": "",
        "default_quality": "",
        "default_output_format": "",
        "default_image_transport": "",
        "logo_overlay_enabled": True,
        "auto_copyright_check_enabled": True,
        "updated_at": None,
    }


def _user_preferences_from_row(user_id: int, row: sqlite3.Row) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "default_model": str(row["default_model"] or ""),
        "default_responses_model": str(row["default_responses_model"] or ""),
        "default_size": str(row["default_size"] or ""),
        "default_quality": str(row["default_quality"] or ""),
        "default_output_format": str(row["default_output_format"] or ""),
        "default_image_transport": str(row["default_image_transport"] or ""),
        "logo_overlay_enabled": bool(row["logo_overlay_enabled"]),
        "auto_copyright_check_enabled": bool(row["auto_copyright_check_enabled"]),
        "updated_at": row["updated_at"],
    }


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS)
    return "$".join(
        [
            _HASH_NAME,
            str(_HASH_ITERATIONS),
            salt.hex(),
            digest.hex(),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        name, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
        if name != _HASH_NAME:
            return False
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _now_text() -> str:
    return _datetime_text(_now())


def _datetime_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _parse_datetime_text(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _require_lastrowid(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite insert did not return a row id")
    return int(cursor.lastrowid)
