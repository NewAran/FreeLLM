from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from .catalog import catalog, model_kind, provider_by_slug
from .config import COOLDOWN_SECONDS, REQUEST_TIMEOUT_SECONDS
from .security import decrypt_json
from .storage import Storage


@dataclass
class Candidate:
    slug: str
    model: str
    base_url: str
    credentials: dict[str, str]
    priority: int


class GatewayRouter:
    def __init__(self, storage: Storage, master_key: bytes):
        self.storage = storage
        self.master_key = master_key

    def _enabled_configs(self) -> list[dict[str, Any]]:
        return [p for p in self.storage.list_providers() if p.get("enabled")]

    def _credentials(self, row: dict) -> dict[str, str]:
        return decrypt_json(self.master_key, row.get("credentials_enc"))

    def _base_url(self, slug: str, row: dict, credentials: dict[str, str]) -> str:
        provider = provider_by_slug(slug)
        if not provider:
            raise ValueError(f"Unknown provider: {slug}")
        base = row.get("base_url_override") or provider["base_url"]
        try:
            return base.format(**credentials).rstrip("/")
        except KeyError as exc:
            raise ValueError(f"Missing credential field for base URL: {exc.args[0]}") from exc

    def _headers(self, credentials: dict[str, str]) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": "FreeLLM-Gateway/0.1"}
        api_key = credentials.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def candidates(self, requested_model: str) -> list[Candidate]:
        enabled = self._enabled_configs()
        if not enabled:
            raise HTTPException(status_code=503, detail="No providers are enabled. Configure one in the dashboard.")

        direct_slug = None
        actual_model = requested_model
        if "::" in requested_model:
            direct_slug, actual_model = requested_model.split("::", 1)

        providers = {p["slug"]: p for p in catalog()}
        details_by_provider = {
            p["slug"]: {m.get("id"): m for m in p.get("model_details", [])}
            for p in catalog()
        }
        stats = self.storage.all_stats()
        now = int(time.time())
        result: list[Candidate] = []

        for row in enabled:
            slug = row["slug"]
            if direct_slug and slug != direct_slug:
                continue
            provider = providers.get(slug)
            if not provider:
                continue
            stat = stats.get(slug, {})
            if not direct_slug and int(stat.get("cooldown_until") or 0) > now:
                continue
            creds = self._credentials(row)
            try:
                base_url = self._base_url(slug, row, creds)
            except ValueError:
                continue

            model = actual_model
            if requested_model.startswith("auto"):
                wanted = "general"
                if requested_model == "auto-code": wanted = "code"
                elif requested_model == "auto-reasoning": wanted = "reasoning"
                elif requested_model == "auto-vision": wanted = "vision"
                selected = None
                for mid in provider.get("models", []):
                    if wanted == "general" or wanted in model_kind(mid, details_by_provider[slug].get(mid)):
                        selected = mid
                        break
                if not selected:
                    continue
                model = selected
            elif not direct_slug:
                if actual_model not in provider.get("models", []):
                    continue

            priority = int(row.get("priority") or 100)
            if requested_model == "auto-fast":
                priority += {"groq": -30, "cloudflare": -10, "kilo": -5}.get(slug, 0)
            latency = stat.get("last_latency_ms")
            latency_penalty = int(latency / 1000) if latency else 0
            failure_penalty = min(int(stat.get("failure_count") or 0), 20)
            result.append(Candidate(slug, model, base_url, creds, priority + latency_penalty + failure_penalty))

        result.sort(key=lambda c: c.priority)
        if not result:
            if direct_slug:
                raise HTTPException(status_code=404, detail=f"Provider '{direct_slug}' is not enabled or configured.")
            raise HTTPException(status_code=503, detail=f"No configured provider can serve model '{requested_model}'.")
        return result

    async def chat(self, payload: dict[str, Any]):
        requested_model = str(payload.get("model") or "auto")
        is_stream = bool(payload.get("stream"))
        candidates = self.candidates(requested_model)
        errors = []

        for candidate in candidates:
            outbound = dict(payload)
            outbound["model"] = candidate.model
            url = f"{candidate.base_url}/chat/completions"
            started = time.perf_counter()
            client = httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=15), follow_redirects=True)
            try:
                request = client.build_request("POST", url, headers=self._headers(candidate.credentials), json=outbound)
                response = await client.send(request, stream=is_stream)
                latency_ms = int((time.perf_counter() - started) * 1000)
                if 200 <= response.status_code < 300:
                    self.storage.record_success(candidate.slug, latency_ms)
                    if is_stream:
                        async def iterator(resp=response, cli=client) -> AsyncIterator[bytes]:
                            try:
                                async for chunk in resp.aiter_bytes():
                                    yield chunk
                            finally:
                                await resp.aclose()
                                await cli.aclose()
                        headers = {}
                        if response.headers.get("x-request-id"):
                            headers["x-upstream-request-id"] = response.headers["x-request-id"]
                        headers["x-freellm-provider"] = candidate.slug
                        headers["x-freellm-model"] = candidate.model
                        return StreamingResponse(iterator(), status_code=response.status_code, media_type=response.headers.get("content-type", "text/event-stream"), headers=headers)
                    content = await response.aread()
                    await response.aclose()
                    await client.aclose()
                    return Response(
                        content=content,
                        status_code=response.status_code,
                        media_type=response.headers.get("content-type", "application/json"),
                        headers={"x-freellm-provider": candidate.slug, "x-freellm-model": candidate.model},
                    )

                body = (await response.aread()).decode(errors="replace")[:800]
                await response.aclose()
                await client.aclose()
                cooldown = int(time.time()) + COOLDOWN_SECONDS if response.status_code in (429, 503) else 0
                error = f"HTTP {response.status_code}: {body}"
                self.storage.record_failure(candidate.slug, error, cooldown)
                errors.append({"provider": candidate.slug, "status": response.status_code, "error": body[:300]})
                if "::" in requested_model:
                    break
            except Exception as exc:
                await client.aclose()
                error = f"{type(exc).__name__}: {exc}"
                self.storage.record_failure(candidate.slug, error, int(time.time()) + 15)
                errors.append({"provider": candidate.slug, "error": str(exc)[:300]})
                if "::" in requested_model:
                    break

        raise HTTPException(status_code=502, detail={"message": "All candidate providers failed", "attempts": errors})

    async def test_provider(self, slug: str) -> dict[str, Any]:
        row = self.storage.get_provider(slug)
        provider = provider_by_slug(slug)
        if not provider:
            raise HTTPException(status_code=404, detail="Unknown provider")
        if not row:
            return {"ok": False, "status": "not_configured"}
        credentials = self._credentials(row)
        if provider.get("anonymous") and not credentials.get("api_key"):
            return {"ok": True, "status": "anonymous", "message": "Provider supports anonymous/free access; live model listing was skipped."}
        try:
            base_url = self._base_url(slug, row, credentials)
            started = time.perf_counter()
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(f"{base_url}/models", headers=self._headers(credentials))
            latency = int((time.perf_counter() - started) * 1000)
            if 200 <= response.status_code < 300:
                self.storage.record_success(slug, latency)
                return {"ok": True, "status": "connected", "latency_ms": latency}
            self.storage.record_failure(slug, f"Test HTTP {response.status_code}: {response.text[:500]}")
            return {"ok": False, "status": "failed", "http_status": response.status_code, "message": response.text[:300]}
        except Exception as exc:
            self.storage.record_failure(slug, f"Test error: {exc}")
            return {"ok": False, "status": "failed", "message": str(exc)}
