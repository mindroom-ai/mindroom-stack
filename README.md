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
- Matrix homeserver: http://matrix.localhost:8008

## First Login (Element)

1) Open Element and create an account (registration is enabled).
2) Create or join a room named `lobby`.
3) Mention `@mindroom_assistant:matrix.localhost` to get a response.

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
