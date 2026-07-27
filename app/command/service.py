from __future__ import annotations

import argparse
import logging

import uvicorn

from app.config import load_config

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Button Clicker test server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument(
        "--reload",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Reload the server when Python source files change.",
    )
    args = parser.parse_args()
    config = load_config()
    log_level = "debug" if config.debug else "info"

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=["app"],
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
