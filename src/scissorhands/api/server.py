"""Local server command for the reporting API."""

import argparse
from pathlib import Path

import uvicorn

from scissorhands.api.app import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="scissorhands-api")
    parser.add_argument("--registry-db", type=Path, help="Project registry SQLite file")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    uvicorn.run(create_app(args.registry_db), host=args.host, port=args.port)
