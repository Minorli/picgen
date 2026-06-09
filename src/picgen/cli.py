from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from .config import Settings
from .logging_config import configure_logging, get_logger
from .storage import prune_old_outputs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="picgen",
        description="PicGen Console — enterprise-grade local UI for OpenAI image APIs.",
    )
    parser.add_argument("--host", default=os.environ.get("PICGEN_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PICGEN_PORT", "8000")),
    )
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload (dev only)")
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("PICGEN_WORKERS", "1")),
        help="Number of uvicorn worker processes (production)",
    )
    parser.add_argument("--log-level", default=os.environ.get("PICGEN_LOG_LEVEL", "INFO"))
    parser.add_argument(
        "--log-format",
        choices=("console", "json"),
        default=os.environ.get("PICGEN_LOG_FORMAT", "console"),
    )
    parser.add_argument(
        "--access-log",
        action="store_true",
        help="Enable uvicorn access log (defaults to off; structured logs already cover requests)",
    )
    parser.add_argument(
        "--prune-now",
        action="store_true",
        help="Prune outputs older than PICGEN_STORAGE_RETENTION_DAYS and exit",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print resolved configuration and exit (secrets masked)",
    )
    return parser


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:4]}…{value[-2:]}"


def _print_config(settings: Settings) -> None:
    snapshot = {
        "static_dir": str(settings.static_dir),
        "data_dir": str(settings.data_dir),
        "outputs_dir": str(settings.outputs_dir),
        "default_generate_url": settings.default_generate_url,
        "default_edit_url": settings.default_edit_url,
        "default_responses_url": settings.default_responses_url,
        "default_model": settings.default_model,
        "default_responses_model": settings.default_responses_model,
        "default_size": settings.default_size,
        "default_api_key": _mask_secret(settings.default_api_key),
        "proxy_auth_token": _mask_secret(settings.proxy_auth_token),
        "bug_report_webhook_url": _mask_secret(settings.bug_report_webhook_url),
        "bug_report_webhook_kind": settings.bug_report_webhook_kind,
        "error_alert_telegram_enabled": bool(
            settings.error_alert_telegram_bot_token and settings.error_alert_telegram_chat_id
        ),
        "error_alert_telegram_chat_id": _mask_secret(settings.error_alert_telegram_chat_id),
        "password_reset_email_enabled": bool(
            settings.smtp_host and settings.smtp_from_email and settings.smtp_username and settings.smtp_password
        ),
        "public_base_url": settings.public_base_url,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_username": _mask_secret(settings.smtp_username),
        "smtp_password": _mask_secret(settings.smtp_password),
        "smtp_from_email": settings.smtp_from_email,
        "smtp_from_name": settings.smtp_from_name,
        "smtp_use_tls": settings.smtp_use_tls,
        "smtp_starttls": settings.smtp_starttls,
        "password_reset_token_minutes": settings.password_reset_token_minutes,
        "auth_enabled": settings.auth_enabled,
        "auth_db_path": str(settings.resolved_auth_db_path),
        "auth_cookie_name": settings.auth_cookie_name,
        "auth_cookie_secure": settings.auth_cookie_secure,
        "auth_session_days": settings.auth_session_days,
        "upstream_timeout_seconds": settings.upstream_timeout_seconds,
        "upstream_connect_timeout_seconds": settings.upstream_connect_timeout_seconds,
        "upstream_max_connections": settings.upstream_max_connections,
        "upstream_max_retries": settings.upstream_max_retries,
        "max_request_body_bytes": settings.max_request_body_bytes,
        "max_image_bytes": settings.max_image_bytes,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "rate_limit_burst": settings.rate_limit_burst,
        "cors_allow_origins": settings.cors_allow_origins,
        "log_level": settings.log_level,
        "log_format": settings.log_format,
        "storage_retention_days": settings.storage_retention_days,
    }
    for key, value in snapshot.items():
        print(f"{key} = {value}")


def main() -> int:
    args = _build_parser().parse_args()
    configure_logging(args.log_level, args.log_format)
    logger = get_logger("picgen.cli")

    try:
        settings = Settings.from_env()
    except Exception as exc:
        print(f"配置解析失败: {exc}", file=sys.stderr)
        return 2

    if args.print_config:
        _print_config(settings)
        return 0

    if not settings.static_dir.exists():
        print(f"Static directory not found: {settings.static_dir}", file=sys.stderr)
        return 2

    settings.outputs_dir.mkdir(parents=True, exist_ok=True)

    if args.prune_now:
        removed = prune_old_outputs(settings.outputs_dir, settings.storage_retention_days)
        print(f"pruned {removed} day-folder(s)")
        return 0

    if args.workers > 1 and args.reload:
        print("--reload cannot be combined with --workers > 1", file=sys.stderr)
        return 2

    logger.info(
        "starting picgen",
        extra={
            "fields": {
                "host": args.host,
                "port": args.port,
                "workers": args.workers,
                "reload": args.reload,
                "log_format": args.log_format,
            }
        },
    )

    uvicorn.run(
        "picgen.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else None,
        log_level=args.log_level.lower(),
        access_log=args.access_log,
        proxy_headers=settings.trust_forwarded_for,
        forwarded_allow_ips="*" if settings.trust_forwarded_for else None,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
