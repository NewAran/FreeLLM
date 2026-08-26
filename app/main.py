from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .catalog import BUILTIN_PROVIDERS, cache_is_stale, catalog, provider_by_slug, sync_catalog
from .config import ADMIN_TOKEN_TTL_SECONDS, APP_NAME, APP_VERSION, DB_PATH, MASTER_KEY_PATH
from .router import GatewayRouter
from .security import decrypt_json, encrypt_json, hash_api_key, hash_password, load_or_create_master_key, make_admin_token, new_gateway_key, verify_admin_token, verify_password
from .storage import Storage

storage = Storage(DB_PATH)
master_key = load_or_create_master_key(MASTER_KEY_PATH)
router = GatewayRouter(storage, master_key)
app = FastAPI(title=APP_NAME, version=APP_VERSION, docs_url="/docs", redoc_url=None)


class SetupRequest(BaseModel):
    admin_password: str = Field(min_length=8, max_length=256)
    gateway_api_key: str | None = Field(default=None, min_length=12, max_length=512)


class LoginRequest(BaseModel):
    password: str


class ProviderUpdate(BaseModel):
    enabled: bool = True
    priority: int = Field(default=100, ge=1, le=1000)
    base_url_override: str | None = None
    credentials: dict[str, str] = Field(default_factory=dict)


def require_admin(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Admin login required")
    if not verify_admin_token(master_key, authorization.split(" ", 1)[1]):
        raise HTTPException(status_code=401, detail="Invalid or expired admin token")


def require_gateway(authorization: str | None = Header(default=None)) -> None:
    if not storage.is_setup():
        raise HTTPException(status_code=503, detail="Gateway setup is not complete")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Gateway API key required")
    supplied = authorization.split(" ", 1)[1]
    expected = storage.get_setting("gateway_api_key_hash")
    if not expected or hash_api_key(supplied) != expected:
        raise HTTPException(status_code=401, detail="Invalid gateway API key")


@app.on_event("startup")
async def startup() -> None:
    storage.init()
    if cache_is_stale():
        try:
            await sync_catalog()
        except Exception:
            pass


@app.get("/health")
async def health():
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION, "setup": storage.is_setup()}


@app.get("/")
async def index():
    return FileResponse("app/static/index.html")


@app.get("/api/status")
async def status():
    return {"setup_required": not storage.is_setup(), "version": APP_VERSION, "provider_count": len(BUILTIN_PROVIDERS)}


@app.post("/api/setup")
async def setup(body: SetupRequest):
    if storage.is_setup():
        raise HTTPException(status_code=409, detail="Setup is already complete")
    gateway_key = body.gateway_api_key or new_gateway_key()
    storage.set_setting("admin_password_hash", hash_password(body.admin_password))
    storage.set_setting("gateway_api_key_hash", hash_api_key(gateway_key))
    for idx, provider in enumerate(BUILTIN_PROVIDERS, start=1):
        storage.save_provider(provider["slug"], False, idx * 10, None, None)
    token = make_admin_token(master_key, ADMIN_TOKEN_TTL_SECONDS)
    return {"ok": True, "admin_token": token, "gateway_api_key": gateway_key}


@app.post("/api/login")
async def login(body: LoginRequest):
    encoded = storage.get_setting("admin_password_hash")
    if not encoded or not verify_password(body.password, encoded):
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": make_admin_token(master_key, ADMIN_TOKEN_TTL_SECONDS), "expires_in": ADMIN_TOKEN_TTL_SECONDS}


@app.post("/api/gateway-key/rotate", dependencies=[Depends(require_admin)])
async def rotate_gateway_key():
    key = new_gateway_key()
    storage.set_setting("gateway_api_key_hash", hash_api_key(key))
    return {"gateway_api_key": key}


def _provider_view(provider: dict, stats: dict[str, dict[str, Any]]) -> dict:
    row = storage.get_provider(provider["slug"]) or {}
    creds = decrypt_json(master_key, row.get("credentials_enc")) if row.get("credentials_enc") else {}
    return {
        **provider,
        "enabled": bool(row.get("enabled", 0)),
        "priority": row.get("priority", 100),
        "base_url_override": row.get("base_url_override"),
        "configured": bool(creds) or bool(provider.get("anonymous")),
        "configured_fields": [k for k, v in creds.items() if v],
        "stats": stats.get(provider["slug"], {}),
    }


@app.get("/api/providers", dependencies=[Depends(require_admin)])
async def providers():
    stats = storage.all_stats()
    return [_provider_view(p, stats) for p in catalog()]


@app.put("/api/providers/{slug}", dependencies=[Depends(require_admin)])
async def update_provider(slug: str, body: ProviderUpdate):
    provider = provider_by_slug(slug)
    if not provider:
        raise HTTPException(status_code=404, detail="Unknown provider")
    for field in provider["credential_fields"]:
        if field.get("required") and body.enabled:
            existing = storage.get_provider(slug)
            existing_creds = decrypt_json(master_key, existing.get("credentials_enc")) if existing and existing.get("credentials_enc") else {}
            if not (body.credentials.get(field["name"]) or existing_creds.get(field["name"])):
                raise HTTPException(status_code=422, detail=f"{field['label']} is required when enabling this provider")
    encrypted = encrypt_json(master_key, {k: v.strip() for k, v in body.credentials.items() if v.strip()}) if any(v.strip() for v in body.credentials.values()) else None
    storage.save_provider(slug, body.enabled, body.priority, body.base_url_override, encrypted)
    return {"ok": True}


@app.post("/api/providers/{slug}/test", dependencies=[Depends(require_admin)])
async def test_provider(slug: str):
    return await router.test_provider(slug)


@app.post("/api/catalog/sync", dependencies=[Depends(require_admin)])
async def sync():
    try:
        result = await sync_catalog()
        return {"ok": True, "source_last_updated": result.get("source_last_updated"), "providers_synced": len(result.get("models", {}))}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Catalog sync failed: {exc}") from exc


@app.get("/v1/models", dependencies=[Depends(require_gateway)])
async def models():
    rows = {r["slug"]: r for r in storage.list_providers() if r.get("enabled")}
    data = [
        {"id": "auto", "object": "model", "owned_by": "freellm"},
        {"id": "auto-fast", "object": "model", "owned_by": "freellm"},
        {"id": "auto-code", "object": "model", "owned_by": "freellm"},
        {"id": "auto-reasoning", "object": "model", "owned_by": "freellm"},
        {"id": "auto-vision", "object": "model", "owned_by": "freellm"},
    ]
    for provider in catalog():
        if provider["slug"] not in rows:
            continue
        for model in provider.get("models", []):
            data.append({"id": f"{provider['slug']}::{model}", "object": "model", "owned_by": provider["slug"]})
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions", dependencies=[Depends(require_gateway)])
async def chat_completions(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(payload, dict) or not payload.get("messages"):
        raise HTTPException(status_code=422, detail="messages is required")
    return await router.chat(payload)
