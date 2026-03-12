#!/usr/bin/env python3
"""Exercise the documented MindRoom stack flow against a running local stack."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_TIMEOUT_SECONDS = 180.0
STACK_ROOT = Path(__file__).resolve().parents[1]


class SmokeTestError(RuntimeError):
    """Raised when the stack fails a smoke-test expectation."""


@dataclass(frozen=True)
class RegisteredUser:
    """Registration details for a temporary Matrix user."""

    user_id: str
    access_token: str
    password: str


def _request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - exercised in integration only
        detail = exc.read().decode("utf-8", errors="replace")
        raise SmokeTestError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - exercised in integration only
        raise SmokeTestError(f"{method} {url} failed: {exc.reason}") from exc

    if not body:
        return {}
    return json.loads(body)


def _request_bytes(url: str, *, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "*/*"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - exercised in integration only
        detail = exc.read().decode("utf-8", errors="replace")
        raise SmokeTestError(f"GET {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - exercised in integration only
        raise SmokeTestError(f"GET {url} failed: {exc.reason}") from exc


def _wait_for_json(
    description: str,
    timeout_seconds: float,
    callback: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return callback()
        except Exception as exc:  # pragma: no cover - exercised in integration only
            last_error = exc
            time.sleep(1.0)
    if last_error is None:
        raise SmokeTestError(f"Timed out waiting for {description}")
    raise SmokeTestError(f"Timed out waiting for {description}: {last_error}") from last_error


def _wait_for_condition(
    description: str,
    timeout_seconds: float,
    callback: Callable[[], Any],
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = callback()
        if result:
            return result
        time.sleep(1.0)
    raise SmokeTestError(f"Timed out waiting for {description}")


def _register_user(homeserver: str) -> RegisteredUser:
    suffix = uuid.uuid4().hex[:10]
    username = f"stack_smoke_{suffix}"
    password = f"stack-smoke-{suffix}"
    payload = {
        "username": username,
        "password": password,
        "auth": {"type": "m.login.dummy"},
        "initial_device_display_name": "stack-smoke-test",
    }
    response = _request_json("POST", f"{homeserver}/_matrix/client/v3/register", payload=payload)
    return RegisteredUser(
        user_id=response["user_id"],
        access_token=response["access_token"],
        password=password,
    )


def _resolve_room_alias(homeserver: str, room_alias: str, token: str | None = None) -> str:
    encoded_alias = urllib.parse.quote(room_alias, safe="")
    response = _request_json(
        "GET",
        f"{homeserver}/_matrix/client/v3/directory/room/{encoded_alias}",
        token=token,
    )
    return response["room_id"]


def _joined_rooms(homeserver: str, token: str) -> list[str]:
    response = _request_json("GET", f"{homeserver}/_matrix/client/v3/joined_rooms", token=token)
    rooms = response.get("joined_rooms")
    if not isinstance(rooms, list):
        raise SmokeTestError("joined_rooms response was missing 'joined_rooms'")
    return [str(room_id) for room_id in rooms]


def _sync(homeserver: str, token: str, *, since: str | None = None, timeout_ms: int = 5000) -> dict[str, Any]:
    params = {"timeout": str(timeout_ms)}
    if since:
        params["since"] = since
    query = urllib.parse.urlencode(params)
    return _request_json("GET", f"{homeserver}/_matrix/client/v3/sync?{query}", token=token, timeout=30.0)


def _send_structured_mention(
    homeserver: str,
    token: str,
    *,
    room_id: str,
    assistant_user_id: str,
    marker: str,
) -> str:
    txn_id = uuid.uuid4().hex
    pill = (
        f'<a href="https://matrix.to/#/{assistant_user_id}">'
        f"{assistant_user_id}</a>"
    )
    payload = {
        "msgtype": "m.text",
        "body": f"{assistant_user_id} reply with exactly {marker}",
        "format": "org.matrix.custom.html",
        "formatted_body": f"{pill} reply with exactly <code>{marker}</code>",
        "m.mentions": {"user_ids": [assistant_user_id]},
    }
    response = _request_json(
        "PUT",
        f"{homeserver}/_matrix/client/v3/rooms/{urllib.parse.quote(room_id, safe='')}/send/"
        f"m.room.message/{txn_id}",
        token=token,
        payload=payload,
    )
    return str(response["event_id"])


def _event_body(event: dict[str, Any]) -> str | None:
    content = event.get("content")
    if not isinstance(content, dict):
        return None
    new_content = content.get("m.new_content")
    if isinstance(new_content, dict):
        body = new_content.get("body")
        if isinstance(body, str):
            return body
    body = content.get("body")
    if isinstance(body, str):
        return body
    return None


def _is_meaningful_assistant_body(body: str, marker: str) -> bool:
    stripped = body.strip()
    if not stripped:
        return False
    if marker in stripped:
        return True
    lowered = stripped.lower()
    if lowered.startswith("thinking...") or lowered.startswith("thinking…"):
        return False
    return True


def _wait_for_assistant_reply(
    homeserver: str,
    token: str,
    *,
    room_id: str,
    assistant_user_id: str,
    marker: str,
    since: str | None,
    timeout_seconds: float,
) -> str:
    next_batch = since
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = _sync(homeserver, token, since=next_batch, timeout_ms=5000)
        next_batch = response.get("next_batch", next_batch)
        joined = response.get("rooms", {}).get("join", {})
        room_data = joined.get(room_id, {})
        events = room_data.get("timeline", {}).get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("type") != "m.room.message":
                continue
            if event.get("sender") != assistant_user_id:
                continue
            body = _event_body(event)
            if body and _is_meaningful_assistant_body(body, marker):
                return str(event.get("event_id", ""))
        time.sleep(0.5)
    raise SmokeTestError(f"Timed out waiting for assistant reply containing {marker}")


def _assert_client_config(client_url: str, homeserver: str) -> None:
    response = _request_json("GET", f"{client_url}/config.json")
    actual = response.get("defaultHomeserverUrl")
    if actual is None:
        homeserver_list = response.get("homeserverList")
        default_index = response.get("defaultHomeserver")
        if isinstance(homeserver_list, list) and isinstance(default_index, int):
            try:
                actual = homeserver_list[default_index]
            except IndexError:
                actual = None
    if actual != homeserver:
        raise SmokeTestError(
            f"Client config mismatch: expected defaultHomeserverUrl={homeserver!r}, got {actual!r}"
        )


def _restart_stack() -> None:
    subprocess.run(
        ["docker", "compose", "restart"],
        cwd=STACK_ROOT,
        check=True,
    )


def _wait_for_stack_health(homeserver: str, client_url: str, dashboard_url: str, timeout_seconds: float) -> None:
    _wait_for_json(
        "homeserver /versions",
        timeout_seconds,
        lambda: _request_json("GET", f"{homeserver}/_matrix/client/versions"),
    )
    _wait_for_json(
        "MindRoom dashboard",
        timeout_seconds,
        lambda: {"ok": bool(_request_bytes(dashboard_url))},
    )
    _wait_for_json(
        "MindRoom client config",
        timeout_seconds,
        lambda: _request_json("GET", f"{client_url}/config.json"),
    )
    _assert_client_config(client_url, homeserver)


def _wait_for_room_aliases(homeserver: str, room_aliases: list[str], timeout_seconds: float) -> None:
    for room_alias in room_aliases:
        room_id = _wait_for_condition(
            f"room alias {room_alias} to resolve",
            timeout_seconds,
            lambda alias=room_alias: _resolve_room_alias(homeserver, alias),
        )
        print(f"Resolved {room_alias} -> {room_id}", flush=True)


def _resolve_and_wait_for_autojoin(
    homeserver: str,
    token: str,
    *,
    room_alias: str,
    user_id: str,
    timeout_seconds: float,
) -> str:
    room_id = _wait_for_condition(
        f"room alias {room_alias} to resolve",
        timeout_seconds,
        lambda: _resolve_room_alias(homeserver, room_alias, token),
    )
    print(f"Resolved {room_alias} -> {room_id}", flush=True)

    joined_room_id = _wait_for_condition(
        f"user {user_id} to auto-join {room_alias}",
        timeout_seconds,
        lambda: room_id if room_id in _joined_rooms(homeserver, token) else None,
    )
    print(f"Auto-joined {room_alias} as {joined_room_id}", flush=True)
    return room_id


def _exercise_agent_reply(
    homeserver: str,
    token: str,
    *,
    room_id: str,
    agent_user_id: str,
    marker_prefix: str,
    since: str | None,
    timeout_seconds: float,
) -> None:
    marker = f"{marker_prefix}-{uuid.uuid4().hex[:12]}"
    _send_structured_mention(
        homeserver,
        token,
        room_id=room_id,
        assistant_user_id=agent_user_id,
        marker=marker,
    )
    _wait_for_assistant_reply(
        homeserver,
        token,
        room_id=room_id,
        assistant_user_id=agent_user_id,
        marker=marker,
        since=since,
        timeout_seconds=timeout_seconds,
    )
    print(f"{agent_user_id} replied after mention {marker}", flush=True)


def run(args: argparse.Namespace) -> None:
    _wait_for_stack_health(args.homeserver, args.client_url, args.dashboard_url, args.timeout_seconds)
    _wait_for_room_aliases(
        args.homeserver,
        [args.assistant_room_alias, args.mind_room_alias],
        args.timeout_seconds,
    )

    user = _register_user(args.homeserver)
    print(f"Registered {user.user_id}", flush=True)

    lobby_room_id = _resolve_and_wait_for_autojoin(
        args.homeserver,
        user.access_token,
        room_alias=args.assistant_room_alias,
        user_id=user.user_id,
        timeout_seconds=args.timeout_seconds,
    )
    personal_room_id = _resolve_and_wait_for_autojoin(
        args.homeserver,
        user.access_token,
        room_alias=args.mind_room_alias,
        user_id=user.user_id,
        timeout_seconds=args.timeout_seconds,
    )

    initial_sync = _sync(args.homeserver, user.access_token, timeout_ms=0)
    since = initial_sync.get("next_batch")

    _exercise_agent_reply(
        args.homeserver,
        user.access_token,
        room_id=lobby_room_id,
        agent_user_id=args.assistant_user_id,
        marker_prefix="ASSISTANT",
        since=since,
        timeout_seconds=args.timeout_seconds,
    )
    post_assistant_sync = _sync(args.homeserver, user.access_token, timeout_ms=0)
    _exercise_agent_reply(
        args.homeserver,
        user.access_token,
        room_id=personal_room_id,
        agent_user_id=args.mind_user_id,
        marker_prefix="MIND",
        since=post_assistant_sync.get("next_batch"),
        timeout_seconds=args.timeout_seconds,
    )

    if not args.restart_check:
        return

    _restart_stack()
    _wait_for_stack_health(args.homeserver, args.client_url, args.dashboard_url, args.timeout_seconds)

    joined_after_restart = _joined_rooms(args.homeserver, user.access_token)
    missing_after_restart = [room_id for room_id in (lobby_room_id, personal_room_id) if room_id not in joined_after_restart]
    if missing_after_restart:
        raise SmokeTestError(f"User lost room membership after restart: {missing_after_restart}; joined={joined_after_restart}")
    print("Restart preserved homeserver health and room membership", flush=True)

    sync_after_restart = _sync(args.homeserver, user.access_token, timeout_ms=0)
    _exercise_agent_reply(
        args.homeserver,
        user.access_token,
        room_id=personal_room_id,
        agent_user_id=args.mind_user_id,
        marker_prefix="RESTART-MIND",
        since=sync_after_restart.get("next_batch"),
        timeout_seconds=args.timeout_seconds,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--homeserver", default="http://localhost:8008")
    parser.add_argument("--client-url", default="http://localhost:8080")
    parser.add_argument("--dashboard-url", default="http://localhost:8765")
    parser.add_argument("--assistant-room-alias", default="#lobby:matrix.localhost")
    parser.add_argument("--mind-room-alias", default="#personal:matrix.localhost")
    parser.add_argument("--assistant-user-id", default="@mindroom_assistant:matrix.localhost")
    parser.add_argument("--mind-user-id", default="@mindroom_mind:matrix.localhost")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--restart-check",
        action="store_true",
        help="Restart the stack after the first replies and verify health plus a post-restart Mind reply.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run(args)
    except (SmokeTestError, subprocess.CalledProcessError) as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
