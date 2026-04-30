from __future__ import annotations

import argparse
import os

import uvicorn

from .config import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local UI for upstream image generation and editing APIs.")
    parser.add_argument("--host", default=os.environ.get("PICGEN_HOST", "127.0.0.1"), help="Bind host")
    parser.add_argument(
        "--port",
        default=int(os.environ.get("PICGEN_PORT", "8000")),
        type=int,
        help="Bind port",
    )
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload mode")
    return parser.parse_args()


def main() -> int:
    settings = Settings.from_env()
    if not settings.static_dir.exists():
        raise SystemExit(f"Static directory not found: {settings.static_dir}")

    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    args = parse_args()
    print(f"PicGen server running at http://{args.host}:{args.port}")
    uvicorn.run("picgen.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0
