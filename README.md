# MindRoom Stack (Full Docker Compose)

This repo starts a complete MindRoom stack in one command:
- MindRoom runtime with bundled dashboard
- Matrix Tuwunel homeserver
- MindRoom web client from a published image

## Quick Start

```bash
git clone https://github.com/mindroom-ai/mindroom-stack
cd mindroom-stack
cp .env.example .env
$EDITOR .env  # add at least one AI provider key

docker compose up -d
```

Open:
- MindRoom UI: http://localhost:8765
- MindRoom client: http://localhost:8080
- Matrix homeserver: http://localhost:8008

The stack uses published images by default:
- `ghcr.io/mindroom-ai/mindroom:latest`
- `ghcr.io/mindroom-ai/mindroom-cinny:latest`
- `ghcr.io/mindroom-ai/mindroom-tuwunel:latest`

If you want to pin or override the client or homeserver image, set `MINDROOM_CLIENT_IMAGE` or `MINDROOM_TUWUNEL_IMAGE` in `.env` before starting the stack.

If you access from another device, set this in `.env` before starting:

```bash
CLIENT_HOMESERVER_URL=http://<host-ip>:8008
```

## First Login (MindRoom Client)

1) Open the MindRoom client: http://localhost:8080
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

The default `config.yaml` is set up for a shared local dev lobby:
- it follows the `uvx mindroom config init --profile full` structure more closely
- it includes the full-profile `Mind` agent and bundled `mind_data` workspace
- managed rooms use multi-user/public access
- both `lobby` and `personal` are published to the room directory
- fresh local users are authorized by default

With only `ANTHROPIC_API_KEY` set, the chat flow works end to end. If you also
want semantic search over `mind_data/memory`, configure the memory embedder too
for example with `OPENAI_API_KEY`, or by switching `memory.embedder` to an
Ollama embedding model.

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

Edit `config.yaml` and restart MindRoom:

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

Ensure `.env` has a valid API key for the provider you use, then restart MindRoom.

## API Keys

API keys can be configured in two ways:

1. **`.env` file** -- set keys before starting the stack (or restart after editing).
2. **MindRoom UI** -- go to http://localhost:8765 and configure keys in the integrations settings.

The `.env` file acts as an initial seed: keys are written to disk on first startup.
Once a key exists, it won't be overwritten by `.env` on subsequent restarts.
This means you can safely change keys via the UI without losing them.

Keys set via the UI are labeled "From environment" or left unlabeled depending on
their origin, so you always know where a key came from.

> **Note:** The default `config.yaml` uses `provider: anthropic`, so you need
> `ANTHROPIC_API_KEY` set in `.env` (or configured via the UI) for the assistant
> to work.

## Stop

```bash
docker compose down
```

## Troubleshooting

- Port already in use: the stack binds ports 8008, 8080, and 8765. Stop any
  conflicting services or change the port mappings in `compose.yaml`.
- The dashboard shows a config error: ensure MindRoom is running and `config.yaml` is valid.
- Agents don't respond: set a real API key in `.env` (or via the UI) and restart MindRoom.
- If you changed `.env` provider keys after first startup, restart `mindroom` so the runtime picks them up.
- To test a different client or homeserver build, point `MINDROOM_CLIENT_IMAGE` or `MINDROOM_TUWUNEL_IMAGE` at another image tag before starting the stack.

## Production Notes

This stack is optimized for quick local setup. For production:
- Set `TUWUNEL_ALLOW_REGISTRATION=false` or configure `TUWUNEL_REGISTRATION_TOKEN`, and remove the open-registration override used for local development.
- Use TLS and a reverse proxy.
