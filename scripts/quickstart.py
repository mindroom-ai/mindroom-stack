#!/usr/bin/env python3
"""Start the local MindRoom stack with a minimal happy-path workflow."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

STACK_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = STACK_ROOT / ".env"
ENV_EXAMPLE_FILE = STACK_ROOT / ".env.example"

DEFAULT_MATRIX_SERVER_NAME = "matrix.localhost"
DEFAULT_HOMESERVER_PORT = "8008"
DEFAULT_CLIENT_PORT = "8080"
DEFAULT_DASHBOARD_PORT = "8765"
DEFAULT_HOMESERVER_URL = f"http://localhost:{DEFAULT_HOMESERVER_PORT}"
DEFAULT_CLIENT_URL = f"http://localhost:{DEFAULT_CLIENT_PORT}"
DEFAULT_DASHBOARD_URL = f"http://localhost:{DEFAULT_DASHBOARD_PORT}"

# The client image .env.example files from March to July 2026 set: the earlier MindRoom Chat app, which gets no
# updates.
RETIRED_CLIENT_IMAGE = "ghcr.io/mindroom-ai/mindroom-cinny:latest"

PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
)


class QuickstartError(RuntimeError):
    """Raised when quickstart cannot complete successfully."""


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value

    return values


def _request_json(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise QuickstartError(f"GET {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise QuickstartError(f"GET {url} failed: {exc.reason}") from exc

    if not body:
        return {}
    return json.loads(body)


def _request_bytes(url: str, *, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "*/*"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise QuickstartError(f"GET {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise QuickstartError(f"GET {url} failed: {exc.reason}") from exc


def _env_value(env_values: dict[str, str], key: str, default: str) -> str:
    value = os.getenv(key)
    if value is not None and value.strip():
        return value.strip()
    value = env_values.get(key)
    if value is not None and value.strip():
        return value.strip()
    return default


def _wait_for_condition(
    description: str,
    timeout_seconds: float,
    callback: Callable[[], Any],
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = callback()
        except Exception as exc:
            last_error = exc
            time.sleep(1.0)
            continue
        if result:
            return result
        time.sleep(1.0)

    if last_error is None:
        raise QuickstartError(f"Timed out waiting for {description}")
    raise QuickstartError(f"Timed out waiting for {description}: {last_error}") from last_error


def _run_compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", *args],
        cwd=STACK_ROOT,
        check=True,
    )


def _compose_output(*args: str) -> str:
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=STACK_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout


def _ensure_env_file() -> dict[str, str]:
    if ENV_FILE.exists():
        return _load_env_file(ENV_FILE)

    shutil.copyfile(ENV_EXAMPLE_FILE, ENV_FILE)
    raise QuickstartError(
        "Created .env from .env.example. Set ANTHROPIC_API_KEY in .env and rerun ./scripts/quickstart.py."
    )


def _ensure_runtime_identity(env_values: dict[str, str]) -> None:
    """Persist the invoking host identity for writable bind-mounted files."""
    if sys.platform == "win32":
        return
    missing_values = {
        name: value
        for name, value in (
            ("MINDROOM_RUNTIME_UID", str(os.getuid())),
            ("MINDROOM_RUNTIME_GID", str(os.getgid())),
        )
        if not (os.getenv(name) or env_values.get(name, "")).strip()
    }
    if missing_values:
        _append_env_values(env_values, "Host identity for writable bind mounts.", missing_values)


def _ensure_dashboard_api_key(env_values: dict[str, str]) -> None:
    """Make compose pass MindRoom a MINDROOM_API_KEY, since the dashboard listens on every interface.

    Generates one in .env when neither .env nor the shell sets it, then checks the value compose resolves
    with the same env files `up -d` reads, so a blank shell export, an empty interpolation, or another
    COMPOSE_ENV_FILES selection cannot leave the dashboard open.
    """
    if "MINDROOM_API_KEY" not in env_values and "MINDROOM_API_KEY" not in os.environ:
        _append_env_values(env_values, "Dashboard login key.", {"MINDROOM_API_KEY": secrets.token_urlsafe(32)})
        print("Generated MINDROOM_API_KEY in .env; the dashboard login asks for it.")
    config = _compose_config()
    if not (config["services"]["mindroom"]["environment"].get("MINDROOM_API_KEY") or "").strip():
        raise QuickstartError(
            "docker compose passes MindRoom an empty MINDROOM_API_KEY, which would let anyone who can reach "
            "the dashboard administer MindRoom. Set MINDROOM_API_KEY to a long random value, or remove it "
            "from .env and unset it in your shell so quickstart generates one."
        )


def _compose_config() -> dict[str, Any]:
    """Return the configuration compose resolves, with the env files and shell `up -d` reads."""
    try:
        return json.loads(_compose_output("config", "--format", "json"))
    except subprocess.CalledProcessError as exc:
        raise QuickstartError(f"docker compose config failed: {(exc.stderr or exc.output or '').strip()}") from exc


def _refuse_retired_client_image() -> None:
    """Stop when compose would start the earlier MindRoom Chat app instead of the one compose.yaml names."""
    image = _compose_config()["services"]["client"]["image"]
    if image == RETIRED_CLIENT_IMAGE:
        raise QuickstartError(
            f"MINDROOM_CLIENT_IMAGE selects {image}, the earlier MindRoom Chat app, which gets no updates. "
            "Delete it from .env, where older .env.example files put it, or wherever else you set it, so the "
            "stack starts the MindRoom Chat compose.yaml names. Then run `docker compose pull`, since "
            "a MindRoom image pulled before this stack version can reject its config, and rerun."
        )


def _validate_config_with_image() -> None:
    """Stop when the MindRoom image compose would start rejects config/config.yaml.

    Such an image restarts in a loop, which resets its health check, so `up -d` would wait forever.
    """
    print("Checking that the MindRoom image accepts config/config.yaml (pulls missing images first)...")
    try:
        # mindroom-permissions gives the runtime user its files first, as `up -d` would. Nothing else starts, so
        # no host port is bound and nothing keeps running when the check fails.
        _compose_output("run", "--rm", "-T", "mindroom-permissions")
        _compose_output("run", "--rm", "--no-deps", "-T", "--entrypoint", "mindroom", "mindroom", "config", "validate")
    except subprocess.CalledProcessError as exc:
        # MindRoom prints config issues on stdout; Docker and compose errors go to stderr.
        output = "\n".join(part.strip() for part in (exc.output, exc.stderr) if part and part.strip())
        raise QuickstartError(
            f"Checking config/config.yaml with the MindRoom image failed:\n{output}\n"
            "If that names a key you did not add, the image is older than this stack: run `docker compose pull`, "
            "or move a MINDROOM_IMAGE you pinned to a newer release, then rerun. If your stack checkout is the "
            "older one, follow Update in README.md. If it names a plugin, fix or remove it in config/config.yaml, "
            "or start with `docker compose up -d`, which runs MindRoom without a plugin that fails to load."
        ) from exc


def _append_env_values(env_values: dict[str, str], comment: str, values: dict[str, str]) -> None:
    existing = ENV_FILE.read_text(encoding="utf-8")
    separator = "" if not existing or existing.endswith("\n") else "\n"
    additions = "\n".join(f"{name}={value}" for name, value in values.items())
    ENV_FILE.write_text(f"{existing}{separator}\n# {comment}\n{additions}\n", encoding="utf-8")
    env_values.update(values)


def _configured_provider_keys(env_values: dict[str, str]) -> list[str]:
    configured: list[str] = []
    for key in PROVIDER_KEYS:
        value = os.getenv(key) or env_values.get(key, "")
        if value.strip():
            configured.append(key)
    return configured


def _resolve_room_alias(homeserver_url: str, room_alias: str) -> str:
    encoded_alias = urllib.parse.quote(room_alias, safe="")
    response = _request_json(f"{homeserver_url}/_matrix/client/v3/directory/room/{encoded_alias}")
    room_id = response.get("room_id")
    if not isinstance(room_id, str) or not room_id:
        raise QuickstartError(f"Room alias {room_alias} resolved without a room_id")
    return room_id


def _assert_client_config(client_url: str, expected_homeserver_url: str) -> None:
    response = _request_json(f"{client_url}/config.json")
    actual = response.get("defaultHomeserverUrl")
    if actual is None:
        homeserver_list = response.get("homeserverList")
        default_index = response.get("defaultHomeserver")
        if isinstance(homeserver_list, list) and isinstance(default_index, int):
            try:
                actual = homeserver_list[default_index]
            except IndexError:
                actual = None
    if actual != expected_homeserver_url:
        raise QuickstartError(
            f"Client config mismatch: expected {expected_homeserver_url!r}, got {actual!r}"
        )


def _wait_for_stack_ready(
    *,
    homeserver_url: str,
    client_url: str,
    dashboard_url: str,
    client_homeserver_url: str,
    matrix_server_name: str,
    timeout_seconds: float,
) -> None:
    _wait_for_condition(
        "homeserver /versions",
        timeout_seconds,
        lambda: _request_json(f"{homeserver_url}/_matrix/client/versions"),
    )
    _wait_for_condition(
        "MindRoom dashboard",
        timeout_seconds,
        lambda: bool(_request_bytes(dashboard_url)),
    )
    _wait_for_condition(
        "MindRoom client config",
        timeout_seconds,
        lambda: _request_json(f"{client_url}/config.json"),
    )
    _assert_client_config(client_url, client_homeserver_url)

    for room_name in ("lobby", "personal"):
        room_alias = f"#{room_name}:{matrix_server_name}"
        room_id = _wait_for_condition(
            f"room alias {room_alias}",
            timeout_seconds,
            lambda alias=room_alias: _resolve_room_alias(homeserver_url, alias),
        )
        print(f"Ready: {room_alias} -> {room_id}")


def _preflight() -> tuple[dict[str, str], list[str]]:
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            cwd=STACK_ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise QuickstartError("docker compose is required but was not found or is not working.") from exc

    env_values = _ensure_env_file()
    _ensure_runtime_identity(env_values)
    configured_keys = _configured_provider_keys(env_values)
    if configured_keys:
        return env_values, configured_keys

    raise QuickstartError(
        "No AI provider key is configured. Set ANTHROPIC_API_KEY in .env for the fastest path, then rerun."
    )


def _diagnose_startup_failure(exc: subprocess.CalledProcessError) -> QuickstartError:
    combined_output = "\n".join(part for part in (exc.output, exc.stderr) if part).strip()
    try:
        logs = _compose_output("logs", "--tail=200", "mindroom")
    except subprocess.CalledProcessError:
        logs = ""

    if "Ports are not available" in combined_output or "port is already allocated" in combined_output:
        return QuickstartError(
            "One of the default host ports is already in use. Update "
            "HOST_HOMESERVER_PORT, HOST_CLIENT_PORT, and/or HOST_DASHBOARD_PORT "
            "in .env, and keep CLIENT_HOMESERVER_URL / CLIENT_MINDROOM_URL aligned "
            "with those host ports."
        )

    if "Unsupported knowledge embedder provider: sentence_transformers" in logs:
        return QuickstartError(
            "The current MindRoom image does not support "
            "memory.embedder.provider=sentence_transformers yet. "
            "Update MINDROOM_IMAGE to a newer build, or temporarily switch "
            "memory.embedder.provider back to openai or ollama."
        )

    if "No module named 'sentence_transformers'" in logs:
        return QuickstartError(
            "The current MindRoom image is missing the sentence_transformers runtime. "
            "Update MINDROOM_IMAGE to a build that includes the merged embedder support."
        )

    detail = combined_output or logs or str(exc)
    return QuickstartError(f"docker compose up -d failed: {detail}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wait-only",
        action="store_true",
        help="Skip docker compose up -d and only wait for the stack to become ready.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help="Maximum time to wait for stack readiness.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        env_values, configured_keys = _preflight()
        host_homeserver_port = _env_value(env_values, "HOST_HOMESERVER_PORT", DEFAULT_HOMESERVER_PORT)
        host_client_port = _env_value(env_values, "HOST_CLIENT_PORT", DEFAULT_CLIENT_PORT)
        host_dashboard_port = _env_value(env_values, "HOST_DASHBOARD_PORT", DEFAULT_DASHBOARD_PORT)
        homeserver_url = f"http://localhost:{host_homeserver_port}"
        client_url = f"http://localhost:{host_client_port}"
        dashboard_url = _env_value(
            env_values,
            "CLIENT_MINDROOM_URL",
            f"http://localhost:{host_dashboard_port}",
        )
        client_homeserver_url = _env_value(
            env_values,
            "CLIENT_HOMESERVER_URL",
            homeserver_url,
        )
        matrix_server_name = _env_value(
            env_values,
            "MATRIX_SERVER_NAME",
            DEFAULT_MATRIX_SERVER_NAME,
        )

        print(f"Using provider keys from: {', '.join(configured_keys)}")

        if not args.wait_only:
            _ensure_dashboard_api_key(env_values)
            _refuse_retired_client_image()
            _validate_config_with_image()
            print("Starting docker compose stack...")
            try:
                _compose_output("up", "-d")
            except subprocess.CalledProcessError as exc:
                raise _diagnose_startup_failure(exc) from exc

        print("Waiting for MindRoom, client, and managed rooms...")
        _wait_for_stack_ready(
            homeserver_url=homeserver_url,
            client_url=client_url,
            dashboard_url=dashboard_url,
            client_homeserver_url=client_homeserver_url,
            matrix_server_name=matrix_server_name,
            timeout_seconds=args.timeout_seconds,
        )
    except (QuickstartError, subprocess.CalledProcessError) as exc:
        print(f"Quickstart failed: {exc}", file=sys.stderr)
        return 1

    print()
    print("Stack ready.")
    print(f"Open client: {client_url}")
    print(f"Open dashboard: {dashboard_url}")
    if not args.wait_only:
        key_source = "your shell" if "MINDROOM_API_KEY" in os.environ else ".env"
        print(f"Dashboard login key: MINDROOM_API_KEY in {key_source}")
    print(f"Homeserver: {homeserver_url}")
    print("Then create an account and try:")
    print(f"- @mindroom_assistant:{matrix_server_name} hello in #lobby:{matrix_server_name}")
    print(f"- @mindroom_mind:{matrix_server_name} who are you? in #personal:{matrix_server_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
