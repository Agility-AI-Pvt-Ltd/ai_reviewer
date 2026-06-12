#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
COMPOSE_PATH = ROOT / "docker-compose.local.yml"

LOCAL_POSTGRES_PORT = "54329"
LOCAL_REDIS_PORT = "63799"
LOCAL_DATABASE_URL = (
    f"postgresql+asyncpg://futurex:futurex@localhost:{LOCAL_POSTGRES_PORT}/futurex_reviewer"
)
LOCAL_REDIS_URL = f"redis://localhost:{LOCAL_REDIS_PORT}/0"

LOCAL_ENV_VALUES = {
    "APP_ENV": "development",
    "APP_PORT": "8000",
    "DATABASE_URL": LOCAL_DATABASE_URL,
    "REDIS_URL": LOCAL_REDIS_URL,
    "REDIS_UR": LOCAL_REDIS_URL,
    "API_RATE_LIMIT_ENABLED": "true",
    "API_RATE_LIMIT_REQUESTS": "120",
    "API_RATE_LIMIT_WINDOW_SECONDS": "60",
    "LOCAL_POSTGRES_PORT": LOCAL_POSTGRES_PORT,
    "LOCAL_REDIS_PORT": LOCAL_REDIS_PORT,
}


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(command))
    return subprocess.run(command, cwd=ROOT, check=check, text=True)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required tool: {name}")


def docker_compose_command() -> list[str]:
    require_tool("docker")
    result = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit("Docker Compose is required. Install Docker Desktop and try again.")
    return ["docker", "compose", "-f", str(COMPOSE_PATH)]


def parse_env_lines(text: str) -> tuple[list[str], dict[str, int]]:
    lines = text.splitlines()
    positions: dict[str, int] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            positions[key] = index
    return lines, positions


def write_local_env() -> None:
    if ENV_PATH.exists():
        lines, positions = parse_env_lines(ENV_PATH.read_text(encoding="utf-8"))
    else:
        lines, positions = [], {}

    for key, value in LOCAL_ENV_VALUES.items():
        line = f"{key}={value}"
        if key in positions:
            lines[positions[key]] = line
        else:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(line)
            positions[key] = len(lines) - 1

    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Updated {ENV_PATH.relative_to(ROOT)} with local Postgres/Redis settings.")


def start_local_services() -> None:
    compose = docker_compose_command()
    run([*compose, "up", "-d", "postgres", "redis"])


def wait_for_services(timeout_seconds: int = 60) -> None:
    compose = docker_compose_command()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        postgres = subprocess.run(
            [*compose, "exec", "-T", "postgres", "pg_isready", "-U", "futurex", "-d", "futurex_reviewer"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        redis = subprocess.run(
            [*compose, "exec", "-T", "redis", "redis-cli", "ping"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if postgres.returncode == 0 and redis.returncode == 0:
            print("Local Postgres and Redis are ready.")
            return
        time.sleep(2)
    raise SystemExit("Timed out waiting for local Postgres/Redis to become ready.")


def install_dependencies() -> None:
    require_tool("uv")
    run(["uv", "sync"])


def initialize_local_schema() -> None:
    compose = docker_compose_command()
    schema_path = ROOT / "db" / "schema.sql"
    print("$", " ".join([*compose, "exec", "-T", "postgres", "psql", "-U", "futurex", "-d", "futurex_reviewer"]), "<", schema_path.relative_to(ROOT))
    with schema_path.open("rb") as schema:
        subprocess.run(
            [*compose, "exec", "-T", "postgres", "psql", "-U", "futurex", "-d", "futurex_reviewer"],
            cwd=ROOT,
            stdin=schema,
            check=True,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up futurex-reviewer for local development.")
    parser.add_argument("--skip-docker", action="store_true", help="Do not start local Postgres/Redis.")
    parser.add_argument("--skip-install", action="store_true", help="Do not run uv sync.")
    parser.add_argument("--skip-schema", action="store_true", help="Do not create local development tables.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    write_local_env()

    if not args.skip_docker:
        start_local_services()
        wait_for_services()

    if not args.skip_install:
        install_dependencies()

    if not args.skip_schema:
        initialize_local_schema()

    print()
    print("Local setup complete.")
    print(f"Postgres: {LOCAL_DATABASE_URL}")
    print(f"Redis:    {LOCAL_REDIS_URL}")
    print("Run the service with: uv run fastapi dev app/main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
