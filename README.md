# MindRoom Stack (Full Docker Compose)

<picture>
  <source media="(prefers-reduced-motion: no-preference)" srcset="https://raw.githubusercontent.com/mindroom-ai/mindroom/main/assets/logo/logo-mark-animated.svg" />
  <img src="https://raw.githubusercontent.com/mindroom-ai/mindroom/main/assets/logo/logo-mark.svg" alt="MindRoom Logo" align="right" width="120" />
</picture>

This repo starts a complete MindRoom stack in one command:
- MindRoom runtime with bundled dashboard
- Matrix Tuwunel homeserver
- MindRoom web client from a published image

## Quick Start

```bash
git clone https://github.com/mindroom-ai/mindroom-stack
cd mindroom-stack
./scripts/quickstart.py
```

On first run, `./scripts/quickstart.py` will:
- create `.env` from `.env.example` if it does not exist
- record the invoking host UID/GID in `.env` so bind-mounted files remain editable
- stop with a clear error until at least one provider key is configured
- generate a `MINDROOM_API_KEY` in `.env`, which the MindRoom UI login asks for
- start `docker compose`
- wait until MindRoom, the client, and the managed rooms are actually ready
- tell you exactly which `.env` settings to change if the default host ports are busy
- surface common startup problems with an explicit fix instead of a raw compose health failure
- print the exact URLs to open

Recommended fastest path:

```bash
cp .env.example .env
$EDITOR .env  # set ANTHROPIC_API_KEY
./scripts/quickstart.py
```

Manual fallback:

```bash
MINDROOM_RUNTIME_UID=$(id -u) MINDROOM_RUNTIME_GID=$(id -g) docker compose up -d
```

Open:
- MindRoom UI: http://localhost:8765 (sign in with `MINDROOM_API_KEY` from `.env`)
- MindRoom client: http://localhost:8080
- Matrix homeserver: http://localhost:8008

If those host ports are already in use, change `HOST_HOMESERVER_PORT`,
`HOST_CLIENT_PORT`, and/or `HOST_DASHBOARD_PORT` in `.env` before starting. If
you change the homeserver or dashboard port, also keep `CLIENT_HOMESERVER_URL`
and `CLIENT_MINDROOM_URL` aligned with the new host ports.

The stack uses published images by default:
- `ghcr.io/mindroom-ai/mindroom:latest`
- `ghcr.io/mindroom-ai/mindroom-chat`, at the MindRoom Chat release `compose.yaml`
  names; the package's `latest` tag is the earlier MindRoom Chat app, which gets
  no updates
- `ghcr.io/mindroom-ai/mindroom-tuwunel:latest`

If you want to pin or override the MindRoom, client, or homeserver image, set
`MINDROOM_IMAGE`, `MINDROOM_CLIENT_IMAGE`, or `MINDROOM_TUWUNEL_IMAGE` in
`.env` before starting the stack. MindRoom Chat releases are listed at
https://github.com/mindroom-ai/mindroom-chat/releases. A `.env` copied from an
older `.env.example` sets `MINDROOM_CLIENT_IMAGE` to the earlier app
(`ghcr.io/mindroom-ai/mindroom-chat:latest` or
`ghcr.io/mindroom-ai/mindroom-cinny:latest`); delete that line, then run
`docker compose pull` (see [Update](#update)). `./scripts/quickstart.py` stops
until you delete it.

If you access from another device, set these in `.env` before starting:

```bash
CLIENT_HOMESERVER_URL=http://<host-ip>:8008
CLIENT_MINDROOM_URL=http://<host-ip>:8765
```

MindRoom then expects to be opened at `CLIENT_MINDROOM_URL`, including from the
machine running the stack.

## First Login (MindRoom Client)

1) Open the MindRoom client. By default that is http://localhost:8080.
   The client is held back until MindRoom has finished creating the managed rooms.
2) The client should already point at your homeserver via `CLIENT_HOMESERVER_URL`.
   If not, set the server to:
   - Local machine: `http://localhost:8008`
   - From another device: `http://<host-ip>:8008`
3) Create a new account (registration is enabled).
4) You should be auto-joined to:
   - `#lobby:matrix.localhost` for the shared Assistant agent
   - `#personal:matrix.localhost` for the full-profile `Mind` agent
5) Try:
   - `@mindroom_assistant:matrix.localhost hello` in `#lobby:matrix.localhost`
   - `@mindroom_mind:matrix.localhost who are you?` in `#personal:matrix.localhost`
6) Once you give an agent tools that use accounts, such as Google Drive or
   GitHub, save the provider's OAuth client in the MindRoom UI (see
   [OAuth Integration Framework](https://docs.mindroom.chat/oauth-framework/),
   and for Google
   [Google Services OAuth](https://docs.mindroom.chat/deployment/google-services-oauth/)).
   This stack's agents are shared, so their accounts, such as Google Drive, are
   connected in the MindRoom UI too. Google accepts plain HTTP only for
   `localhost`, so Google accounts connect only while `CLIENT_MINDROOM_URL` is
   a `localhost` or HTTPS address. Accounts that are always per user, such as
   GitHub, are connected by each user from Settings, General, **Open
   Connections** in the client. The Computer button in agent rooms needs
   worker computers, which this stack does not set up; see
   [Worker Computers](https://docs.mindroom.chat/tools/worker-computer/).

The default `config/config.yaml` is set up for a shared local dev lobby:
- it uses Anthropic Claude Opus by default while following the current MindRoom starter structure
- it includes the full `Mind` agent and mounts the bundled `mind_data/` directory into the canonical Mind workspace
- managed rooms use multi-user/public access
- both `lobby` and `personal` are published to the room directory
- fresh local users are authorized by default

## Owner Accounts And Managed Agent Accounts

The Docker stack does not run `mindroom config init` or `mindroom connect`.
It ships this repo's `config/config.yaml` and starts a local Tuwunel homeserver with open registration for local development.
That can make the standard owner-account flow easy to miss.

In the normal hosted/local onboarding flow, `mindroom config init` writes owner placeholders into membership access fields.
Then `mindroom connect --pair-code ...` replaces those placeholders with the Matrix account you paired.
That covers using your ordinary human Matrix account as the MindRoom owner.

Because stack users edit this repo's `config/config.yaml` directly, the owner-only template is documented in that file beside the active membership access blocks.
Replace `@your-user:matrix.localhost` with your Matrix account if you want to lock the stack to one owner.

This stack takes a different local-dev default: each responder allows current room members.
Any fresh local user on the stack homeserver can join the published managed rooms and talk to the agents.
That includes Mind's `shell`, which runs commands in the MindRoom container as MindRoom's own user, so they can read and change MindRoom's config, provider keys, dashboard key, and data.
Anyone who can reach the homeserver port can register, so make the stack owner-only before other people can reach it.
To make the stack owner-only, follow the template in `config/config.yaml` to switch rooms to invite-only and grant the owner explicitly.

Agent accounts are separate managed Matrix users.
MindRoom creates and persists them in the stack `mindroom_data` Docker volume.
Importing pre-existing agent account credentials is not part of this stack quickstart.

With only `ANTHROPIC_API_KEY` set, the chat flow works end to end. The default
stack config now prefers a local `sentence_transformers` embedder for semantic
search over the Mind workspace `memory/` directory, so no separate embedding
API key is required by default.

If your installed MindRoom image predates that embedder support, the quickstart
script will tell you to update `MINDROOM_IMAGE` or temporarily switch the
embedder back to `openai` or `ollama`.

If `matrix.localhost` doesn’t resolve on your device, either:
- use `http://<host-ip>:8008`, or
- add a hosts entry for `matrix.localhost` pointing at your host IP.

To verify the full flow against a running stack:

```bash
python3 scripts/stack_smoke_test.py --restart-check
```

Run it after the stack is up and at least one working provider key is configured.

This checks:
- homeserver, dashboard, and client reachability
- fresh-user auto-join into `#lobby:matrix.localhost` and `#personal:matrix.localhost`
- a real `assistant` reply in the lobby
- a real `mind` reply in the personal room
- a full `docker compose restart` followed by another successful `mind` reply

## Configure Models

Edit `config/config.yaml` and restart MindRoom:

```bash
docker compose restart mindroom
```

Example OpenAI-compatible base URL:

```yaml
models:
  main:
    provider: openai
    id: your-model-id
    extra_kwargs:
      base_url: http://your-openai-compatible-server/v1
```

Example embedding config:

```yaml
memory:
  embedder:
    provider: openai
    config:
      model: embeddinggemma:300m
      host: http://your-embeddings-server/v1
```

Ensure `.env` has a valid API key for the provider you use, then run
`docker compose up -d` so MindRoom starts with it.

Local model servers running on the Docker host are reachable from MindRoom at
`host.docker.internal`, not `localhost`. The commented Ollama and llama.cpp
presets in `config/config.yaml` already use that address. On Linux, make the
server listen beyond loopback (for example `OLLAMA_HOST=0.0.0.0 ollama serve`)
and let the host firewall accept its port from Docker networks. A `.env` copied
from an older `.env.example` still sets `OLLAMA_HOST=http://localhost:11434`;
change it to `http://host.docker.internal:11434`.

## API Keys

API keys can be configured in two ways:

1. **`.env` file** -- set keys before starting the stack, or run `docker compose up -d` after editing.
2. **MindRoom UI** -- go to the dashboard URL from `.env` (default `http://localhost:8765`) and configure keys in the integrations settings.

MindRoom reads the `.env` keys from its environment on every start and stores no
copy, so removing a key from `.env` and running `docker compose up -d` stops
MindRoom from using it. `docker compose restart` keeps the old values.
A key saved in the UI takes precedence over the `.env` value for the same provider.

> **Note:** The default `config/config.yaml` uses `provider: anthropic`, so you need
> `ANTHROPIC_API_KEY` set in `.env` (or configured via the UI) for the assistant
> to work.

## Dashboard Login

The MindRoom UI listens on every interface of the host, so `./scripts/quickstart.py`
protects it with a random `MINDROOM_API_KEY` in `.env`. Its login page names
`/app/config/.env`, the path inside the container; in this stack the key is in
the stack's `.env`. Quickstart refuses to start MindRoom without a key; the
manual `docker compose up -d` leaves the UI open to anyone who can reach its
port unless you set `MINDROOM_API_KEY` in `.env` yourself. Open the UI at
`CLIENT_MINDROOM_URL`: once signed in, changes made from any other address are
refused.

## Update

```bash
docker compose down &&
  git pull &&
  docker compose pull &&
  ./scripts/quickstart.py
```

Stop the stack first: MindRoom reloads `config/config.yaml` as soon as it
changes. If `git pull` refuses because of changes of yours, such as
`config/config.yaml` saved from the MindRoom UI or Mind's notes in
`mind_data/`, run `git stash`, `git pull` and `git stash pop`, resolve any
conflict, then run `docker compose pull && ./scripts/quickstart.py`.
`docker compose pull` matters because `docker compose up -d` keeps the `latest`
images it pulled before, and a config from a newer stack can need a newer
MindRoom image. With an image that exists only on your machine set in `.env`,
use `docker compose pull --ignore-pull-failures`.

## Stop

```bash
docker compose down
```

## Troubleshooting

- Port already in use: update `HOST_HOMESERVER_PORT`, `HOST_CLIENT_PORT`, and/or
  `HOST_DASHBOARD_PORT` in `.env`. If you change the homeserver or dashboard
  port, also update `CLIENT_HOMESERVER_URL` or `CLIENT_MINDROOM_URL` to match.
- The stack is taking a while to come up: rerun `./scripts/quickstart.py --wait-only`
  to block until the dashboard, client, and managed rooms are ready.
- Quickstart stays at "Starting docker compose stack..." and `docker compose logs mindroom`
  shows `Unknown key` or another config error: the MindRoom image is older or newer than
  the stack's config. Run `docker compose pull` (and `git pull`), then rerun.
- The dashboard shows a config error: ensure MindRoom is running and `config/config.yaml` is valid.
- Agents don't respond: set a real API key in `.env` (or via the UI) and run `docker compose up -d`.
- If you changed `.env` after first startup, run `docker compose up -d`; `docker compose restart` does not reread `.env`.
- To test a different MindRoom, client, or homeserver build, point `MINDROOM_IMAGE`, `MINDROOM_CLIENT_IMAGE`, or `MINDROOM_TUWUNEL_IMAGE` at another image tag before starting the stack.

## Production Notes

This stack is optimized for quick local setup. For production:
- Set `TUWUNEL_ALLOW_REGISTRATION=false` or configure `TUWUNEL_REGISTRATION_TOKEN`, and remove the open-registration override used for local development.
- Use TLS and a reverse proxy.
- Make the stack owner-only (see [Owner Accounts And Managed Agent Accounts](#owner-accounts-and-managed-agent-accounts)) or remove `shell` from Mind: its commands run in the MindRoom container with MindRoom's config, keys, and data.
