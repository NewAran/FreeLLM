# FreeLLM Gateway

A self-hosted **OpenAI-compatible API gateway** that lets you configure multiple free LLM providers once, then use them through one local API with automatic routing and fallback.

FreeLLM is inspired by and syncs model metadata from [`mnfst/awesome-free-llm-apis`](https://github.com/mnfst/awesome-free-llm-apis). That upstream project is a catalog; FreeLLM turns the catalog into a runnable gateway.

> **Status:** early V1. Chat Completions, streaming, provider routing/fallback, encrypted provider credentials, a web setup dashboard, Docker, Codespaces and GitHub Actions are included. Free-tier limits and provider model availability can change, so always check the provider's own terms and dashboard.

## What you get

- One OpenAI-compatible endpoint: `POST /v1/chat/completions`
- One model list endpoint: `GET /v1/models`
- Web setup/dashboard at `/`
- Encrypted provider credentials stored in the Docker volume
- Automatic provider fallback on rate limits, outages and unsupported models
- Smart aliases: `auto`, `auto-fast`, `auto-code`, `auto-reasoning`, `auto-vision`
- Direct routing with `provider::model`, for example `groq::openai/gpt-oss-120b`
- Streaming support (`stream: true`)
- Health endpoint: `GET /health`
- Automatic daily model-catalog refresh when the upstream catalog is reachable
- GitHub Actions Linux container smoke tests
- GHCR image publishing for `linux/amd64` and `linux/arm64`

## Supported providers

The V1 configuration includes the 16 providers currently represented by the source catalog:

| Provider | Key required? | Gateway compatibility base |
|---|---:|---|
| Aion Labs | Yes | `https://api.aionlabs.ai/v1` |
| Cohere | Yes | Cohere OpenAI Compatibility API |
| Google Gemini | Yes | Gemini OpenAI Compatibility API |
| Mistral AI | Yes | `https://api.mistral.ai/v1` |
| Z AI (Zhipu AI) | Yes | `https://open.bigmodel.cn/api/paas/v4` |
| Cloudflare Workers AI | Yes + Account ID | Workers AI OpenAI-compatible endpoint |
| Groq | Yes | `https://api.groq.com/openai/v1` |
| Hugging Face | Yes | `https://router.huggingface.co/v1` |
| Kilo Code | Optional for some free routes | `https://api.kilo.ai/api/gateway` |
| LLM7.io | Optional | `https://api.llm7.io/v1` |
| ModelScope | Yes | `https://api-inference.modelscope.cn/v1` |
| NVIDIA NIM | Yes | `https://integrate.api.nvidia.com/v1` |
| Ollama Cloud | Yes | `https://ollama.com/v1` |
| OpenRouter | Yes | `https://openrouter.ai/api/v1` |
| OVHcloud AI Endpoints | Optional for anonymous tier | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` |
| SiliconFlow | Yes | `https://api.siliconflow.cn/v1` |

Provider APIs change. The dashboard therefore has a **Base URL override** field for every provider, and a **Sync provider catalog** action that refreshes model metadata from the upstream project.

---

# Fastest way to test — no VPS required

## Option A: GitHub Codespaces (recommended for your first test)

You do **not** need to rent a Linux server.

1. Open this repository on GitHub.
2. Click **Code**.
3. Open the **Codespaces** tab.
4. Click **Create codespace on main**.
5. Wait for the Codespace terminal to open.
6. Run:

```bash
docker compose up -d --build
```

7. Check the container:

```bash
docker compose ps
```

8. Test health:

```bash
curl http://127.0.0.1:8080/health
```

Expected response:

```json
{"status":"ok","app":"FreeLLM Gateway","version":"0.1.0","setup":false}
```

9. GitHub Codespaces should automatically forward port **8080** and offer **Open in Browser**. If it does not, open the **Ports** tab and open port `8080` manually.
10. Complete the first-time setup in the browser.

### Stop it in Codespaces

```bash
docker compose down
```

### Delete all local FreeLLM data in Codespaces

```bash
docker compose down -v
```

---

# Linux / VPS installation

There are two installation modes.

## Mode 1: Run the published image

Use this when the GHCR image is available to your machine.

```bash
docker run -d \
  --name freellm \
  --restart unless-stopped \
  -p 8080:8080 \
  -v freellm-data:/data \
  ghcr.io/newaran/freellm:latest
```

Then open:

```text
http://SERVER_IP:8080
```

On the same computer:

```text
http://127.0.0.1:8080
```

### Important: this repository is currently private

A private repository normally produces a private GHCR package. A machine outside GitHub may need to authenticate before it can pull the image:

```bash
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
docker pull ghcr.io/newaran/freellm:latest
```

Use a GitHub token with the minimum package-read permission needed for your setup. **Do not paste tokens into shell history on shared machines.**

If you later make the repository/package public, normal users can pull without this login step.

## Mode 2: Build directly from the repository

This is the simplest option while the project is private and you are using Codespaces or an authenticated Git clone.

```bash
git clone https://github.com/NewAran/FreeLLM.git
cd FreeLLM
docker compose up -d --build
```

Then open `http://SERVER_IP:8080`.

---

# One-line installer

`install.sh` pulls the GHCR image, creates the persistent Docker volume, replaces an old container if one exists, starts the new container, and waits for `/health`.

When the repository/package is public:

```bash
curl -fsSL https://raw.githubusercontent.com/NewAran/FreeLLM/main/install.sh | bash
```

Because this repo is currently private, the raw GitHub URL will require GitHub authentication and the GHCR package may also require `docker login`. For now, the recommended private-repo flow is **Codespaces + `docker compose up -d --build`**.

The installer supports overrides:

```bash
FREELLM_PORT=9000 FREELLM_IMAGE=ghcr.io/newaran/freellm:latest ./install.sh
```

---

# First-time web setup

Open the dashboard and create:

1. A **dashboard password** (minimum 8 characters).
2. A **FreeLLM gateway API key**, or leave the field empty and let FreeLLM generate one.

If FreeLLM generates the key, copy it immediately. Only its SHA-256 hash is stored; the plaintext gateway key is not recoverable later. You can rotate it from the dashboard.

Then configure providers. For each provider:

1. Click its **Get key** link.
2. Obtain an official API key/token from that provider.
3. Enter only the API credentials the provider officially exposes. Do not enter your normal account password.
4. Set **Enabled**.
5. Choose a priority. Lower numbers are attempted first.
6. Click **Save**.
7. Click **Test**.

Cloudflare also needs the **Account ID** because its compatibility URL contains the account identifier.

Provider credentials are encrypted before they are stored in the SQLite database inside `/data`. The encryption master key is stored in `/data/master.key` unless `FREELLM_MASTER_KEY` is provided explicitly.

---

# Use the unified API

## cURL

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_FREELLM_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Explain what an API gateway is in two sentences."}
    ]
  }'
```

FreeLLM adds these response headers when possible:

```text
x-freellm-provider: groq
x-freellm-model: openai/gpt-oss-120b
```

They show which upstream provider/model actually served the request.

## Python with the OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8080/v1",
    api_key="YOUR_FREELLM_KEY",
)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
)

print(response.choices[0].message.content)
```

## JavaScript / Node.js

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:8080/v1",
  apiKey: "YOUR_FREELLM_KEY",
});

const response = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Hello!" }],
});

console.log(response.choices[0].message.content);
```

## Streaming

```python
stream = client.chat.completions.create(
    model="auto-fast",
    messages=[{"role": "user", "content": "Write three short tips."}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

---

# Model routing

## `auto`

Tries enabled providers by configured priority and picks a known model from each provider until one succeeds.

## `auto-fast`

Like `auto`, with a routing preference for providers configured for fast inference (currently Groq receives the largest preference).

## `auto-code`

Chooses models whose source metadata or model ID indicates coding capability.

## `auto-reasoning`

Chooses reasoning-oriented models when available.

## `auto-vision`

Chooses models whose metadata indicates image/vision/multimodal support.

## Direct provider + model

```text
groq::openai/gpt-oss-120b
```

Example:

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_FREELLM_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google::gemini-2.5-flash",
    "messages": [{"role":"user","content":"Hello"}]
  }'
```

Direct routing does not switch to a different provider if that selected provider fails.

## List models

```bash
curl http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer YOUR_FREELLM_KEY"
```

---

# How fallback works

For automatic routes, FreeLLM:

1. Builds a candidate list from **enabled** providers.
2. Skips providers in temporary cooldown.
3. Selects a model matching the requested auto mode.
4. Calls the first candidate.
5. If the provider rejects/fails the request, FreeLLM records the failure and tries the next candidate.
6. HTTP `429` and `503` temporarily place a provider in cooldown.
7. A successful response records latency and clears the last error.

FreeLLM does **not** attempt to bypass upstream rate limits. It simply uses another provider you have legitimately configured when one provider is unavailable or has reached its normal limit.

---

# Useful Docker commands

## Status

```bash
docker ps --filter name=freellm
```

With Compose:

```bash
docker compose ps
```

## Logs

```bash
docker logs -f freellm
```

Compose:

```bash
docker compose logs -f
```

## Restart

```bash
docker restart freellm
```

## Stop

```bash
docker stop freellm
```

## Start again

```bash
docker start freellm
```

## Remove container but keep configuration/data

```bash
docker rm -f freellm
```

The named volume `freellm-data` remains.

## Remove everything including saved keys/config

```bash
docker rm -f freellm 2>/dev/null || true
docker volume rm freellm-data
```

This permanently deletes the FreeLLM database and encryption key.

---

# Update FreeLLM

For an image-based deployment:

```bash
docker pull ghcr.io/newaran/freellm:latest
docker rm -f freellm
docker run -d \
  --name freellm \
  --restart unless-stopped \
  -p 8080:8080 \
  -v freellm-data:/data \
  ghcr.io/newaran/freellm:latest
```

Your configuration remains in `freellm-data`.

With Compose from a local checkout:

```bash
git pull
docker compose up -d --build
```

---

# Backup and restore

The important persistent data lives in the named Docker volume.

## Backup

```bash
docker run --rm \
  -v freellm-data:/data:ro \
  -v "$PWD":/backup \
  alpine \
  tar czf /backup/freellm-backup.tgz -C /data .
```

Keep the backup private: it contains the encrypted provider credentials **and** the local master key needed to decrypt them.

## Restore

Stop FreeLLM first, then:

```bash
docker volume create freellm-data
docker run --rm \
  -v freellm-data:/data \
  -v "$PWD":/backup \
  alpine \
  sh -c 'cd /data && tar xzf /backup/freellm-backup.tgz'
```

Start the container again.

---

# Environment variables

| Variable | Default | Description |
|---|---|---|
| `FREELLM_DATA_DIR` | `/data` | Persistent data directory |
| `FREELLM_REQUEST_TIMEOUT` | `90` | Upstream request timeout in seconds |
| `FREELLM_COOLDOWN_SECONDS` | `60` | Cooldown after selected upstream failures |
| `FREELLM_ADMIN_TOKEN_TTL` | `43200` | Dashboard login token lifetime in seconds |
| `FREELLM_CATALOG_URL` | upstream `data.json` | Model catalog source |
| `FREELLM_MASTER_KEY` | generated in `/data/master.key` | Optional external encryption master key |
| `FREELLM_PORT` | `8080` | Host port used by Compose/install script |

If you provide `FREELLM_MASTER_KEY`, it must decode to exactly 32 bytes of URL-safe base64 data. Do not change/remove it after credentials are stored or those encrypted credentials will no longer be decryptable.

---

# GitHub Actions

Two workflows are included.

## `CI`

Runs on Ubuntu for pushes and pull requests:

- Installs Python dependencies
- Runs unit tests
- Compiles Python modules
- Builds the Docker image
- Starts the container on a Linux GitHub runner
- Checks `/health`
- Checks the web page
- Performs first-time setup
- Restarts the container
- Verifies that setup state persisted through the Docker volume

This is the main answer to **"How do I test Linux/Docker before buying a VPS?"**: every push can run an actual Docker smoke test on GitHub's Linux runner.

## `Publish container`

On `main` and version tags, it builds multi-architecture images and pushes them to:

```text
ghcr.io/newaran/freellm
```

Architectures:

```text
linux/amd64
linux/arm64
```

For a private repository/package, external pulls may require GHCR authentication.

---

# Security notes

- FreeLLM asks for provider **API keys/tokens**, not provider account passwords.
- Provider credential JSON is encrypted at rest with Fernet authenticated encryption.
- The gateway API key is stored only as a SHA-256 hash.
- The dashboard password is stored as a salted PBKDF2-SHA256 hash.
- The local encryption key is persisted separately in `/data/master.key` with restrictive permissions where supported.
- Dashboard session tokens are HMAC-signed and expire.
- The container runs as a non-root user.
- No telemetry is implemented by FreeLLM V1.
- Provider requests still go to the provider you configure; review each provider's privacy/data-use terms before sending sensitive data.

For internet-facing VPS use, do not leave plain HTTP port 8080 exposed as your final production setup. Put FreeLLM behind HTTPS (for example, a reverse proxy or secure tunnel), restrict network access to the dashboard where practical, and use strong keys/passwords.

---

# Troubleshooting

## `docker: command not found`

Install Docker Engine or use GitHub Codespaces, where this repository's devcontainer enables Docker-in-Docker.

## Port 8080 is already in use

Compose:

```bash
FREELLM_PORT=9000 docker compose up -d --build
```

Then open port `9000`.

## Provider test says 401 / 403

Usually the API key/token is wrong, expired, missing a required permission, or the provider requires account setup. Generate/verify the key on the provider's official dashboard and save it again.

## Provider test says 404 on `/models`

Some OpenAI-compatible providers do not expose a standard model-list endpoint even when Chat Completions works. The dashboard test is a convenience check, not the source of truth. Try a direct chat request with a model listed by that provider.

## `All candidate providers failed`

Check:

```bash
docker logs --tail 200 freellm
```

Then open the dashboard and inspect each provider's **Last error**, key, enabled state and base URL.

## Catalog sync fails

FreeLLM continues using its built-in catalog. Sync only refreshes model metadata; it is not required for the server to boot.

## GHCR pull denied

The package is probably private. Authenticate with GitHub Container Registry or build locally from the repository.

---

# Development

Local Python development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
FREELLM_DATA_DIR=./data uvicorn app.main:app --reload --port 8080
```

Tests:

```bash
pytest -q
```

Docker build:

```bash
docker build -t freellm:dev .
docker run --rm -p 8080:8080 -v freellm-dev-data:/data freellm:dev
```

---

# API surface in V1

Public/local UI:

```text
GET  /
GET  /health
GET  /docs
```

Setup/admin API:

```text
GET  /api/status
POST /api/setup
POST /api/login
GET  /api/providers
PUT  /api/providers/{slug}
POST /api/providers/{slug}/test
POST /api/catalog/sync
POST /api/gateway-key/rotate
```

OpenAI-compatible gateway:

```text
GET  /v1/models
POST /v1/chat/completions
```

---

# Known V1 limitations

- Free-tier quotas are displayed/sourced as metadata but are not perfectly metered locally because provider quota rules differ and can change.
- Automatic fallback works at request/start-of-stream time; once a provider has begun a successful stream, FreeLLM does not splice a second provider into the middle of that stream.
- V1 focuses on Chat Completions. Embeddings, images, audio, Responses API compatibility and per-user API keys can be added later.
- Some providers advertise OpenAI compatibility differently from their catalog base URL. FreeLLM ships compatibility URLs for Gemini, Cohere, Cloudflare and Ollama; every provider also has a manual base-URL override.

---

# Credits and source catalog

Model/provider metadata is based on the CC0-licensed project:

- [`mnfst/awesome-free-llm-apis`](https://github.com/mnfst/awesome-free-llm-apis)

FreeLLM is a separate gateway project and is not affiliated with the listed model/API providers.

## License

MIT. See [`LICENSE`](LICENSE).
