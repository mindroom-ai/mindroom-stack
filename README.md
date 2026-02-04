# MindRoom Stack (Full Docker Compose)

This repo starts a complete MindRoom stack in one command:
- MindRoom backend + frontend
- Matrix Synapse + Postgres + Redis
- Element Web client

## Quick Start

```bash
git clone https://github.com/mindroom-ai/mindroom-stack
cd mindroom-stack
cp .env.example .env
$EDITOR .env  # add at least one AI provider key

docker compose up -d
```

Open:
- MindRoom UI: http://localhost:3003
- Element: http://localhost:8080
- Matrix homeserver: http://localhost:8008

If you access from another device, set this in `.env` before starting:

```bash
ELEMENT_HOMESERVER_URL=http://<host-ip>:8008
```

Also update `synapse/homeserver.yaml` so `public_baseurl` matches the same
reachable URL (e.g., `http://<host-ip>:8008/`). Element uses this value after
login; if it points to `matrix.localhost` on a different device, Element will
stay stuck on “Syncing…”. After editing, run:

```bash
docker compose restart synapse
```

## First Login (Element)

1) Open Element: http://localhost:8080
2) Element should already point at your homeserver via `ELEMENT_HOMESERVER_URL`.
   If not, click “Edit” (homeserver) and set it to:
   - Local machine: `http://localhost:8008`
   - From another device: `http://<host-ip>:8008`
3) Create a new account (registration is enabled).
4) You should be auto-joined to `#lobby:matrix.localhost`. If not, join it manually.
5) Mention `@mindroom_assistant:matrix.localhost` to get a response.

If `matrix.localhost` doesn’t resolve on your device, either:
- use `http://<host-ip>:8008`, or
- add a hosts entry for `matrix.localhost` pointing at your host IP.

## Configure Models

Edit `config.yaml` and restart the backend:

```bash
docker compose restart backend
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

Ensure `.env` has a valid API key for the provider you use, then restart the backend.

## Stop

```bash
docker compose down
```

## Troubleshooting

- Port 8008 already in use: stop the other service or change the mapping.
- Frontend shows a config error: ensure backend is running and `config.yaml` is valid.
- Agents don’t respond: set a real API key in `.env` and restart the backend.

## Production Notes

This stack is optimized for quick local setup. For production:
- Disable open registration in `synapse/homeserver.yaml`.
- Set strong secrets (`macaroon_secret_key`, `form_secret`).
- Use TLS and a reverse proxy.
