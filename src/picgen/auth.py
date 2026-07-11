from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import DEFAULT_RESPONSES_MODEL, LEGACY_DEFAULT_RESPONSES_MODEL

_HASH_NAME = "pbkdf2_sha256"
_HASH_ITERATIONS = 600_000
_SALT_BYTES = 16
_SESSION_TOKEN_BYTES = 32
_PASSWORD_RESET_TOKEN_BYTES = 32
_SCHEMA_VERSION = 15
_SHARED_RESULT_OWNERSHIP_SCHEMA_VERSION = 15
_MAX_FAILED_LOGIN_ATTEMPTS = 5
_ACCOUNT_LOCK_MINUTES = 15
_PASSWORD_RESET_REQUEST_THROTTLE_MINUTES = 10
TEAM_CHAT_BOT_ID = "gpt-bot"
TEAM_CHAT_BOT_NAME = "GPT-BOT"
DEFAULT_COMPANY = "6renyou"
DEFAULT_DEPARTMENT = "PD & OPS"
DEFAULT_ORG_UNITS = ((DEFAULT_COMPANY, DEFAULT_DEPARTMENT),)
SYSTEM_USERNAMES_WITHOUT_ORG = {"admin", "minorli"}
_UI_MODES = frozenset({"simple", "professional"})


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    created_at: str
    last_login_at: str | None = None
    role: str = "user"
    is_active: bool = True
    display_name: str = ""
    wechat: str = ""
    phone_country_code: str = "+86"
    phone: str = ""
    email: str = ""
    company: str = DEFAULT_COMPANY
    department: str = DEFAULT_DEPARTMENT
    team: str = ""
    job_title: str = ""
    note: str = ""
    avatar_path: str = ""
    avatar_url: str = ""

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
            "display_name": self.display_name,
            "wechat": self.wechat,
            "phone_country_code": self.phone_country_code,
            "phone": self.phone,
            "email": self.email,
            "company": self.company,
            "department": self.department,
            "team": self.team,
            "job_title": self.job_title,
            "note": self.note,
            "avatar_url": self.avatar_url,
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
                        token_hash TEXT,
                        email TEXT NOT NULL DEFAULT '',
                        email_sent_at TEXT,
                        expires_at TEXT,
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
                        ui_mode TEXT CHECK (ui_mode IS NULL OR ui_mode IN ('simple', 'professional')),
                        default_model TEXT NOT NULL DEFAULT '',
                        default_responses_model TEXT NOT NULL DEFAULT '',
                        default_size TEXT NOT NULL DEFAULT '',
                        default_quality TEXT NOT NULL DEFAULT '',
                        default_output_format TEXT NOT NULL DEFAULT '',
                        default_image_transport TEXT NOT NULL DEFAULT '',
                        logo_overlay_enabled INTEGER NOT NULL DEFAULT 1,
                        auto_copyright_check_enabled INTEGER NOT NULL DEFAULT 1,
                        simple_checklist_completed INTEGER NOT NULL DEFAULT 0,
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
                        reasoning_effort TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'started',
                        prompt TEXT NOT NULL DEFAULT '',
                        original_prompt TEXT NOT NULL DEFAULT '',
                        prompt_mode TEXT NOT NULL DEFAULT 'free',
                        recipe_id TEXT NOT NULL DEFAULT '',
                        recipe_version TEXT NOT NULL DEFAULT '',
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
                        source_generated_image_id INTEGER,
                        asset_kind TEXT NOT NULL DEFAULT 'result',
                        version_note TEXT NOT NULL DEFAULT '',
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
                    CREATE TABLE IF NOT EXISTS generated_image_metadata (
                        generated_image_id INTEGER PRIMARY KEY,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        migrated_from_path TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (generated_image_id) REFERENCES generated_images(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS gallery_image_metadata (
                        generated_image_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        is_favorite INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (generated_image_id, user_id),
                        FOREIGN KEY (generated_image_id) REFERENCES generated_images(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_gallery_metadata_user_favorite
                        ON gallery_image_metadata(user_id, is_favorite, updated_at);

                    CREATE TABLE IF NOT EXISTS gallery_image_tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        generated_image_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        tag TEXT NOT NULL,
                        tag_normalized TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(generated_image_id, user_id, tag_normalized),
                        FOREIGN KEY (generated_image_id) REFERENCES generated_images(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_gallery_tags_user_tag
                        ON gallery_image_tags(user_id, tag_normalized);
                    CREATE INDEX IF NOT EXISTS idx_gallery_tags_image
                        ON gallery_image_tags(generated_image_id, user_id);

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

                    CREATE TABLE IF NOT EXISTS team_chat_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        room_key TEXT NOT NULL,
                        room_type TEXT NOT NULL DEFAULT 'team',
                        sender_user_id INTEGER,
                        sender_type TEXT NOT NULL DEFAULT 'user',
                        sender_name TEXT NOT NULL DEFAULT '',
                        content TEXT NOT NULL,
                        mentions_json TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (sender_user_id) REFERENCES users(id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_team_chat_messages_room
                        ON team_chat_messages(room_key, id);
                    CREATE INDEX IF NOT EXISTS idx_team_chat_messages_created_at
                        ON team_chat_messages(created_at);
                    CREATE INDEX IF NOT EXISTS idx_team_chat_messages_sender
                        ON team_chat_messages(sender_user_id);

                    CREATE TABLE IF NOT EXISTS team_chat_reads (
                        user_id INTEGER NOT NULL,
                        room_key TEXT NOT NULL,
                        last_read_message_id INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (user_id, room_key),
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_team_chat_reads_user
                        ON team_chat_reads(user_id);

                    CREATE TABLE IF NOT EXISTS organization_units (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company TEXT NOT NULL,
                        department TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(company, department)
                    );

                    CREATE INDEX IF NOT EXISTS idx_organization_units_active
                        ON organization_units(is_active, company, department);

                    CREATE TABLE IF NOT EXISTS organization_audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        actor_user_id INTEGER,
                        target_user_id INTEGER NOT NULL,
                        old_company TEXT NOT NULL DEFAULT '',
                        old_department TEXT NOT NULL DEFAULT '',
                        new_company TEXT NOT NULL DEFAULT '',
                        new_department TEXT NOT NULL DEFAULT '',
                        reason TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL,
                        FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_org_audit_target
                        ON organization_audit_events(target_user_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_org_audit_created_at
                        ON organization_audit_events(created_at);

                    CREATE TABLE IF NOT EXISTS group_announcements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        room_key TEXT NOT NULL UNIQUE,
                        company TEXT NOT NULL DEFAULT '',
                        department TEXT NOT NULL DEFAULT '',
                        content TEXT NOT NULL DEFAULT '',
                        created_by_user_id INTEGER,
                        updated_by_user_id INTEGER,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
                        FOREIGN KEY (updated_by_user_id) REFERENCES users(id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_group_announcements_room
                        ON group_announcements(room_key);

                    CREATE TABLE IF NOT EXISTS group_saved_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        room_key TEXT NOT NULL,
                        company TEXT NOT NULL DEFAULT '',
                        department TEXT NOT NULL DEFAULT '',
                        user_id INTEGER,
                        generated_image_id INTEGER,
                        title TEXT NOT NULL DEFAULT '',
                        note TEXT NOT NULL DEFAULT '',
                        prompt TEXT NOT NULL DEFAULT '',
                        mode TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        saved_image_path TEXT NOT NULL DEFAULT '',
                        saved_image_url TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                        FOREIGN KEY (generated_image_id) REFERENCES generated_images(id) ON DELETE SET NULL
                    );

                    CREATE UNIQUE INDEX IF NOT EXISTS idx_group_saved_items_unique_image
                        ON group_saved_items(room_key, generated_image_id)
                        WHERE generated_image_id IS NOT NULL;
                    CREATE INDEX IF NOT EXISTS idx_group_saved_items_room
                        ON group_saved_items(room_key, created_at);
                    """
                )
                migrated_sidecar_paths = self._run_schema_migrations(conn)
                migrated_sidecar_paths += _migrate_legacy_image_sidecars(conn)
            # Delete migrated sidecar files only AFTER the transaction above has
            # committed. Unlinking mid-transaction loses the metadata forever if
            # the commit never happens (crash/rollback): the DB rows vanish but
            # the files are already gone, and the next startup skips them.
            for sidecar_path in migrated_sidecar_paths:
                with suppress(OSError):
                    sidecar_path.unlink()
            self._initialized = True

    def create_user(
        self,
        username: str,
        password: str,
        *,
        role: str = "user",
        is_active: bool = True,
        company: str = DEFAULT_COMPANY,
        department: str = DEFAULT_DEPARTMENT,
    ) -> AuthUser:
        user, _session = self._create_user(
            username,
            password,
            role=role,
            is_active=is_active,
            company=company,
            department=department,
            session_days=None,
        )
        return user

    def create_user_and_session(
        self,
        username: str,
        password: str,
        *,
        days: int,
        company: str = DEFAULT_COMPANY,
        department: str = DEFAULT_DEPARTMENT,
    ) -> tuple[AuthUser, AuthSession]:
        user, session = self._create_user(
            username,
            password,
            role="user",
            is_active=True,
            company=company,
            department=department,
            session_days=days,
        )
        if session is None:  # pragma: no cover - guarded by session_days
            raise RuntimeError("session was not created")
        return user, session

    def _create_user(
        self,
        username: str,
        password: str,
        *,
        role: str,
        is_active: bool,
        company: str,
        department: str,
        session_days: int | None,
    ) -> tuple[AuthUser, AuthSession | None]:
        now = _now_text()
        normalized = normalize_username(username)
        normalized_role = normalize_role(role)
        clean_company, clean_department = normalize_user_org(
            company,
            department,
            username_normalized=normalized,
            role=normalized_role,
        )
        with self._lock, self._connect() as conn:
            _require_active_org_unit(conn, clean_company, clean_department)
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        username,
                        username_normalized,
                        password_hash,
                        role,
                        is_active,
                        company,
                        department,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        username.strip(),
                        normalized,
                        hash_password(password),
                        normalized_role,
                        1 if is_active else 0,
                        clean_company,
                        clean_department,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise UserExistsError(username) from exc
            user_id = _require_lastrowid(cursor)
            user = AuthUser(
                id=user_id,
                username=username.strip(),
                created_at=now,
                role=normalized_role,
                is_active=is_active,
                company=clean_company,
                department=clean_department,
            )
            session = (
                self._insert_session(conn, user_id, days=session_days)
                if session_days is not None
                else None
            )
            return user, session

    def ensure_admin_user(self, username: str, password: str) -> AuthUser:
        if not password:
            raise ValueError("管理员密码不能为空")
        now = _now_text()
        normalized = normalize_username(username)
        clean_username = username.strip()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM users
                WHERE username_normalized = ?
                """,
                (normalized,),
            ).fetchone()
            if row is None:
                try:
                    cursor = conn.execute(
                        """
                        INSERT INTO users (
                            username,
                            username_normalized,
                            password_hash,
                            role,
                            is_active,
                            company,
                            department,
                            created_at
                        )
                        VALUES (?, ?, ?, 'admin', 1, '', '', ?)
                        """,
                        (clean_username, normalized, hash_password(password), now),
                    )
                except sqlite3.IntegrityError:
                    # Another uvicorn worker bootstrapping the same fresh DB won
                    # the INSERT between our SELECT and here (the threading lock
                    # cannot serialize across processes). Fall through to the
                    # UPDATE path against the row that now exists.
                    row = conn.execute(
                        "SELECT * FROM users WHERE username_normalized = ?",
                        (normalized,),
                    ).fetchone()
                    if row is None:  # pragma: no cover - defensive
                        raise
                else:
                    return _auth_user_from_values(
                        user_id=_require_lastrowid(cursor),
                        username=clean_username,
                        created_at=now,
                        role="admin",
                        is_active=True,
                        company="",
                        department="",
                    )
            conn.execute(
                """
                UPDATE users
                SET username = ?, password_hash = ?, role = 'admin', is_active = 1,
                    failed_login_count = 0, locked_until = NULL
                WHERE id = ?
                """,
                (clean_username, hash_password(password), row["id"]),
            )
            return _auth_user_from_row(row, username=clean_username, role="admin", is_active=True)

    def authenticate(self, username: str, password: str) -> AuthUser:
        user, _session = self._authenticate_credentials(username, password, session_days=None)
        return user

    def authenticate_and_create_session(
        self,
        username: str,
        password: str,
        *,
        days: int,
    ) -> tuple[AuthUser, AuthSession]:
        user, session = self._authenticate_credentials(username, password, session_days=days)
        if session is None:  # pragma: no cover - guarded by session_days
            raise RuntimeError("session was not created")
        return user, session

    def _authenticate_credentials(
        self,
        username: str,
        password: str,
        *,
        session_days: int | None,
    ) -> tuple[AuthUser, AuthSession | None]:
        normalized = normalize_username(username)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    *
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
            verified_password_hash = str(row["password_hash"])
            if not verify_password(password, verified_password_hash):
                lock_until_text = _datetime_text(now_dt + timedelta(minutes=_ACCOUNT_LOCK_MINUTES))
                # Atomic increment: a read-modify-write in Python loses counts
                # when several workers process wrong passwords concurrently
                # (PBKDF2 keeps the window wide open). An expired lock means the
                # user served their time — restart the count at 1 so they are
                # not re-locked by the very next wrong guess.
                # "已服完刑"必须校验 locked_until 确实过期：跨 worker 并发时
                # 另一个 worker 可能刚写入新锁，无条件的 IS NOT NULL 分支会把
                # 刚生效的锁清掉，阈值处的并发爆破就永远锁不住。
                now_text = _datetime_text(now_dt)
                conn.execute(
                    """
                    UPDATE users
                    SET failed_login_count = CASE
                            WHEN locked_until IS NOT NULL AND locked_until <= ? THEN 1
                            ELSE COALESCE(failed_login_count, 0) + 1
                        END,
                        locked_until = CASE
                            WHEN locked_until IS NOT NULL AND locked_until <= ? THEN NULL
                            WHEN locked_until IS NOT NULL THEN locked_until
                            WHEN COALESCE(failed_login_count, 0) + 1 >= ? THEN ?
                            ELSE NULL
                        END
                    WHERE id = ? AND password_hash = ? AND is_active = 1
                    """,
                    (
                        now_text,
                        now_text,
                        _MAX_FAILED_LOGIN_ATTEMPTS,
                        lock_until_text,
                        row["id"],
                        verified_password_hash,
                    ),
                )
                conn.commit()
                raise InvalidCredentialsError(username)
            now = _now_text()
            updated_cursor = conn.execute(
                """
                UPDATE users
                SET last_login_at = ?, failed_login_count = 0, locked_until = NULL
                WHERE id = ?
                  AND password_hash = ?
                  AND is_active = 1
                  AND (locked_until IS NULL OR locked_until <= ?)
                """,
                (now, row["id"], verified_password_hash, now),
            )
            if updated_cursor.rowcount != 1:
                current = conn.execute(
                    "SELECT is_active, password_hash, locked_until FROM users WHERE id = ?",
                    (row["id"],),
                ).fetchone()
                current_lock = _parse_datetime_text(current["locked_until"]) if current is not None else None
                if current is not None and bool(current["is_active"]) and current_lock and current_lock > _now():
                    raise AccountLockedError(username)
                raise InvalidCredentialsError(username)
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
            if updated is None:  # pragma: no cover - row was updated above
                raise InvalidCredentialsError(username)
            session = (
                self._insert_session(conn, int(row["id"]), days=session_days)
                if session_days is not None
                else None
            )
            return _auth_user_from_row(updated), session

    def request_password_reset(
        self,
        username: str,
        *,
        client_host: str = "",
        user_agent: str = "",
        token_expires_at: str | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_username(username)
        clean_username = username.strip()
        now = _now_text()
        reset_token = secrets.token_urlsafe(_PASSWORD_RESET_TOKEN_BYTES)
        token_hash = hash_session_token(reset_token)
        expires_at = token_expires_at or _datetime_text(_now() + timedelta(minutes=30))
        with self._lock, self._connect() as conn:
            user_row = conn.execute(
                """
                SELECT id, username, email
                FROM users
                WHERE username_normalized = ?
                """,
                (normalized,),
            ).fetchone()
            user_id = int(user_row["id"]) if user_row is not None else None
            display_username = str(user_row["username"] or clean_username) if user_row is not None else clean_username
            email = str(user_row["email"] or "").strip() if user_row is not None else ""
            existing = conn.execute(
                """
                SELECT id, created_at, expires_at
                FROM password_reset_requests
                WHERE username_normalized = ? AND status = 'pending'
                ORDER BY id DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if existing is not None:
                request_id = int(existing["id"])
                existing_created_at = _parse_datetime_text(existing["created_at"])
                if (
                    existing_created_at is not None
                    and _now() - existing_created_at < timedelta(minutes=_PASSWORD_RESET_REQUEST_THROTTLE_MINUTES)
                ):
                    return {
                        "id": request_id,
                        "user_id": user_id,
                        "username": display_username[:64],
                        "username_normalized": normalized,
                        "status": "pending",
                        "matched_user": user_id is not None,
                        "email": email[:160],
                        "email_available": bool(user_id is not None and email),
                        "reset_token": "",
                        "expires_at": str(existing["expires_at"] or expires_at),
                        "requested_ip": client_host.strip()[:128],
                        "user_agent": user_agent.strip()[:512],
                        "created_at": str(existing["created_at"] or now),
                        "notification_suppressed": True,
                    }
                conn.execute(
                    """
                    UPDATE password_reset_requests
                    SET
                        user_id = ?,
                        username = ?,
                        token_hash = ?,
                        email = ?,
                        email_sent_at = NULL,
                        expires_at = ?,
                        requested_ip = ?,
                        user_agent = ?,
                        created_at = ?
                    WHERE id = ?
                    """,
                    (
                        user_id,
                        display_username[:64],
                        token_hash if user_id is not None and email else None,
                        email[:160],
                        expires_at,
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
                        token_hash,
                        email,
                        expires_at,
                        requested_ip,
                        user_agent,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        display_username[:64],
                        normalized,
                        token_hash if user_id is not None and email else None,
                        email[:160],
                        expires_at,
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
            "email": email[:160],
            "email_available": bool(user_id is not None and email),
            "reset_token": reset_token if user_id is not None and email else "",
            "expires_at": expires_at,
            "requested_ip": client_host.strip()[:128],
            "user_agent": user_agent.strip()[:512],
            "created_at": now,
        }

    def mark_password_reset_email_sent(self, request_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE password_reset_requests
                SET email_sent_at = ?
                WHERE id = ?
                """,
                (_now_text(), request_id),
            )

    def reset_password_with_token(self, *, token: str, password: str) -> AuthUser | None:
        token_hash = hash_session_token(token.strip())
        now_dt = _now()
        now = _datetime_text(now_dt)
        new_hash = hash_password(password)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    u.*,
                    r.id AS reset_request_id,
                    r.user_id AS reset_user_id,
                    r.username_normalized AS reset_username_normalized,
                    r.expires_at AS reset_expires_at
                FROM password_reset_requests r
                JOIN users u ON u.id = r.user_id
                WHERE r.token_hash = ?
                  AND r.status = 'pending'
                  AND u.is_active = 1
                ORDER BY r.id DESC
                LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            expires_at = _parse_datetime_text(row["reset_expires_at"])
            if expires_at is None or expires_at <= now_dt:
                conn.execute(
                    """
                    UPDATE password_reset_requests
                    SET status = 'expired', resolved_at = ?
                    WHERE id = ?
                    """,
                    (now, row["reset_request_id"]),
                )
                return None
            user_id = int(row["reset_user_id"])
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
                    resolved_by_user_id = NULL
                WHERE status = 'pending'
                  AND (user_id = ? OR token_hash = ?)
                """,
                (now, user_id, token_hash),
            )
        return _auth_user_from_row(row)

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
                    r.email,
                    r.email_sent_at,
                    r.expires_at,
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

    def list_organization_units(self, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        where_clause = "" if include_inactive else "WHERE is_active = 1"
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, company, department, is_active, created_at, updated_at
                FROM organization_units
                {where_clause}
                ORDER BY company COLLATE NOCASE ASC, department COLLATE NOCASE ASC
                """
            ).fetchall()
        return [_organization_unit_row_to_dict(row) for row in rows]

    def create_organization_unit(self, *, company: str, department: str) -> dict[str, Any]:
        clean_company, clean_department = normalize_org_unit(company, department)
        now = _now_text()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO organization_units (company, department, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(company, department) DO UPDATE SET
                    is_active = 1,
                    updated_at = excluded.updated_at
                """,
                (clean_company, clean_department, now, now),
            )
            row = conn.execute(
                """
                SELECT id, company, department, is_active, created_at, updated_at
                FROM organization_units
                WHERE company = ? AND department = ?
                """,
                (clean_company, clean_department),
            ).fetchone()
        if row is None:
            raise RuntimeError("组织单位创建失败")
        return _organization_unit_row_to_dict(row)

    def update_user_org(
        self,
        *,
        user_id: int,
        company: str,
        department: str,
        actor_user_id: int,
        reason: str = "",
    ) -> AuthUser | None:
        now = _now_text()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                return None
            clean_company, clean_department = normalize_user_org(
                company,
                department,
                username_normalized=str(row["username_normalized"] or ""),
                role=str(row["role"] or "user"),
            )
            _require_active_org_unit(conn, clean_company, clean_department)
            old_company = str(row["company"] or "")
            old_department = str(row["department"] or "")
            conn.execute(
                """
                UPDATE users
                SET company = ?, department = ?
                WHERE id = ?
                """,
                (clean_company, clean_department, user_id),
            )
            conn.execute(
                """
                INSERT INTO organization_audit_events (
                    actor_user_id,
                    target_user_id,
                    old_company,
                    old_department,
                    new_company,
                    new_department,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor_user_id,
                    user_id,
                    old_company[:120],
                    old_department[:120],
                    clean_company,
                    clean_department,
                    reason.strip()[:1000],
                    now,
                ),
            )
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _auth_user_from_row(updated) if updated is not None else None

    def list_organization_audit_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    e.id,
                    e.actor_user_id,
                    actor.username AS actor_username,
                    e.target_user_id,
                    target.username AS target_username,
                    e.old_company,
                    e.old_department,
                    e.new_company,
                    e.new_department,
                    e.reason,
                    e.created_at
                FROM organization_audit_events e
                LEFT JOIN users actor ON actor.id = e.actor_user_id
                JOIN users target ON target.id = e.target_user_id
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [_organization_audit_row_to_dict(row) for row in rows]

    def reset_user_password(self, *, user_id: int, password: str, admin_user_id: int) -> AuthUser | None:
        now = _now_text()
        new_hash = hash_password(password)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
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
        return _auth_user_from_row(row)

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
                SELECT *
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None or not bool(row["is_active"]):
                raise InvalidCredentialsError("inactive")
            verified_password_hash = str(row["password_hash"])
            if not verify_password(current_password, verified_password_hash):
                raise InvalidCredentialsError("current_password")
            updated_cursor = conn.execute(
                """
                UPDATE users
                SET
                    password_hash = ?,
                    password_changed_at = ?,
                    failed_login_count = 0,
                    locked_until = NULL
                WHERE id = ? AND password_hash = ? AND is_active = 1
                """,
                (hash_password(new_password), now, user_id, verified_password_hash),
            )
            if updated_cursor.rowcount != 1:
                raise InvalidCredentialsError("current_password")
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
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if updated is None:  # pragma: no cover - guarded by successful update
                raise InvalidCredentialsError("inactive")
        return _auth_user_from_row(updated)

    def update_user_profile(
        self,
        *,
        user_id: int,
        username: str,
        current_password: str,
        display_name: str,
        wechat: str,
        phone_country_code: str,
        phone: str,
        email: str,
        company: str,
        department: str,
        team: str,
        job_title: str,
        note: str,
        current_session_token: str = "",
    ) -> AuthUser:
        token_hash = hash_session_token(current_session_token) if current_session_token else ""
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None or not bool(row["is_active"]):
                raise InvalidCredentialsError("inactive")
            clean_username = username.strip() or str(row["username"])
            normalized_username = normalize_username(clean_username)
            username_changed = normalized_username != str(row["username_normalized"])
            verified_password_hash = str(row["password_hash"])
            if username_changed and not verify_password(current_password, verified_password_hash):
                raise InvalidCredentialsError("current_password")
            # Organization membership is an authorization boundary. Profile
            # edits may carry stale or forged organization fields, but only an
            # administrator may change the stored assignment.
            clean_company = str(row["company"] or "")
            clean_department = str(row["department"] or "")
            try:
                updated_cursor = conn.execute(
                    """
                    UPDATE users
                    SET
                        username = ?,
                        username_normalized = ?,
                        display_name = ?,
                        wechat = ?,
                        phone_country_code = ?,
                        phone = ?,
                        email = ?,
                        company = ?,
                        department = ?,
                        team = ?,
                        job_title = ?,
                        note = ?
                    WHERE id = ?
                      AND is_active = 1
                      AND (? = 0 OR password_hash = ?)
                    """,
                    (
                        clean_username,
                        normalized_username,
                        display_name.strip()[:80],
                        wechat.strip()[:120],
                        phone_country_code.strip()[:8] or "+86",
                        phone.strip()[:40],
                        email.strip()[:160],
                        clean_company,
                        clean_department,
                        team.strip()[:120],
                        job_title.strip()[:120],
                        note.strip()[:1000],
                        user_id,
                        int(username_changed),
                        verified_password_hash,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise UserExistsError(clean_username) from exc
            if updated_cursor.rowcount != 1:
                raise InvalidCredentialsError("current_password" if username_changed else "inactive")
            if username_changed:
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
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if updated is None:
                raise InvalidCredentialsError("inactive")
            return _auth_user_from_row(updated)

    def update_user_avatar(self, *, user_id: int, avatar_path: str, avatar_url: str) -> AuthUser | None:
        user, _previous_path = self.replace_user_avatar(
            user_id=user_id,
            avatar_path=avatar_path,
            avatar_url=avatar_url,
        )
        return user

    def replace_user_avatar(
        self,
        *,
        user_id: int,
        avatar_path: str,
        avatar_url: str,
    ) -> tuple[AuthUser | None, str]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None or not bool(row["is_active"]):
                return None, ""
            previous_path = str(row["avatar_path"] or "")
            conn.execute(
                """
                UPDATE users
                SET avatar_path = ?, avatar_url = ?
                WHERE id = ?
                """,
                (avatar_path.strip()[:1024], avatar_url.strip()[:1024], user_id),
            )
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return (_auth_user_from_row(updated) if updated is not None else None), previous_path

    def create_session(self, user_id: int, *, days: int) -> AuthSession:
        with self._lock, self._connect() as conn:
            return self._insert_session(conn, user_id, days=days)

    @staticmethod
    def _insert_session(conn: sqlite3.Connection, user_id: int, *, days: int) -> AuthSession:
        token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
        created_at = _now()
        expires_at = created_at + timedelta(days=days)
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
                SELECT u.*
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
            return _auth_user_from_row(row)

    def create_generation_job(
        self,
        *,
        request_id: str,
        user_id: int | None,
        username: str = "",
        endpoint_path: str,
        mode: str = "",
        transport: str = "",
        reasoning_effort: str = "",
        prompt: str = "",
        original_prompt: str = "",
        prompt_mode: str = "free",
        recipe_id: str = "",
        recipe_version: str = "",
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
                    reasoning_effort,
                    prompt,
                    original_prompt,
                    prompt_mode,
                    recipe_id,
                    recipe_version,
                    model,
                    size,
                    sample_count,
                    logo_requested,
                    started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id.strip()[:128],
                    user_id,
                    username.strip()[:128],
                    endpoint_path.strip()[:128],
                    mode.strip()[:64],
                    transport.strip()[:64],
                    reasoning_effort.strip()[:32],
                    prompt.strip()[:32_000],
                    original_prompt.strip()[:32_000],
                    prompt_mode.strip()[:32] or "free",
                    recipe_id.strip()[:128],
                    recipe_version.strip()[:64],
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
                    transport = COALESCE(NULLIF(?, ''), transport),
                    reasoning_effort = COALESCE(NULLIF(?, ''), reasoning_effort),
                    model = COALESCE(NULLIF(?, ''), model),
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
                    str(result.get("transport") or "").strip()[:64],
                    str(result.get("reasoning_effort") or "").strip()[:32],
                    str(result.get("model") or "").strip()[:128],
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
                # Use the candidate's original upstream index when the payload
                # carries it; the response side matches records to images by
                # this value, so a positional fallback would misattach ids
                # whenever an unsaveable candidate shifted the positions.
                candidate_index = int(image.get("candidate_index", index) or 0)
                source_generated_image_id = _validated_source_generated_image_id(
                    conn,
                    source_id=(
                        image.get("source_generated_image_id")
                        or result.get("source_generated_image_id")
                    ),
                    user_id=job_user_id,
                )
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
                        source_generated_image_id,
                        asset_kind,
                        version_note,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        job_user_id,
                        candidate_index,
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
                        source_generated_image_id,
                        str(image.get("asset_kind") or result.get("asset_kind") or "result")[:64],
                        str(image.get("version_note") or result.get("version_note") or "")[:255],
                        now,
                    ),
                )
                generated_image_id = _require_lastrowid(cursor)
                _upsert_generated_image_metadata(
                    conn,
                    generated_image_id=generated_image_id,
                    metadata=image.get("metadata"),
                    migrated_from_path="",
                    now=now,
                )
                created.append({"id": generated_image_id, "candidate_index": candidate_index})
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
                    source_generated_image_id,
                    asset_kind,
                    version_note,
                    created_at
                FROM generated_images
                WHERE id = ? AND user_id = ?
                """,
                (generated_image_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return _generated_image_row_to_dict(row)

    def resolve_generated_image_id_from_source(
        self,
        *,
        user_id: int,
        source_names: list[str],
        source_urls: list[str],
        source_paths: list[str],
    ) -> int | None:
        names = _clean_source_tokens(source_names, max_length=255)
        urls = _clean_source_tokens(source_urls, max_length=1024)
        paths = _clean_source_tokens(source_paths, max_length=1024)
        clauses: list[str] = []
        params: list[Any] = [user_id]
        if names:
            placeholders = ",".join("?" for _ in names)
            clauses.append(f"saved_image_name IN ({placeholders})")
            params.extend(names)
        if urls:
            placeholders = ",".join("?" for _ in urls)
            clauses.append(f"saved_image_url IN ({placeholders})")
            params.extend(urls)
        if paths:
            placeholders = ",".join("?" for _ in paths)
            clauses.append(f"saved_image_path IN ({placeholders})")
            params.extend(paths)
        if not clauses:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id
                FROM generated_images
                WHERE user_id = ?
                  AND ({' OR '.join(clauses)})
                ORDER BY id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        return int(row["id"]) if row is not None else None

    def generated_image_detail_for_user(self, *, generated_image_id: int, user_id: int) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    gi.id,
                    gi.job_id,
                    gi.user_id,
                    gi.candidate_index,
                    gi.mode,
                    gi.model,
                    gi.prompt,
                    gi.saved_image_path,
                    gi.saved_image_url,
                    gi.saved_image_name,
                    gi.saved_metadata_path,
                    gi.saved_metadata_url,
                    gi.saved_image_mime,
                    gi.saved_image_width,
                    gi.saved_image_height,
                    gi.saved_image_bytes,
                    gi.logo_requested,
                    gi.logo_overlay_applied,
                    gi.source_generated_image_id,
                    gi.asset_kind,
                    gi.version_note,
                    gi.created_at,
                    j.request_id,
                    j.endpoint_path,
                    j.transport,
                    j.prompt AS effective_prompt,
                    j.original_prompt,
                    j.prompt_mode,
                    j.recipe_id,
                    j.recipe_version,
                    j.status,
                    j.sample_count,
                    j.started_at,
                    j.completed_at,
                    j.elapsed_ms,
                    COALESCE(gim.metadata_json, '{}') AS metadata_json
                FROM generated_images gi
                JOIN generation_jobs j ON j.id = gi.job_id
                LEFT JOIN generated_image_metadata gim ON gim.generated_image_id = gi.id
                WHERE gi.id = ? AND gi.user_id = ?
                """,
                (generated_image_id, user_id),
            ).fetchone()
        if row is None:
            return None
        item = _generated_image_row_to_dict(row)
        metadata: dict[str, Any] = {}
        try:
            parsed = json.loads(str(row["metadata_json"] or "{}"))
            if isinstance(parsed, dict):
                metadata = parsed
        except json.JSONDecodeError:
            metadata = {}
        item["lineage"] = {
            "request_id": str(row["request_id"] or ""),
            "endpoint_path": str(row["endpoint_path"] or ""),
            "transport": str(row["transport"] or ""),
            "prompt_mode": str(row["prompt_mode"] or "free"),
            "original_prompt": str(row["original_prompt"] or row["effective_prompt"] or ""),
            "effective_prompt": str(row["effective_prompt"] or row["prompt"] or ""),
            "recipe_id": str(row["recipe_id"] or ""),
            "recipe_version": str(row["recipe_version"] or ""),
            "status": str(row["status"] or ""),
            "sample_count": max(1, int(row["sample_count"] or 1)),
            "started_at": str(row["started_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
            "elapsed_ms": float(row["elapsed_ms"]) if row["elapsed_ms"] is not None else None,
        }
        item["metadata"] = metadata
        _attach_original_source_fields(item, metadata)
        return item

    def list_generated_image_versions_for_user(
        self,
        *,
        generated_image_id: int,
        user_id: int,
        limit: int = 200,
    ) -> list[dict[str, Any]] | None:
        bounded_limit = max(1, min(int(limit or 200), 500))
        with self._lock, self._connect() as conn:
            # Scope the fetch to the requested image's LINEAGE (ancestors, then
            # everything below each ancestor). A flat per-user query with LIMIT
            # ordered oldest-first stopped covering newer images as soon as a
            # user's library outgrew the limit — version history then 404'd for
            # every image after the first `limit`.
            rows = conn.execute(
                """
                WITH RECURSIVE
                ancestors(id) AS (
                    SELECT id FROM generated_images WHERE id = ? AND user_id = ?
                    UNION
                    SELECT parent.id
                    FROM generated_images parent
                    JOIN generated_images child ON child.source_generated_image_id = parent.id
                    JOIN ancestors a ON child.id = a.id
                    WHERE parent.user_id = ?
                ),
                lineage(id) AS (
                    SELECT id FROM ancestors
                    UNION
                    SELECT child.id
                    FROM generated_images child
                    JOIN lineage l ON child.source_generated_image_id = l.id
                    WHERE child.user_id = ?
                )
                SELECT
                    gi.*,
                    j.request_id,
                    j.endpoint_path,
                    j.transport,
                    j.prompt AS effective_prompt,
                    j.original_prompt,
                    j.prompt_mode,
                    j.recipe_id,
                    j.recipe_version,
                    j.status,
                    j.sample_count,
                    j.started_at,
                    j.completed_at,
                    j.elapsed_ms,
                    COALESCE(gim.metadata_json, '{}') AS metadata_json
                FROM generated_images gi
                JOIN generation_jobs j ON j.id = gi.job_id
                LEFT JOIN generated_image_metadata gim ON gim.generated_image_id = gi.id
                WHERE gi.id IN (SELECT id FROM lineage)
                  AND gi.user_id = ?
                  AND gi.saved_image_url != ''
                ORDER BY gi.created_at ASC, gi.id ASC
                LIMIT ?
                """,
                (generated_image_id, user_id, user_id, user_id, user_id, bounded_limit),
            ).fetchall()
        records = {int(row["id"]): _version_image_row_to_dict(row) for row in rows}
        if generated_image_id not in records:
            return None

        root_id = generated_image_id
        visited: set[int] = set()
        while root_id not in visited:
            visited.add(root_id)
            parent_id = records[root_id].get("source_generated_image_id")
            if not isinstance(parent_id, int) or parent_id not in records:
                break
            root_id = parent_id

        children: dict[int, list[int]] = {}
        for item_id, item in records.items():
            parent_id = item.get("source_generated_image_id")
            if isinstance(parent_id, int) and parent_id in records:
                children.setdefault(parent_id, []).append(item_id)
        for child_ids in children.values():
            child_ids.sort(key=lambda value: (records[value].get("created_at", ""), value))

        ordered: list[dict[str, Any]] = []
        queued = [(root_id, 0)]
        seen: set[int] = set()
        while queued and len(ordered) < bounded_limit:
            item_id, depth = queued.pop(0)
            if item_id in seen:
                continue
            seen.add(item_id)
            item = {**records[item_id], "version_depth": depth, "is_current": item_id == generated_image_id}
            ordered.append(item)
            queued.extend((child_id, depth + 1) for child_id in children.get(item_id, []))
        return ordered

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
                SELECT id, user_id, job_id
                FROM generated_images
                WHERE id = ? AND user_id = ?
                """,
                (generated_image_id, user_id),
            ).fetchone()
            if row is None:
                raise PermissionError("无权更新这张图片")
            first_logo_final_for_job = False
            if logo_overlay_applied:
                existing_logo_final = conn.execute(
                    """
                    SELECT 1
                    FROM generated_images
                    WHERE job_id = ? AND logo_overlay_applied = 1
                    LIMIT 1
                    """,
                    (int(row["job_id"]),),
                ).fetchone()
                first_logo_final_for_job = existing_logo_final is None
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
                    logo_requested = CASE WHEN ? THEN 1 ELSE logo_requested END,
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
                    source_generated_image_id,
                    asset_kind,
                    version_note,
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
            _upsert_generated_image_metadata(
                conn,
                generated_image_id=generated_image_id,
                metadata=image.get("metadata"),
                migrated_from_path="",
                now=now,
            )
        if updated is None:
            raise RuntimeError("更新后的图片记录不存在")
        result = _generated_image_row_to_dict(updated)
        result["_first_logo_final_for_job"] = first_logo_final_for_job
        return result

    def list_gallery_items(
        self,
        *,
        viewer_user_id: int,
        target_user_id: int | None,
        query: str = "",
        tag: str = "",
        favorite_only: bool = False,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit or 60), 200))
        clean_query = query.strip()[:200]
        clean_tag = tag.strip()[:40]
        conditions: list[str] = ["gi.saved_image_url != ''"]
        params: list[Any] = []
        if target_user_id is not None:
            conditions.append("gi.user_id = ?")
            params.append(target_user_id)
        if clean_query:
            like = f"%{clean_query}%"
            conditions.append(
                """
                (
                    gi.prompt LIKE ?
                    OR gi.model LIKE ?
                    OR gi.mode LIKE ?
                    OR gi.saved_image_name LIKE ?
                    OR owner.username LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM gallery_image_tags tag_search
                        WHERE tag_search.generated_image_id = gi.id
                          AND tag_search.user_id = ?
                          AND tag_search.tag LIKE ?
                    )
                )
                """
            )
            params.extend([like, like, like, like, like, viewer_user_id, like])
        if clean_tag:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM gallery_image_tags tag_filter
                    WHERE tag_filter.generated_image_id = gi.id
                      AND tag_filter.user_id = ?
                      AND tag_filter.tag_normalized = ?
                )
                """
            )
            params.extend([viewer_user_id, clean_tag.casefold()])
        if favorite_only:
            conditions.append("COALESCE(meta.is_favorite, 0) = 1")
        params.append(bounded_limit)
        where_sql = " AND ".join(f"({condition})" for condition in conditions)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    gi.*,
                    owner.username AS username,
                    owner.display_name AS display_name,
                    COALESCE(meta.is_favorite, 0) AS is_favorite,
                    meta.updated_at AS gallery_updated_at,
                    COALESCE(gim.metadata_json, '{{}}') AS metadata_json,
                    COALESCE((
                        SELECT GROUP_CONCAT(t.tag, char(31))
                        FROM gallery_image_tags t
                        WHERE t.generated_image_id = gi.id
                          AND t.user_id = ?
                        ORDER BY t.id
                    ), '') AS tags_text
                FROM generated_images gi
                LEFT JOIN users owner ON owner.id = gi.user_id
                LEFT JOIN gallery_image_metadata meta
                    ON meta.generated_image_id = gi.id
                   AND meta.user_id = ?
                LEFT JOIN generated_image_metadata gim
                    ON gim.generated_image_id = gi.id
                WHERE {where_sql}
                ORDER BY gi.created_at DESC, gi.id DESC
                LIMIT ?
                """,
                (viewer_user_id, viewer_user_id, *params),
            ).fetchall()
        return [_gallery_image_row_to_dict(row) for row in rows]

    def list_generation_jobs_for_user(self, *, user_id: int, limit: int = 30) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit or 30), 100))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    j.id,
                    j.request_id,
                    j.user_id,
                    j.username,
                    j.endpoint_path,
                    j.mode,
                    j.transport,
                    j.reasoning_effort,
                    j.status,
                    j.prompt,
                    j.original_prompt,
                    j.prompt_mode,
                    j.recipe_id,
                    j.recipe_version,
                    j.model,
                    j.size,
                    j.sample_count,
                    j.logo_requested,
                    j.image_count,
                    j.saved_bytes,
                    j.error_code,
                    j.error_message,
                    j.started_at,
                    j.completed_at,
                    j.elapsed_ms,
                    first_image.id AS first_generated_image_id,
                    first_image.saved_image_url AS first_saved_image_url,
                    first_image.saved_image_name AS first_saved_image_name,
                    first_image.logo_overlay_applied AS first_logo_overlay_applied
                FROM generation_jobs j
                LEFT JOIN generated_images first_image
                    ON first_image.id = (
                        SELECT gi.id
                        FROM generated_images gi
                        WHERE gi.job_id = j.id
                        ORDER BY gi.candidate_index ASC, gi.id ASC
                        LIMIT 1
                    )
                WHERE j.user_id = ?
                ORDER BY j.started_at DESC, j.id DESC
                LIMIT ?
                """,
                (user_id, bounded_limit),
            ).fetchall()
        return [_generation_job_row_to_dict(row) for row in rows]

    def update_gallery_item(
        self,
        *,
        user_id: int,
        generated_image_id: int,
        is_favorite: bool,
        tags: list[str],
    ) -> dict[str, Any]:
        cleaned_tags = normalize_gallery_tags(tags)
        now = _now_text()
        with self._lock, self._connect() as conn:
            image = conn.execute(
                """
                SELECT id
                FROM generated_images
                WHERE id = ? AND user_id = ?
                """,
                (generated_image_id, user_id),
            ).fetchone()
            if image is None:
                raise PermissionError("无权整理这张图片")
            conn.execute(
                """
                INSERT INTO gallery_image_metadata (
                    generated_image_id,
                    user_id,
                    is_favorite,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(generated_image_id, user_id) DO UPDATE SET
                    is_favorite = excluded.is_favorite,
                    updated_at = excluded.updated_at
                """,
                (generated_image_id, user_id, 1 if is_favorite else 0, now),
            )
            conn.execute(
                "DELETE FROM gallery_image_tags WHERE generated_image_id = ? AND user_id = ?",
                (generated_image_id, user_id),
            )
            for tag in cleaned_tags:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO gallery_image_tags (
                        generated_image_id,
                        user_id,
                        tag,
                        tag_normalized,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (generated_image_id, user_id, tag, tag.casefold(), now),
                )
            row = conn.execute(
                """
                SELECT
                    gi.*,
                    owner.username AS username,
                    owner.display_name AS display_name,
                    COALESCE(meta.is_favorite, 0) AS is_favorite,
                    meta.updated_at AS gallery_updated_at,
                    COALESCE(gim.metadata_json, '{}') AS metadata_json,
                    COALESCE((
                        SELECT GROUP_CONCAT(t.tag, char(31))
                        FROM gallery_image_tags t
                        WHERE t.generated_image_id = gi.id
                          AND t.user_id = ?
                        ORDER BY t.id
                    ), '') AS tags_text
                FROM generated_images gi
                LEFT JOIN users owner ON owner.id = gi.user_id
                LEFT JOIN gallery_image_metadata meta
                    ON meta.generated_image_id = gi.id
                   AND meta.user_id = ?
                LEFT JOIN generated_image_metadata gim
                    ON gim.generated_image_id = gi.id
                WHERE gi.id = ?
                """,
                (user_id, user_id, generated_image_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("更新后的作品不存在")
        return _gallery_image_row_to_dict(row)

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

    def can_user_access_output(
        self,
        *,
        user_id: int,
        is_admin: bool,
        relative_path: str,
        absolute_path: Path,
    ) -> bool:
        if is_admin:
            return True
        references = _output_reference_tokens(
            relative_path=relative_path,
            absolute_path=absolute_path,
        )
        if not references:
            return False
        placeholders = ",".join("?" for _ in references)
        image_match = (
            f"(saved_image_url IN ({placeholders}) "
            f"OR saved_image_path IN ({placeholders}) "
            f"OR saved_metadata_url IN ({placeholders}) "
            f"OR saved_metadata_path IN ({placeholders}))"
        )
        shared_match = (
            f"(gi.saved_image_url IN ({placeholders}) "
            f"OR gi.saved_image_path IN ({placeholders}) "
            f"OR gi.saved_metadata_url IN ({placeholders}) "
            f"OR gi.saved_metadata_path IN ({placeholders}))"
        )
        group_match = (
            f"(gi.saved_image_url IN ({placeholders}) "
            f"OR gi.saved_image_path IN ({placeholders}) "
            f"OR gi.saved_metadata_url IN ({placeholders}) "
            f"OR gi.saved_metadata_path IN ({placeholders}))"
        )
        with self._lock, self._connect() as conn:
            owned = conn.execute(
                f"SELECT 1 FROM generated_images WHERE user_id = ? AND {image_match} LIMIT 1",
                (user_id, *references, *references, *references, *references),
            ).fetchone()
            if owned is not None:
                return True
            metadata_owned = conn.execute(
                f"""
                SELECT 1
                FROM generated_images gi
                JOIN generated_image_metadata gim ON gim.generated_image_id = gi.id
                WHERE gi.user_id = ?
                  AND (
                    json_extract(gim.metadata_json, '$.source_saved_image_url') IN ({placeholders})
                    OR json_extract(gim.metadata_json, '$.source_saved_image_path') IN ({placeholders})
                    OR json_extract(gim.metadata_json, '$.source_image_path') IN ({placeholders})
                  )
                LIMIT 1
                """,
                (user_id, *references, *references, *references),
            ).fetchone()
            if metadata_owned is not None:
                return True
            shared = conn.execute(
                f"""
                SELECT 1
                FROM shared_results s
                JOIN generated_images gi
                  ON gi.id = s.generated_image_id
                 AND gi.user_id = s.sender_user_id
                WHERE s.recipient_user_id = ? AND {shared_match}
                LIMIT 1
                """,
                (user_id, *references, *references, *references, *references),
            ).fetchone()
            if shared is not None:
                return True
            user_row = conn.execute(
                "SELECT id, username_normalized, role, company, department FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user_row is None:
                return False
            room_key = _team_chat_group_from_user_row(user_row)["room_key"]
            grouped = conn.execute(
                f"""
                SELECT 1
                FROM group_saved_items item
                JOIN generated_images gi ON gi.id = item.generated_image_id
                WHERE item.room_key = ? AND {group_match}
                LIMIT 1
                """,
                (room_key, *references, *references, *references, *references),
            ).fetchone()
        return grouped is not None

    def get_user_preferences(self, *, user_id: int) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    ui_mode,
                    default_model,
                    default_responses_model,
                    default_size,
                    default_quality,
                    default_output_format,
                    default_image_transport,
                    logo_overlay_enabled,
                    auto_copyright_check_enabled,
                    simple_checklist_completed,
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
        default_model: str | None = None,
        default_responses_model: str | None = None,
        default_size: str | None = None,
        default_quality: str | None = None,
        default_output_format: str | None = None,
        default_image_transport: str | None = None,
        logo_overlay_enabled: bool | None = None,
        auto_copyright_check_enabled: bool | None = None,
        simple_checklist_completed: bool | None = None,
        ui_mode: str | None = None,
    ) -> dict[str, Any]:
        if ui_mode is not None and ui_mode not in _UI_MODES:
            raise ValueError("ui_mode must be simple or professional")
        now = _now_text()
        values = {
            "user_id": user_id,
            "ui_mode": ui_mode,
            "default_model": default_model.strip()[:128] if default_model is not None else None,
            "default_responses_model": (
                default_responses_model.strip()[:128] if default_responses_model is not None else None
            ),
            "default_size": default_size.strip()[:64] if default_size is not None else None,
            "default_quality": default_quality.strip()[:64] if default_quality is not None else None,
            "default_output_format": (
                default_output_format.strip()[:64] if default_output_format is not None else None
            ),
            "default_image_transport": (
                default_image_transport.strip()[:64] if default_image_transport is not None else None
            ),
            "logo_overlay_enabled": None if logo_overlay_enabled is None else int(logo_overlay_enabled),
            "auto_copyright_check_enabled": (
                None if auto_copyright_check_enabled is None else int(auto_copyright_check_enabled)
            ),
            "simple_checklist_completed": (
                None if simple_checklist_completed is None else int(simple_checklist_completed)
            ),
            "updated_at": now,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (
                    user_id,
                    ui_mode,
                    default_model,
                    default_responses_model,
                    default_size,
                    default_quality,
                    default_output_format,
                    default_image_transport,
                    logo_overlay_enabled,
                    auto_copyright_check_enabled,
                    simple_checklist_completed,
                    updated_at
                )
                VALUES (
                    :user_id,
                    :ui_mode,
                    COALESCE(:default_model, ''),
                    COALESCE(:default_responses_model, ''),
                    COALESCE(:default_size, ''),
                    COALESCE(:default_quality, ''),
                    COALESCE(:default_output_format, ''),
                    COALESCE(:default_image_transport, ''),
                    COALESCE(:logo_overlay_enabled, 1),
                    COALESCE(:auto_copyright_check_enabled, 1),
                    COALESCE(:simple_checklist_completed, 0),
                    :updated_at
                )
                ON CONFLICT(user_id) DO UPDATE SET
                    ui_mode = COALESCE(:ui_mode, user_preferences.ui_mode),
                    default_model = COALESCE(:default_model, user_preferences.default_model),
                    default_responses_model = COALESCE(
                        :default_responses_model,
                        user_preferences.default_responses_model
                    ),
                    default_size = COALESCE(:default_size, user_preferences.default_size),
                    default_quality = COALESCE(:default_quality, user_preferences.default_quality),
                    default_output_format = COALESCE(
                        :default_output_format,
                        user_preferences.default_output_format
                    ),
                    default_image_transport = COALESCE(
                        :default_image_transport,
                        user_preferences.default_image_transport
                    ),
                    logo_overlay_enabled = COALESCE(
                        :logo_overlay_enabled,
                        user_preferences.logo_overlay_enabled
                    ),
                    auto_copyright_check_enabled = COALESCE(
                        :auto_copyright_check_enabled,
                        user_preferences.auto_copyright_check_enabled
                    ),
                    simple_checklist_completed = COALESCE(
                        :simple_checklist_completed,
                        user_preferences.simple_checklist_completed
                    ),
                    updated_at = excluded.updated_at
                """,
                values,
            )
            row = conn.execute(
                """
                SELECT
                    ui_mode,
                    default_model,
                    default_responses_model,
                    default_size,
                    default_quality,
                    default_output_format,
                    default_image_transport,
                    logo_overlay_enabled,
                    auto_copyright_check_enabled,
                    simple_checklist_completed,
                    updated_at
                FROM user_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:  # pragma: no cover - the upsert above guarantees a row
            raise RuntimeError("preferences were not saved")
        return _user_preferences_from_row(user_id, row)

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
            if normalized_rating == "good" and generated_image_id is not None:
                _upsert_group_saved_item_for_image(
                    conn,
                    user_id=user_id,
                    generated_image_id=generated_image_id,
                    title=(clean_reason or "满意作品")[:160],
                    note=clean_reason,
                    fallback_prompt=clean_prompt,
                    fallback_mode=clean_mode,
                    fallback_model=clean_model,
                    fallback_path=clean_path,
                    fallback_url=clean_url,
                    now=now,
                )
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

    def get_group_announcement(self, *, user_id: int) -> dict[str, Any] | None:
        group = self.team_chat_group_for_user(user_id)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    a.id,
                    a.room_key,
                    a.company,
                    a.department,
                    a.content,
                    a.created_by_user_id,
                    creator.username AS created_by_username,
                    a.updated_by_user_id,
                    updater.username AS updated_by_username,
                    a.created_at,
                    a.updated_at
                FROM group_announcements a
                LEFT JOIN users creator ON creator.id = a.created_by_user_id
                LEFT JOIN users updater ON updater.id = a.updated_by_user_id
                WHERE a.room_key = ? AND a.content != ''
                """,
                (group["room_key"],),
            ).fetchone()
        return _group_announcement_row_to_dict(row) if row is not None else None

    def upsert_group_announcement(
        self,
        *,
        company: str,
        department: str,
        content: str,
        actor_user_id: int,
    ) -> dict[str, Any] | None:
        clean_company, clean_department = normalize_user_org(
            company,
            department,
            username_normalized="",
            role="user",
        )
        clean_content = content.strip()[:2000]
        now = _now_text()
        room_key = team_chat_group_room_key(clean_company, clean_department)
        with self._lock, self._connect() as conn:
            _require_active_org_unit(conn, clean_company, clean_department)
            existing = conn.execute(
                "SELECT id, created_by_user_id, created_at FROM group_announcements WHERE room_key = ?",
                (room_key,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO group_announcements (
                        room_key,
                        company,
                        department,
                        content,
                        created_by_user_id,
                        updated_by_user_id,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        room_key,
                        clean_company,
                        clean_department,
                        clean_content,
                        actor_user_id,
                        actor_user_id,
                        now,
                        now,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE group_announcements
                    SET
                        company = ?,
                        department = ?,
                        content = ?,
                        updated_by_user_id = ?,
                        updated_at = ?
                    WHERE room_key = ?
                    """,
                    (clean_company, clean_department, clean_content, actor_user_id, now, room_key),
                )
            row = conn.execute(
                """
                SELECT
                    a.id,
                    a.room_key,
                    a.company,
                    a.department,
                    a.content,
                    a.created_by_user_id,
                    creator.username AS created_by_username,
                    a.updated_by_user_id,
                    updater.username AS updated_by_username,
                    a.created_at,
                    a.updated_at
                FROM group_announcements a
                LEFT JOIN users creator ON creator.id = a.created_by_user_id
                LEFT JOIN users updater ON updater.id = a.updated_by_user_id
                WHERE a.room_key = ?
                """,
                (room_key,),
            ).fetchone()
        if row is None or not clean_content:
            return None
        return _group_announcement_row_to_dict(row)

    def list_group_saved_items(self, *, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        group = self.team_chat_group_for_user(user_id)
        bounded_limit = max(1, min(limit, 100))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    item.id,
                    item.room_key,
                    item.company,
                    item.department,
                    item.user_id,
                    u.username,
                    item.generated_image_id,
                    item.title,
                    item.note,
                    item.prompt,
                    item.mode,
                    item.model,
                    item.saved_image_path,
                    item.saved_image_url,
                    item.created_at
                FROM group_saved_items item
                LEFT JOIN users u ON u.id = item.user_id
                WHERE item.room_key = ?
                ORDER BY item.created_at DESC, item.id DESC
                LIMIT ?
                """,
                (group["room_key"], bounded_limit),
            ).fetchall()
        return [_group_saved_item_row_to_dict(row) for row in rows]

    def save_group_item(
        self,
        *,
        user_id: int,
        generated_image_id: int,
        title: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        now = _now_text()
        with self._lock, self._connect() as conn:
            asset_id = _upsert_group_saved_item_for_image(
                conn,
                user_id=user_id,
                generated_image_id=generated_image_id,
                title=title.strip()[:160] or "优秀作品",
                note=note.strip()[:1000],
                now=now,
            )
            row = conn.execute(
                """
                SELECT
                    item.id,
                    item.room_key,
                    item.company,
                    item.department,
                    item.user_id,
                    u.username,
                    item.generated_image_id,
                    item.title,
                    item.note,
                    item.prompt,
                    item.mode,
                    item.model,
                    item.saved_image_path,
                    item.saved_image_url,
                    item.created_at
                FROM group_saved_items item
                LEFT JOIN users u ON u.id = item.user_id
                WHERE item.id = ?
                """,
                (asset_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Group 资产保存失败")
        return _group_saved_item_row_to_dict(row)

    def group_stats(self, *, user_id: int) -> dict[str, Any]:
        group = self.team_chat_group_for_user(user_id)
        return self._group_stats_for_org(company=group["company"], department=group["department"])

    def organization_stats(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT company, department
                FROM organization_units
                WHERE is_active = 1
                ORDER BY company COLLATE NOCASE ASC, department COLLATE NOCASE ASC
                """
            ).fetchall()
        stats: list[dict[str, Any]] = []
        for row in rows:
            company = str(row["company"] or "")
            department = str(row["department"] or "")
            stats.append(self._group_stats_for_org(company=company, department=department))
        return stats

    def _group_stats_for_org(self, *, company: str, department: str) -> dict[str, Any]:
        room_key = team_chat_group_room_key(company, department)
        now = _now()
        active_after = _datetime_text(now - timedelta(days=30))
        with self._lock, self._connect() as conn:
            users_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS member_count,
                    COALESCE(SUM(CASE WHEN last_login_at >= ? THEN 1 ELSE 0 END), 0) AS active_user_count
                FROM users
                WHERE is_active = 1
                  AND role != 'admin'
                  AND company = ?
                  AND department = ?
                """,
                (active_after, company, department),
            ).fetchone()
            usage_row = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT j.id) AS job_count,
                    COUNT(gi.id) AS generated_image_count,
                    COALESCE(SUM(gi.saved_image_bytes), 0) AS saved_bytes
                FROM generation_jobs j
                LEFT JOIN generated_images gi ON gi.job_id = j.id
                JOIN users u ON u.id = j.user_id
                WHERE u.company = ? AND u.department = ?
                """,
                (company, department),
            ).fetchone()
            feedback_rows = conn.execute(
                """
                SELECT f.rating, COUNT(*) AS count
                FROM result_feedback f
                JOIN users u ON u.id = f.user_id
                WHERE u.company = ? AND u.department = ?
                GROUP BY f.rating
                """,
                (company, department),
            ).fetchall()
            chat_row = conn.execute(
                "SELECT COUNT(*) AS message_count FROM team_chat_messages WHERE room_key = ?",
                (room_key,),
            ).fetchone()
            asset_row = conn.execute(
                "SELECT COUNT(*) AS asset_count FROM group_saved_items WHERE room_key = ?",
                (room_key,),
            ).fetchone()
        return _group_stats_payload(
            company=company,
            department=department,
            room_key=room_key,
            users_row=users_row,
            usage_row=usage_row,
            feedback_rows=feedback_rows,
            chat_row=chat_row,
            asset_row=asset_row,
        )

    def group_summary(self, *, user_id: int, days: int = 7) -> dict[str, Any]:
        bounded_days = max(1, min(int(days or 7), 31))
        group = self.team_chat_group_for_user(user_id)
        since = _datetime_text(_now() - timedelta(days=bounded_days))
        with self._lock, self._connect() as conn:
            prompt_rows = conn.execute(
                """
                SELECT gi.prompt, COUNT(*) AS count
                FROM generated_images gi
                JOIN users u ON u.id = gi.user_id
                WHERE u.company = ?
                  AND u.department = ?
                  AND gi.created_at >= ?
                  AND gi.prompt != ''
                GROUP BY gi.prompt
                ORDER BY count DESC, MAX(gi.created_at) DESC
                LIMIT 5
                """,
                (group["company"], group["department"], since),
            ).fetchall()
            feedback_rows = conn.execute(
                """
                SELECT f.rating, COUNT(*) AS count
                FROM result_feedback f
                JOIN users u ON u.id = f.user_id
                WHERE u.company = ?
                  AND u.department = ?
                  AND f.created_at >= ?
                GROUP BY f.rating
                """,
                (group["company"], group["department"], since),
            ).fetchall()
            image_row = conn.execute(
                """
                SELECT COUNT(gi.id) AS image_count
                FROM generated_images gi
                JOIN users u ON u.id = gi.user_id
                WHERE u.company = ?
                  AND u.department = ?
                  AND gi.created_at >= ?
                """,
                (group["company"], group["department"], since),
            ).fetchone()
            asset_row = conn.execute(
                """
                SELECT COUNT(*) AS asset_count
                FROM group_saved_items
                WHERE room_key = ? AND created_at >= ?
                """,
                (group["room_key"], since),
            ).fetchone()
        totals = {"good": 0, "ok": 0, "bad": 0}
        for row in feedback_rows:
            rating = str(row["rating"] or "")
            if rating in totals:
                totals[rating] = int(row["count"] or 0)
        prompts: list[dict[str, Any]] = [
            {"prompt": str(row["prompt"] or ""), "count": int(row["count"] or 0)}
            for row in prompt_rows
        ]
        title = f"{group['company'] or '未分配公司'} · {group['department'] or '未分配部门'}"
        image_count = int(image_row["image_count"] or 0) if image_row is not None else 0
        asset_count = int(asset_row["asset_count"] or 0) if asset_row is not None else 0
        if prompts:
            prompt_line = "；".join(
                f"{str(item['prompt'])[:48]}（{int(item['count'])}次）"
                for item in prompts[:3]
            )
        else:
            prompt_line = "暂无高频提示词"
        text = (
            f"{title} 最近 {bounded_days} 天：生成 {image_count} 张图，"
            f"满意 {totals['good']}，一般 {totals['ok']}，不好 {totals['bad']}，"
            f"沉淀优秀资产 {asset_count} 个。高频提示词：{prompt_line}。"
        )
        return {
            "group": {
                "company": group["company"],
                "department": group["department"],
                "room_key": group["room_key"],
                "title": title,
            },
            "days": bounded_days,
            "since": since,
            "image_count": image_count,
            "asset_count": asset_count,
            "feedback": totals,
            "top_prompts": prompts,
            "text": text,
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
                    u.company,
                    u.department,
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
                "company": str(row["company"] or ""),
                "department": str(row["department"] or ""),
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

    def image_count_stats(self, *, user_id: int) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            current_user_count = conn.execute(
                """
                SELECT COUNT(id)
                FROM generated_images
                WHERE user_id = ?
                  AND saved_image_url != ''
                  AND asset_kind = 'result'
                """,
                (user_id,),
            ).fetchone()[0]
            platform_count = conn.execute(
                """
                SELECT COUNT(id)
                FROM generated_images
                WHERE saved_image_url != ''
                  AND asset_kind = 'result'
                """,
            ).fetchone()[0]
        return {
            "current_user_generated_image_count": int(current_user_count or 0),
            "platform_generated_image_count": int(platform_count or 0),
        }

    def list_active_users(self, *, exclude_user_id: int | None = None) -> list[dict[str, Any]]:
        where_clause = "WHERE is_active = 1"
        params: tuple[Any, ...] = ()
        if exclude_user_id is not None:
            where_clause = "WHERE is_active = 1 AND id != ?"
            params = (exclude_user_id,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    username,
                    display_name,
                    avatar_url,
                    role,
                    is_active,
                    company,
                    department,
                    created_at,
                    last_login_at
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
                "display_name": str(row["display_name"] or ""),
                "avatar_url": str(row["avatar_url"] or ""),
                "role": str(row["role"]),
                "is_admin": str(row["role"]) == "admin",
                "is_active": bool(row["is_active"]),
                "company": str(row["company"] or ""),
                "department": str(row["department"] or ""),
                "created_at": str(row["created_at"]),
                "last_login_at": row["last_login_at"],
            }
            for row in rows
        ]

    def list_team_chat_members(self, *, current_user_id: int) -> list[dict[str, Any]]:
        group = self.team_chat_group_for_user(current_user_id)
        current_username = group["username_normalized"]
        current_company = group["company"]
        current_department = group["department"]
        if not current_company and not current_department:
            rows: list[sqlite3.Row] = []
        else:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                """
                SELECT id, username, username_normalized, display_name, avatar_url, company, department
                FROM users
                WHERE is_active = 1
                  AND role != 'admin'
                  AND id != ?
                  AND company = ?
                  AND department = ?
                ORDER BY username COLLATE NOCASE ASC
                """,
                (current_user_id, current_company, current_department),
                ).fetchall()

        include_minorli = current_username == "minorli"
        members: list[dict[str, Any]] = [
            {
                "id": TEAM_CHAT_BOT_ID,
                "type": "bot",
                "username": TEAM_CHAT_BOT_NAME,
                "display_name": TEAM_CHAT_BOT_NAME,
                "avatar_url": "",
                "company": current_company,
                "department": current_department,
            }
        ]
        for row in rows:
            normalized = str(row["username_normalized"] or "")
            if normalized == "minorli" and not include_minorli:
                continue
            members.append(
                {
                    "id": int(row["id"]),
                    "type": "user",
                    "username": str(row["username"]),
                    "display_name": str(row["display_name"] or ""),
                    "avatar_url": str(row["avatar_url"] or ""),
                    "company": str(row["company"] or ""),
                    "department": str(row["department"] or ""),
                }
            )
        return members

    def team_chat_group_for_user(self, user_id: int) -> dict[str, str]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username_normalized, role, company, department
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            company = ""
            department = ""
            username_normalized = ""
        else:
            group = _team_chat_group_from_user_row(row)
            company = group["company"]
            department = group["department"]
            room_key = group["room_key"]
            username_normalized = str(row["username_normalized"] or "")
        if row is None:
            room_key = f"team:unassigned:{user_id}"
        return {
            "company": company,
            "department": department,
            "room_key": room_key,
            "username_normalized": username_normalized,
        }

    def team_chat_room_key(
        self,
        *,
        current_user_id: int,
        room_type: str,
        recipient_user_id: int | None = None,
    ) -> str:
        normalized_room_type = normalize_team_chat_room_type(room_type)
        if normalized_room_type == "team":
            return self.team_chat_group_for_user(current_user_id)["room_key"]
        if normalized_room_type == "bot":
            return f"bot:{current_user_id}"
        if recipient_user_id is None or recipient_user_id <= 0 or recipient_user_id == current_user_id:
            raise ValueError("请选择聊天对象")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, role, is_active
                FROM users
                WHERE id = ?
                """,
                (recipient_user_id,),
            ).fetchone()
        if row is None or not bool(row["is_active"]) or str(row["role"]) == "admin":
            raise ValueError("聊天对象不存在或已停用")
        low, high = sorted((current_user_id, recipient_user_id))
        return f"dm:{low}:{high}"

    def create_team_chat_message(
        self,
        *,
        room_key: str,
        room_type: str,
        sender_user_id: int | None,
        sender_type: str,
        sender_name: str,
        content: str,
        mentions: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_content = content.strip()[:4000]
        if not clean_content:
            raise ValueError("消息不能为空")
        clean_sender_type = normalize_team_chat_sender_type(sender_type)
        clean_room_type = normalize_team_chat_room_type(room_type)
        clean_mentions = [_truncate_text(item.strip(), 80) for item in mentions or [] if item.strip()]
        now = _now_text()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO team_chat_messages (
                    room_key,
                    room_type,
                    sender_user_id,
                    sender_type,
                    sender_name,
                    content,
                    mentions_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room_key.strip()[:128],
                    clean_room_type,
                    sender_user_id,
                    clean_sender_type,
                    sender_name.strip()[:120],
                    clean_content,
                    json.dumps(clean_mentions, ensure_ascii=False),
                    now,
                ),
            )
            message_id = _require_lastrowid(cursor)
            row = conn.execute(
                """
                SELECT *
                FROM team_chat_messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("team chat message insert failed")
        return _team_chat_message_row_to_dict(row)

    def list_team_chat_messages(
        self,
        *,
        room_key: str,
        limit: int = 100,
        after_id: int = 0,
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 200))
        bounded_after_id = max(0, int(after_id or 0))
        with self._lock, self._connect() as conn:
            if bounded_after_id > 0:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM team_chat_messages
                    WHERE room_key = ?
                      AND id > ?
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (room_key.strip()[:128], bounded_after_id, bounded_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM (
                        SELECT *
                        FROM team_chat_messages
                        WHERE room_key = ?
                        ORDER BY id DESC
                        LIMIT ?
                    )
                    ORDER BY id ASC
                    """,
                    (room_key.strip()[:128], bounded_limit),
                ).fetchall()
        return [_team_chat_message_row_to_dict(row) for row in rows]

    def mark_team_chat_read(self, *, user_id: int, room_key: str, message_id: int) -> dict[str, Any]:
        bounded_message_id = max(0, int(message_id or 0))
        now = _now_text()
        with self._lock, self._connect() as conn:
            current = conn.execute(
                """
                SELECT last_read_message_id
                FROM team_chat_reads
                WHERE user_id = ? AND room_key = ?
                """,
                (user_id, room_key),
            ).fetchone()
            last_read_message_id = max(
                bounded_message_id,
                int(current["last_read_message_id"] or 0) if current is not None else 0,
            )
            conn.execute(
                """
                INSERT INTO team_chat_reads (user_id, room_key, last_read_message_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, room_key) DO UPDATE SET
                    last_read_message_id = MAX(team_chat_reads.last_read_message_id, excluded.last_read_message_id),
                    updated_at = excluded.updated_at
                """,
                (user_id, room_key.strip()[:128], last_read_message_id, now),
            )
        return {
            "room_key": room_key.strip()[:128],
            "last_read_message_id": last_read_message_id,
            "updated_at": now,
        }

    def team_chat_unread_summary(self, *, user_id: int) -> dict[str, Any]:
        group_room_key = self.team_chat_group_for_user(user_id)["room_key"]
        accessible_prefixes = [f"dm:{user_id}:", f"bot:{user_id}"]
        accessible_dm_suffix = f":{user_id}"
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    m.room_key,
                    COUNT(*) AS unread_count,
                    MAX(m.id) AS latest_message_id
                FROM team_chat_messages m
                LEFT JOIN team_chat_reads r
                  ON r.user_id = ? AND r.room_key = m.room_key
                WHERE m.id > COALESCE(r.last_read_message_id, 0)
                  AND COALESCE(m.sender_user_id, -1) != ?
                  AND (
                    m.room_key = ?
                    OR m.room_key = ?
                    OR m.room_key LIKE ?
                    OR m.room_key LIKE ?
                  )
                GROUP BY m.room_key
                """,
                (
                    user_id,
                    user_id,
                    group_room_key,
                    accessible_prefixes[1],
                    accessible_prefixes[0] + "%",
                    "dm:%" + accessible_dm_suffix,
                ),
            ).fetchall()
        rooms = {str(row["room_key"]): int(row["unread_count"] or 0) for row in rows}
        latest = {
            str(row["room_key"]): int(row["latest_message_id"] or 0)
            for row in rows
            if row["latest_message_id"]
        }
        return {
            "total": sum(rooms.values()),
            "rooms": rooms,
            "latest_message_ids": latest,
        }

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

    def list_success_templates_for_user(self, *, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit or 20), 60))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    f.id,
                    f.generated_image_id,
                    f.reason,
                    f.prompt,
                    f.mode,
                    f.model,
                    f.saved_image_url,
                    f.created_at
                FROM result_feedback f
                WHERE f.user_id = ?
                  AND f.rating = 'good'
                  AND f.prompt != ''
                ORDER BY f.created_at DESC, f.id DESC
                LIMIT ?
                """,
                (user_id, bounded_limit * 3),
            ).fetchall()
        templates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            prompt = str(row["prompt"] or "").strip()
            normalized = " ".join(prompt.casefold().split())
            if not prompt or normalized in seen:
                continue
            seen.add(normalized)
            title = str(row["reason"] or "").strip() or _success_template_title(prompt)
            templates.append(
                {
                    "id": int(row["id"]),
                    "source": "good_feedback",
                    "generated_image_id": int(row["generated_image_id"]) if row["generated_image_id"] else None,
                    "title": title[:160],
                    "prompt": prompt,
                    "mode": str(row["mode"] or ""),
                    "model": str(row["model"] or ""),
                    "saved_image_url": str(row["saved_image_url"] or ""),
                    "created_at": str(row["created_at"] or ""),
                }
            )
            if len(templates) >= bounded_limit:
                break
        return templates

    def record_bug_report(
        self,
        *,
        user_id: int,
        title: str,
        description: str,
        contact: str = "",
        page_url: str = "",
        user_agent: str = "",
        notification_status: str = "not_configured",
    ) -> dict[str, Any]:
        clean_description = description.strip()[:4000]
        if not clean_description:
            raise ValueError("问题描述不能为空")
        clean_title = title.strip()[:160] or clean_description[:80]
        clean_contact = contact.strip()[:256]
        clean_page_url = page_url.strip()[:1024]
        clean_user_agent = user_agent.strip()[:512]
        clean_notification_status = notification_status.strip()[:64] or "not_configured"
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
                VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    user_id,
                    clean_title,
                    clean_description,
                    clean_contact,
                    clean_page_url,
                    clean_user_agent,
                    clean_notification_status,
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
            "notification_status": clean_notification_status,
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
            image: sqlite3.Row | None
            if generated_image_id is not None:
                image = conn.execute(
                    """
                    SELECT
                        id,
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
            else:
                url_tokens = _clean_source_tokens(
                    [clean_url, clean_url.lstrip("/")],
                    max_length=1024,
                )
                path_tokens = _clean_source_tokens([clean_path], max_length=1024)
                clauses: list[str] = []
                image_params: list[Any] = [sender_user_id]
                if url_tokens:
                    url_placeholders = ",".join("?" for _ in url_tokens)
                    clauses.append(f"saved_image_url IN ({url_placeholders})")
                    image_params.extend(url_tokens)
                if path_tokens:
                    path_placeholders = ",".join("?" for _ in path_tokens)
                    clauses.append(f"saved_image_path IN ({path_placeholders})")
                    image_params.extend(path_tokens)
                image = conn.execute(
                    f"""
                    SELECT id, saved_image_path, saved_image_url, prompt, mode, model
                    FROM generated_images
                    WHERE user_id = ?
                      AND ({' OR '.join(clauses) if clauses else '0'})
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    tuple(image_params),
                ).fetchone()
            if image is None:
                raise PermissionError("无权分享这张图片")
            generated_image_id = int(image["id"])
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
    def _run_schema_migrations(conn: sqlite3.Connection) -> list[Path]:
        _ensure_columns(conn, "users", {
            "role": "TEXT NOT NULL DEFAULT 'user'",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "display_name": "TEXT NOT NULL DEFAULT ''",
            "real_name": "TEXT NOT NULL DEFAULT ''",
            "wechat": "TEXT NOT NULL DEFAULT ''",
            "phone_country_code": "TEXT NOT NULL DEFAULT '+86'",
            "phone": "TEXT NOT NULL DEFAULT ''",
            "email": "TEXT NOT NULL DEFAULT ''",
            "company": "TEXT NOT NULL DEFAULT ''",
            "department": "TEXT NOT NULL DEFAULT ''",
            "team": "TEXT NOT NULL DEFAULT ''",
            "job_title": "TEXT NOT NULL DEFAULT ''",
            "note": "TEXT NOT NULL DEFAULT ''",
            "avatar_path": "TEXT NOT NULL DEFAULT ''",
            "avatar_url": "TEXT NOT NULL DEFAULT ''",
            "created_source": "TEXT NOT NULL DEFAULT 'self_register'",
            "last_seen_at": "TEXT",
            "password_changed_at": "TEXT",
            "failed_login_count": "INTEGER NOT NULL DEFAULT 0",
            "locked_until": "TEXT",
            "disabled_reason": "TEXT NOT NULL DEFAULT ''",
        })
        _ensure_columns(conn, "password_reset_requests", {
            "token_hash": "TEXT",
            "email": "TEXT NOT NULL DEFAULT ''",
            "email_sent_at": "TEXT",
            "expires_at": "TEXT",
        })
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_password_reset_token_hash ON password_reset_requests(token_hash)"
        )
        _ensure_columns(conn, "result_feedback", {
            "generated_image_id": "INTEGER",
        })
        _ensure_columns(conn, "shared_results", {
            "generated_image_id": "INTEGER",
        })
        _ensure_columns(conn, "user_preferences", {
            "ui_mode": "TEXT CHECK (ui_mode IS NULL OR ui_mode IN ('simple', 'professional'))",
            "default_model": "TEXT NOT NULL DEFAULT ''",
            "default_responses_model": "TEXT NOT NULL DEFAULT ''",
            "default_size": "TEXT NOT NULL DEFAULT ''",
            "default_quality": "TEXT NOT NULL DEFAULT ''",
            "default_output_format": "TEXT NOT NULL DEFAULT ''",
            "default_image_transport": "TEXT NOT NULL DEFAULT ''",
            "logo_overlay_enabled": "INTEGER NOT NULL DEFAULT 1",
            "auto_copyright_check_enabled": "INTEGER NOT NULL DEFAULT 1",
            "simple_checklist_completed": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        })
        _ensure_columns(conn, "generation_jobs", {
            "original_prompt": "TEXT NOT NULL DEFAULT ''",
            "prompt_mode": "TEXT NOT NULL DEFAULT 'free'",
            "recipe_id": "TEXT NOT NULL DEFAULT ''",
            "recipe_version": "TEXT NOT NULL DEFAULT ''",
            "reasoning_effort": "TEXT NOT NULL DEFAULT ''",
        })
        _ensure_columns(conn, "generated_images", {
            "source_generated_image_id": "INTEGER",
            "asset_kind": "TEXT NOT NULL DEFAULT 'result'",
            "version_note": "TEXT NOT NULL DEFAULT ''",
        })
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_generated_images_source
            ON generated_images(source_generated_image_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_gallery_metadata_user_favorite
            ON gallery_image_metadata(user_id, is_favorite, updated_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_gallery_tags_user_tag
            ON gallery_image_tags(user_id, tag_normalized)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_gallery_tags_image
            ON gallery_image_tags(generated_image_id, user_id)
            """
        )
        _ensure_generated_image_metadata_table(conn)
        migrated_sidecar_paths = _migrate_legacy_image_sidecars(conn)
        conn.execute("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''")
        conn.execute("UPDATE users SET is_active = 1 WHERE is_active IS NULL")
        conn.execute(
            """
            UPDATE users
            SET phone_country_code = '+86'
            WHERE phone_country_code IS NULL OR phone_country_code = ''
            """
        )
        conn.execute(
            """
            UPDATE users
            SET company = '', department = ''
            WHERE role = 'admin' OR username_normalized IN ('admin', 'minorli')
            """
        )
        now = _now_text()
        share_migration_applied = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (_SHARED_RESULT_OWNERSHIP_SCHEMA_VERSION,),
        ).fetchone()
        if share_migration_applied is None:
            conn.execute(
                """
                UPDATE shared_results AS share
                SET generated_image_id = (
                    SELECT gi.id
                    FROM generated_images gi
                    WHERE gi.user_id = share.sender_user_id
                      AND (
                        (
                            TRIM(share.saved_image_path) != ''
                            AND gi.saved_image_path = share.saved_image_path
                        )
                        OR (
                            TRIM(share.saved_image_url) != ''
                            AND LTRIM(gi.saved_image_url, '/') = LTRIM(share.saved_image_url, '/')
                        )
                      )
                    ORDER BY gi.id DESC
                    LIMIT 1
                )
                WHERE share.generated_image_id IS NULL
                """
            )
            conn.execute(
                """
                UPDATE shared_results AS share
                SET
                    saved_image_path = (
                        SELECT gi.saved_image_path
                        FROM generated_images gi
                        WHERE gi.id = share.generated_image_id
                          AND gi.user_id = share.sender_user_id
                    ),
                    saved_image_url = (
                        SELECT gi.saved_image_url
                        FROM generated_images gi
                        WHERE gi.id = share.generated_image_id
                          AND gi.user_id = share.sender_user_id
                    ),
                    prompt = (
                        SELECT gi.prompt
                        FROM generated_images gi
                        WHERE gi.id = share.generated_image_id
                          AND gi.user_id = share.sender_user_id
                    ),
                    mode = (
                        SELECT gi.mode
                        FROM generated_images gi
                        WHERE gi.id = share.generated_image_id
                          AND gi.user_id = share.sender_user_id
                    ),
                    model = (
                        SELECT gi.model
                        FROM generated_images gi
                        WHERE gi.id = share.generated_image_id
                          AND gi.user_id = share.sender_user_id
                    )
                WHERE EXISTS (
                    SELECT 1
                    FROM generated_images gi
                    WHERE gi.id = share.generated_image_id
                      AND gi.user_id = share.sender_user_id
                )
                """
            )
            conn.execute(
                """
                DELETE FROM shared_results
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM generated_images gi
                    WHERE gi.id = shared_results.generated_image_id
                      AND gi.user_id = shared_results.sender_user_id
                )
                """
            )
            conn.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (?, 'shared_result_image_ownership', ?)
                """,
                (_SHARED_RESULT_OWNERSHIP_SCHEMA_VERSION, now),
            )
        model_migration_applied = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (13,),
        ).fetchone()
        if model_migration_applied is None:
            conn.execute(
                """
                UPDATE user_preferences
                SET default_responses_model = ?, updated_at = ?
                WHERE default_responses_model = ?
                """,
                (DEFAULT_RESPONSES_MODEL, now, LEGACY_DEFAULT_RESPONSES_MODEL),
            )
            conn.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (13, 'image_job_execution_metadata', ?)
                """,
                (now,),
            )
        for company, department in DEFAULT_ORG_UNITS:
            conn.execute(
                """
                INSERT INTO organization_units (company, department, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(company, department) DO UPDATE SET
                    is_active = 1,
                    updated_at = CASE
                        WHEN organization_units.updated_at = '' THEN excluded.updated_at
                        ELSE organization_units.updated_at
                    END
                """,
                (company, department, now, now),
            )
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (14, "simple_checklist_preference", now),
        )
        return migrated_sidecar_paths

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


def normalize_team_chat_room_type(room_type: str) -> str:
    normalized = room_type.strip().lower()
    if normalized not in {"team", "dm", "bot"}:
        raise ValueError("聊天房间类型无效")
    return normalized


def normalize_team_chat_sender_type(sender_type: str) -> str:
    normalized = sender_type.strip().lower()
    if normalized not in {"user", "bot"}:
        raise ValueError("消息发送者类型无效")
    return normalized


def _truncate_text(value: str, max_length: int) -> str:
    return value[: max(0, max_length)]


def _team_chat_message_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    mentions: list[str] = []
    raw_mentions = str(row["mentions_json"] or "[]")
    try:
        parsed = json.loads(raw_mentions)
        if isinstance(parsed, list):
            mentions = [str(item) for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        mentions = []
    return {
        "id": int(row["id"]),
        "room_key": str(row["room_key"]),
        "room_type": str(row["room_type"] or "team"),
        "sender_user_id": int(row["sender_user_id"]) if row["sender_user_id"] is not None else None,
        "sender_type": str(row["sender_type"] or "user"),
        "sender_name": str(row["sender_name"] or ""),
        "content": str(row["content"] or ""),
        "mentions": mentions,
        "created_at": str(row["created_at"]),
    }


def _organization_unit_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "company": str(row["company"] or ""),
        "department": str(row["department"] or ""),
        "is_active": bool(row["is_active"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _organization_audit_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "actor_user_id": int(row["actor_user_id"]) if row["actor_user_id"] is not None else None,
        "actor_username": str(row["actor_username"] or ""),
        "target_user_id": int(row["target_user_id"]),
        "target_username": str(row["target_username"] or ""),
        "old_company": str(row["old_company"] or ""),
        "old_department": str(row["old_department"] or ""),
        "new_company": str(row["new_company"] or ""),
        "new_department": str(row["new_department"] or ""),
        "reason": str(row["reason"] or ""),
        "created_at": str(row["created_at"]),
    }


def _group_announcement_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "room_key": str(row["room_key"] or ""),
        "company": str(row["company"] or ""),
        "department": str(row["department"] or ""),
        "content": str(row["content"] or ""),
        "created_by_user_id": int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
        "created_by_username": str(row["created_by_username"] or ""),
        "updated_by_user_id": int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
        "updated_by_username": str(row["updated_by_username"] or ""),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _group_saved_item_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "room_key": str(row["room_key"] or ""),
        "company": str(row["company"] or ""),
        "department": str(row["department"] or ""),
        "user_id": int(row["user_id"]) if row["user_id"] is not None else None,
        "username": str(row["username"] or ""),
        "generated_image_id": int(row["generated_image_id"]) if row["generated_image_id"] is not None else None,
        "title": str(row["title"] or ""),
        "note": str(row["note"] or ""),
        "prompt": str(row["prompt"] or ""),
        "mode": str(row["mode"] or ""),
        "model": str(row["model"] or ""),
        "saved_image_path": str(row["saved_image_path"] or ""),
        "saved_image_url": str(row["saved_image_url"] or ""),
        "created_at": str(row["created_at"]),
    }


def _upsert_group_saved_item_for_image(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    generated_image_id: int,
    title: str,
    note: str,
    fallback_prompt: str = "",
    fallback_mode: str = "",
    fallback_model: str = "",
    fallback_path: str = "",
    fallback_url: str = "",
    now: str | None = None,
) -> int:
    image = conn.execute(
        """
        SELECT
            id,
            user_id,
            mode,
            model,
            prompt,
            saved_image_path,
            saved_image_url
        FROM generated_images
        WHERE id = ? AND user_id = ?
        """,
        (generated_image_id, user_id),
    ).fetchone()
    if image is None:
        raise PermissionError("无权沉淀这张图片")
    user_row = conn.execute(
        """
        SELECT id, username_normalized, role, company, department
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    if user_row is None:
        raise PermissionError("用户不存在")
    group = _team_chat_group_from_user_row(user_row)
    saved_at = now or _now_text()
    clean_title = title.strip()[:160] or "优秀作品"
    clean_note = note.strip()[:1000]
    asset_values = (
        clean_title,
        clean_note,
        str(image["prompt"] or fallback_prompt)[:32_000],
        str(image["mode"] or fallback_mode)[:64],
        str(image["model"] or fallback_model)[:128],
        str(image["saved_image_path"] or fallback_path)[:1024],
        str(image["saved_image_url"] or fallback_url)[:1024],
    )
    existing_asset = conn.execute(
        """
        SELECT id
        FROM group_saved_items
        WHERE room_key = ? AND generated_image_id = ?
        """,
        (group["room_key"], generated_image_id),
    ).fetchone()
    if existing_asset is None:
        cursor = conn.execute(
            """
            INSERT INTO group_saved_items (
                room_key,
                company,
                department,
                user_id,
                generated_image_id,
                title,
                note,
                prompt,
                mode,
                model,
                saved_image_path,
                saved_image_url,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group["room_key"],
                group["company"],
                group["department"],
                user_id,
                generated_image_id,
                *asset_values,
                saved_at,
            ),
        )
        return _require_lastrowid(cursor)
    asset_id = int(existing_asset["id"])
    conn.execute(
        """
        UPDATE group_saved_items
        SET
            title = ?,
            note = ?,
            prompt = ?,
            mode = ?,
            model = ?,
            saved_image_path = ?,
            saved_image_url = ?
        WHERE id = ?
        """,
        (*asset_values, asset_id),
    )
    return asset_id


def _group_stats_payload(
    *,
    company: str,
    department: str,
    room_key: str,
    users_row: sqlite3.Row | None,
    usage_row: sqlite3.Row | None,
    feedback_rows: list[sqlite3.Row],
    chat_row: sqlite3.Row | None,
    asset_row: sqlite3.Row | None,
) -> dict[str, Any]:
    totals = {"good": 0, "ok": 0, "bad": 0}
    for row in feedback_rows:
        rating = str(row["rating"] or "")
        if rating in totals:
            totals[rating] = int(row["count"] or 0)
    return {
        "group": {
            "company": company,
            "department": department,
            "room_key": room_key,
            "title": f"{company or '未分配公司'} · {department or '未分配部门'}",
        },
        "users": {
            "member_count": int(users_row["member_count"] or 0) if users_row is not None else 0,
            "active_user_count": int(users_row["active_user_count"] or 0) if users_row is not None else 0,
        },
        "usage": {
            "job_count": int(usage_row["job_count"] or 0) if usage_row is not None else 0,
            "generated_image_count": int(usage_row["generated_image_count"] or 0) if usage_row is not None else 0,
            "saved_bytes": int(usage_row["saved_bytes"] or 0) if usage_row is not None else 0,
        },
        "feedback": {
            "totals": totals,
            "total_count": sum(totals.values()),
        },
        "chat": {
            "message_count": int(chat_row["message_count"] or 0) if chat_row is not None else 0,
        },
        "assets": {
            "asset_count": int(asset_row["asset_count"] or 0) if asset_row is not None else 0,
        },
    }


def _team_chat_group_from_user_row(row: sqlite3.Row) -> dict[str, str]:
    if str(row["role"] or "user") == "admin":
        company = ""
        department = ""
    else:
        company, department = normalize_user_org(
            str(row["company"] or ""),
            str(row["department"] or ""),
            username_normalized=str(row["username_normalized"] or ""),
            role=str(row["role"] or "user"),
        )
    room_key = team_chat_group_room_key(company, department)
    if not company and not department and "id" in set(row.keys()):
        room_key = f"team:unassigned:{int(row['id'])}"
    return {
        "company": company,
        "department": department,
        "room_key": room_key,
    }


def _row_text(row: sqlite3.Row, name: str, default: str = "") -> str:
    try:
        value = row[name]
    except (KeyError, IndexError):
        return default
    if value is None:
        return default
    return str(value)


def _auth_user_from_values(
    *,
    user_id: int,
    username: str,
    created_at: str,
    last_login_at: str | None = None,
    role: str = "user",
    is_active: bool = True,
    display_name: str = "",
    wechat: str = "",
    phone_country_code: str = "+86",
    phone: str = "",
    email: str = "",
    company: str = DEFAULT_COMPANY,
    department: str = DEFAULT_DEPARTMENT,
    team: str = "",
    job_title: str = "",
    note: str = "",
    avatar_path: str = "",
    avatar_url: str = "",
) -> AuthUser:
    return AuthUser(
        id=user_id,
        username=username,
        created_at=created_at,
        last_login_at=last_login_at,
        role=role,
        is_active=is_active,
        display_name=display_name,
        wechat=wechat,
        phone_country_code=phone_country_code or "+86",
        phone=phone,
        email=email,
        company=company,
        department=department,
        team=team,
        job_title=job_title,
        note=note,
        avatar_path=avatar_path,
        avatar_url=avatar_url,
    )


def _auth_user_from_row(
    row: sqlite3.Row,
    *,
    username: str | None = None,
    last_login_at: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> AuthUser:
    return _auth_user_from_values(
        user_id=int(row["id"]),
        username=username if username is not None else str(row["username"]),
        created_at=str(row["created_at"]),
        last_login_at=last_login_at if last_login_at is not None else row["last_login_at"],
        role=role if role is not None else str(row["role"]),
        is_active=is_active if is_active is not None else bool(row["is_active"]),
        display_name=_row_text(row, "display_name"),
        wechat=_row_text(row, "wechat"),
        phone_country_code=_row_text(row, "phone_country_code", "+86") or "+86",
        phone=_row_text(row, "phone"),
        email=_row_text(row, "email"),
        company=_row_text(row, "company", DEFAULT_COMPANY),
        department=_row_text(row, "department", DEFAULT_DEPARTMENT),
        team=_row_text(row, "team"),
        job_title=_row_text(row, "job_title"),
        note=_row_text(row, "note"),
        avatar_path=_row_text(row, "avatar_path"),
        avatar_url=_row_text(row, "avatar_url"),
    )


def normalize_role(role: str) -> str:
    cleaned = role.strip().lower()
    if cleaned not in {"admin", "user"}:
        raise ValueError("未知用户角色")
    return cleaned


def normalize_org_unit(company: str, department: str) -> tuple[str, str]:
    clean_company = company.strip()[:120]
    clean_department = department.strip()[:120]
    if not clean_company:
        raise ValueError("公司不能为空")
    if not clean_department:
        raise ValueError("部门不能为空")
    return clean_company, clean_department


def normalize_user_org(
    company: str,
    department: str,
    *,
    username_normalized: str,
    role: str,
) -> tuple[str, str]:
    if normalize_role(role) == "admin" or username_normalized in SYSTEM_USERNAMES_WITHOUT_ORG:
        return "", ""
    if not company.strip() and not department.strip():
        return "", ""
    clean_company = company.strip()[:120] or DEFAULT_COMPANY
    clean_department = department.strip()[:120] or DEFAULT_DEPARTMENT
    return clean_company, clean_department


def _require_active_org_unit(conn: sqlite3.Connection, company: str, department: str) -> None:
    if not company.strip() and not department.strip():
        return
    row = conn.execute(
        """
        SELECT id
        FROM organization_units
        WHERE company = ? AND department = ? AND is_active = 1
        """,
        (company.strip(), department.strip()),
    ).fetchone()
    if row is None:
        raise ValueError("请选择已启用的公司/部门")


def team_chat_group_room_key(company: str, department: str) -> str:
    raw_company = company.strip()
    raw_department = department.strip()
    if not raw_company and not raw_department:
        return "team:unassigned"
    clean_company = raw_company or DEFAULT_COMPANY
    clean_department = raw_department or DEFAULT_DEPARTMENT
    digest = hashlib.sha256(f"{clean_company}\n{clean_department}".encode()).hexdigest()[:24]
    return f"team:{digest}"


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
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
                refreshed = {
                    str(row["name"])
                    for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if name not in refreshed:
                    raise
                existing = refreshed
            else:
                existing.add(name)


def _ensure_generated_image_metadata_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS generated_image_metadata (
            generated_image_id INTEGER PRIMARY KEY,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            migrated_from_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (generated_image_id) REFERENCES generated_images(id) ON DELETE CASCADE
        )
        """
    )


def _serialize_metadata_json(metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return "{}"
    try:
        return json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return "{}"


def _upsert_generated_image_metadata(
    conn: sqlite3.Connection,
    *,
    generated_image_id: int,
    metadata: Any,
    migrated_from_path: str,
    now: str,
) -> None:
    existing = conn.execute(
        "SELECT metadata_json FROM generated_image_metadata WHERE generated_image_id = ?",
        (generated_image_id,),
    ).fetchone()
    merged_metadata: dict[str, Any] = {}
    if existing is not None:
        with suppress(json.JSONDecodeError):
            parsed = json.loads(str(existing["metadata_json"] or "{}"))
            if isinstance(parsed, dict):
                merged_metadata = parsed
    if isinstance(metadata, dict):
        merged_metadata = {**merged_metadata, **metadata}
    metadata_json = _serialize_metadata_json(merged_metadata)
    if metadata_json == "{}" and not migrated_from_path:
        return
    conn.execute(
        """
        INSERT INTO generated_image_metadata (
            generated_image_id,
            metadata_json,
            migrated_from_path,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(generated_image_id) DO UPDATE SET
            metadata_json = excluded.metadata_json,
            migrated_from_path = CASE
                WHEN excluded.migrated_from_path != '' THEN excluded.migrated_from_path
                ELSE generated_image_metadata.migrated_from_path
            END,
            updated_at = excluded.updated_at
        """,
        (
            generated_image_id,
            metadata_json,
            migrated_from_path.strip()[:1024],
            now,
            now,
        ),
    )


def _is_registered_sidecar_for_image(*, metadata_path: Path, image_path: Path) -> bool:
    try:
        metadata_path = metadata_path.resolve(strict=False)
        image_path = image_path.resolve(strict=False)
    except OSError:
        return False
    return (
        metadata_path.suffix.lower() == ".json"
        and image_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        and metadata_path.parent == image_path.parent
        and metadata_path.stem == image_path.stem
    )


def _migrate_legacy_image_sidecars(conn: sqlite3.Connection) -> list[Path]:
    """Copy legacy sidecar JSON into the DB; return the file paths to delete
    once the caller's transaction has committed."""

    _ensure_generated_image_metadata_table(conn)
    rows = conn.execute(
        """
        SELECT
            gi.id,
            gi.saved_image_path,
            gi.saved_metadata_path
        FROM generated_images gi
        LEFT JOIN generated_image_metadata gim
            ON gim.generated_image_id = gi.id
        WHERE gi.saved_metadata_path != ''
          AND gim.generated_image_id IS NULL
        """
    ).fetchall()
    migrated_paths: list[Path] = []
    now = _now_text()
    for row in rows:
        metadata_path = Path(str(row["saved_metadata_path"] or ""))
        image_path = Path(str(row["saved_image_path"] or ""))
        if not _is_registered_sidecar_for_image(metadata_path=metadata_path, image_path=image_path):
            continue
        if not metadata_path.is_file():
            continue
        try:
            parsed = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        _upsert_generated_image_metadata(
            conn,
            generated_image_id=int(row["id"]),
            metadata=parsed,
            migrated_from_path=str(metadata_path),
            now=now,
        )
        migrated_paths.append(metadata_path)
    return migrated_paths


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validated_source_generated_image_id(
    conn: sqlite3.Connection,
    *,
    source_id: Any,
    user_id: int | None,
) -> int | None:
    parsed = _optional_int(source_id)
    if parsed is None or parsed <= 0 or user_id is None:
        return None
    row = conn.execute(
        "SELECT id FROM generated_images WHERE id = ? AND user_id = ?",
        (parsed, user_id),
    ).fetchone()
    return parsed if row is not None else None


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
    row_keys = set(row.keys())
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
        "source_generated_image_id": (
            int(row["source_generated_image_id"])
            if "source_generated_image_id" in row_keys and row["source_generated_image_id"] is not None
            else None
        ),
        "asset_kind": str(row["asset_kind"] or "result") if "asset_kind" in row_keys else "result",
        "version_note": str(row["version_note"] or "") if "version_note" in row_keys else "",
        "created_at": str(row["created_at"]),
    }


def _clean_source_tokens(values: list[str], *, max_length: int) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()[:max_length]
        if not token or token in seen:
            continue
        cleaned.append(token)
        seen.add(token)
    return cleaned[:20]


def _output_reference_tokens(*, relative_path: str, absolute_path: Path) -> tuple[str, ...]:
    cleaned = relative_path.strip().lstrip("/")[:1024]
    if not cleaned.startswith("outputs/"):
        return ()
    file_url = f"files/{cleaned}"
    try:
        absolute = str(absolute_path.resolve(strict=False))[:1024]
    except OSError:
        absolute = str(absolute_path)[:1024]
    return tuple(
        dict.fromkeys(
            (
                cleaned,
                f"/{cleaned}",
                file_url,
                f"/{file_url}",
                absolute,
            )
        )
    )


def _attach_original_source_fields(item: dict[str, Any], metadata: dict[str, Any]) -> None:
    source_url = str(metadata.get("source_saved_image_url") or "").strip()[:1024]
    source_path = str(
        metadata.get("source_saved_image_path")
        or metadata.get("source_image_path")
        or ""
    ).strip()[:1024]
    item["original_saved_image_url"] = source_url
    item["original_saved_image_path"] = source_path


def _image_lineage_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "request_id": str(row["request_id"] or ""),
        "endpoint_path": str(row["endpoint_path"] or ""),
        "transport": str(row["transport"] or ""),
        "prompt_mode": str(row["prompt_mode"] or "free"),
        "original_prompt": str(row["original_prompt"] or row["effective_prompt"] or ""),
        "effective_prompt": str(row["effective_prompt"] or row["prompt"] or ""),
        "recipe_id": str(row["recipe_id"] or ""),
        "recipe_version": str(row["recipe_version"] or ""),
        "status": str(row["status"] or ""),
        "sample_count": max(1, int(row["sample_count"] or 1)),
        "started_at": str(row["started_at"] or ""),
        "completed_at": str(row["completed_at"] or ""),
        "elapsed_ms": float(row["elapsed_ms"]) if row["elapsed_ms"] is not None else None,
    }


def _version_image_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = _generated_image_row_to_dict(row)
    item["lineage"] = _image_lineage_from_row(row)
    try:
        parsed = json.loads(str(row["metadata_json"] or "{}"))
        item["metadata"] = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        item["metadata"] = {}
    _attach_original_source_fields(item, item["metadata"])
    return item


def _generation_job_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    row_keys = set(row.keys())
    return {
        "id": int(row["id"]),
        "generation_job_id": int(row["id"]),
        "request_id": str(row["request_id"] or ""),
        "user_id": int(row["user_id"]) if row["user_id"] is not None else None,
        "username": str(row["username"] or ""),
        "endpoint_path": str(row["endpoint_path"] or ""),
        "mode": str(row["mode"] or ""),
        "transport": str(row["transport"] or ""),
        "reasoning_effort": str(row["reasoning_effort"] or ""),
        "status": str(row["status"] or ""),
        "prompt": str(row["prompt"] or ""),
        "original_prompt": str(row["original_prompt"] or row["prompt"] or ""),
        "prompt_mode": str(row["prompt_mode"] or "free"),
        "recipe_id": str(row["recipe_id"] or ""),
        "recipe_version": str(row["recipe_version"] or ""),
        "model": str(row["model"] or ""),
        "size": str(row["size"] or ""),
        "sample_count": max(1, int(row["sample_count"] or 1)),
        "logo_requested": bool(row["logo_requested"]),
        "image_count": max(0, int(row["image_count"] or 0)),
        "saved_bytes": max(0, int(row["saved_bytes"] or 0)),
        "error_code": str(row["error_code"] or ""),
        "error_message": str(row["error_message"] or ""),
        "started_at": str(row["started_at"] or ""),
        "completed_at": str(row["completed_at"] or ""),
        "elapsed_ms": float(row["elapsed_ms"]) if row["elapsed_ms"] is not None else None,
        "first_generated_image_id": (
            int(row["first_generated_image_id"])
            if "first_generated_image_id" in row_keys and row["first_generated_image_id"] is not None
            else None
        ),
        "first_saved_image_url": (
            str(row["first_saved_image_url"] or "")
            if "first_saved_image_url" in row_keys
            else ""
        ),
        "first_saved_image_name": (
            str(row["first_saved_image_name"] or "")
            if "first_saved_image_name" in row_keys
            else ""
        ),
        "first_logo_overlay_applied": (
            bool(row["first_logo_overlay_applied"])
            if "first_logo_overlay_applied" in row_keys and row["first_logo_overlay_applied"] is not None
            else False
        ),
    }


def normalize_gallery_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_tag in tags[:20]:
        tag = str(raw_tag).strip()[:40]
        if not tag:
            continue
        folded = tag.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        cleaned.append(tag)
    return cleaned


def _gallery_image_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = _generated_image_row_to_dict(row)
    row_keys = row.keys()
    try:
        parsed = json.loads(str(row["metadata_json"] or "{}")) if "metadata_json" in row_keys else {}
        metadata = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        metadata = {}
    item["metadata"] = metadata
    _attach_original_source_fields(item, metadata)
    raw_tags = _row_text(row, "tags_text")
    tags = [tag for tag in raw_tags.split("\x1f") if tag] if raw_tags else []
    item.update(
        {
            "username": _row_text(row, "username"),
            "display_name": _row_text(row, "display_name"),
            "is_favorite": bool(row["is_favorite"]) if "is_favorite" in row_keys else False,
            "tags": tags,
            "gallery_updated_at": row["gallery_updated_at"] if "gallery_updated_at" in row_keys else None,
        }
    )
    return item


def _password_reset_request_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    user_id = int(row["user_id"]) if row["user_id"] is not None else None
    resolver_id = int(row["resolved_by_user_id"]) if row["resolved_by_user_id"] is not None else None
    row_keys = row.keys()
    email = str(row["email"] or "") if "email" in row_keys else ""
    return {
        "id": int(row["id"]),
        "user_id": user_id,
        "username": str(row["username"] or ""),
        "username_normalized": str(row["username_normalized"] or ""),
        "matched_user": user_id is not None,
        "matched_username": str(row["matched_username"] or "") if row["matched_username"] is not None else "",
        "status": str(row["status"] or ""),
        "email_available": bool(email),
        "email_masked": mask_email(email),
        "email_sent_at": row["email_sent_at"] if "email_sent_at" in row_keys else None,
        "expires_at": row["expires_at"] if "expires_at" in row_keys else None,
        "requested_ip": str(row["requested_ip"] or ""),
        "user_agent": str(row["user_agent"] or ""),
        "created_at": str(row["created_at"]),
        "resolved_at": row["resolved_at"],
        "resolved_by_user_id": resolver_id,
        "resolved_by_username": (
            str(row["resolved_by_username"] or "") if row["resolved_by_username"] is not None else ""
        ),
    }


def mask_email(email: str) -> str:
    cleaned = email.strip()
    if "@" not in cleaned:
        return ""
    local, domain = cleaned.split("@", 1)
    if not local or not domain:
        return ""
    masked_local = f"{local[0]}*" if len(local) <= 2 else f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


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
        "simple_checklist_completed": False,
        "updated_at": None,
    }


def _user_preferences_from_row(user_id: int, row: sqlite3.Row) -> dict[str, Any]:
    ui_mode = str(row["ui_mode"] or "")
    return {
        "user_id": user_id,
        **({"ui_mode": ui_mode} if ui_mode in _UI_MODES else {}),
        "default_model": str(row["default_model"] or ""),
        "default_responses_model": str(row["default_responses_model"] or ""),
        "default_size": str(row["default_size"] or ""),
        "default_quality": str(row["default_quality"] or ""),
        "default_output_format": str(row["default_output_format"] or ""),
        "default_image_transport": str(row["default_image_transport"] or ""),
        "logo_overlay_enabled": bool(row["logo_overlay_enabled"]),
        "auto_copyright_check_enabled": bool(row["auto_copyright_check_enabled"]),
        "simple_checklist_completed": bool(row["simple_checklist_completed"]),
        "updated_at": row["updated_at"],
    }


def _success_template_title(prompt: str) -> str:
    first_line = next((line.strip() for line in prompt.splitlines() if line.strip()), "")
    return first_line[:48] or "满意提示词模板"


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
        if not 1 <= iterations <= 10_000_000:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    except (ValueError, TypeError):
        return False
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
