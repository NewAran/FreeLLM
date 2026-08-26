from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

from .config import CATALOG_CACHE_PATH, SOURCE_CATALOG_URL


def _p(slug, name, base_url, key_url, credential_fields, models, description="", anonymous=False):
    return {
        "slug": slug,
        "name": name,
        "base_url": base_url,
        "key_url": key_url,
        "credential_fields": credential_fields,
        "models": models,
        "description": description,
        "anonymous": anonymous,
    }


BUILTIN_PROVIDERS = [
    _p("aion", "Aion Labs", "https://api.aionlabs.ai/v1", "https://www.aionlabs.ai/app/api-keys/", [{"name":"api_key","label":"API Key","secret":True,"required":True}], ["aion-labs/aion-2.0","aion-labs/aion-rp-llama-3.1-8b","aion-labs/aion-3.0","aion-labs/aion-3.0-mini"], "Permanent free tier; specialized models."),
    _p("cohere", "Cohere", "https://api.cohere.ai/compatibility/v1", "https://dashboard.cohere.com/api-keys", [{"name":"api_key","label":"API Key","secret":True,"required":True}], ["command-a-plus-05-2026","command-a-03-2025","command-r-plus-08-2024","command-r-08-2024","command-r7b-12-2024","command-a-reasoning-08-2025","command-a-translate-08-2025","command-a-vision-07-2025","command-r7b-arabic-02-2025","c4ai-aya-expanse-32b","c4ai-aya-vision-32b"], "Cohere OpenAI Compatibility API."),
    _p("google", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "https://aistudio.google.com/app/apikey", [{"name":"api_key","label":"Gemini API Key","secret":True,"required":True}], ["gemini-3.7-flash","gemini-3.6-flash","gemini-3.5-flash","gemini-3.5-flash-lite","gemini-3.1-flash-lite","gemini-2.5-flash","gemini-2.5-flash-lite","gemini-2.5-pro","gemma-4-31b-it","gemma-4-26b-a4b-it"], "Gemini OpenAI compatibility endpoint."),
    _p("mistral", "Mistral AI", "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys", [{"name":"api_key","label":"API Key","secret":True,"required":True}], ["mistral-medium-3-5","mistral-small-2603","mistral-large-2512","ministral-8b-2512","codestral-2508","ministral-3b-2512","ministral-14b-2512"]),
    _p("zai", "Z AI (Zhipu AI)", "https://open.bigmodel.cn/api/paas/v4", "https://open.bigmodel.cn/usercenter/apikeys", [{"name":"api_key","label":"API Key","secret":True,"required":True}], ["glm-4.7-flash","glm-4.5-flash","glm-4.6v-flash"]),
    _p("cloudflare", "Cloudflare Workers AI", "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1", "https://dash.cloudflare.com/profile/api-tokens", [{"name":"account_id","label":"Account ID","secret":False,"required":True},{"name":"api_key","label":"API Token","secret":True,"required":True}], ["@cf/meta/llama-3.3-70b-instruct-fp8-fast","@cf/meta/llama-4-scout-17b-16e-instruct","@cf/openai/gpt-oss-120b","@cf/google/gemma-4-26b-a4b-it","@cf/zai-org/glm-4.7-flash","@cf/mistralai/mistral-small-3.1-24b-instruct","@cf/deepseek-ai/deepseek-r1-distill-qwen-32b"], "10,000 neurons/day free tier."),
    _p("groq", "Groq", "https://api.groq.com/openai/v1", "https://console.groq.com/keys", [{"name":"api_key","label":"API Key","secret":True,"required":True}], ["openai/gpt-oss-120b","openai/gpt-oss-20b","groq/compound","groq/compound-mini","qwen/qwen3.6-27b"], "Ultra-fast inference."),
    _p("huggingface", "Hugging Face", "https://router.huggingface.co/v1", "https://huggingface.co/settings/tokens", [{"name":"api_key","label":"Access Token","secret":True,"required":True}], ["meta-llama/Llama-3.1-8B-Instruct","google/gemma-3-4b-it","microsoft/phi-4","Qwen/Qwen2.5-Coder-7B-Instruct","Qwen/Qwen2.5-7B-Instruct"]),
    _p("kilo", "Kilo Code", "https://api.kilo.ai/api/gateway", "https://app.kilo.ai/profile", [{"name":"api_key","label":"API Key (optional)","secret":True,"required":False}], ["kilo-auto/free","nvidia/nemotron-3-ultra-550b-a55b:free","stepfun/step-3.7-flash:free","nvidia/nemotron-3-super-120b-a12b:free","nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free","poolside/laguna-s-2.1:free","poolside/laguna-xs-2.1:free","cohere/north-mini-code:free","openrouter/free","tencent/hy3:free","nvidia/nemotron-3.5-lightning:free","liquid/lfm-2.5-2.6b:free"], "Some free routes may work without a key.", True),
    _p("llm7", "LLM7.io", "https://api.llm7.io/v1", "https://token.llm7.io", [{"name":"api_key","label":"Free Token (optional)","secret":True,"required":False}], ["gpt-oss:20b","mistral-Nemo-Instruct-2407","minimax-m2.7"], "Anonymous access supported with lower limits.", True),
    _p("modelscope", "ModelScope", "https://api-inference.modelscope.cn/v1", "https://modelscope.cn/my/myaccesstoken", [{"name":"api_key","label":"Access Token","secret":True,"required":True}], ["Qwen/Qwen3.5-35B-A3B","Qwen/Qwen3.5-27B"]),
    _p("nvidia", "NVIDIA NIM", "https://integrate.api.nvidia.com/v1", "https://build.nvidia.com/explore/discover", [{"name":"api_key","label":"NVIDIA API Key","secret":True,"required":True}], ["nvidia/nemotron-3-super-120b-a12b","nvidia/nemotron-3-nano-30b-a3b","nvidia/llama-3.1-nemotron-ultra-253b-v1","meta/llama-3.3-70b-instruct","mistralai/mistral-nemotron","google/gemma-4-31b-it","mistralai/mistral-large-2-instruct","minimaxai/minimax-m3","nvidia/nemotron-3-ultra-550b-a55b","openai/gpt-oss-120b","openai/gpt-oss-20b"]),
    _p("ollama", "Ollama Cloud", "https://ollama.com/v1", "https://ollama.com/settings/keys", [{"name":"api_key","label":"API Key","secret":True,"required":True}], ["deepseek-v4-pro","deepseek-v4-flash","minimax-m3","kimi-k3","gpt-oss:120b","gpt-oss:20b","nemotron-3-ultra","mistral-large-3:675b","qwen3.5:397b"]),
    _p("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/keys", [{"name":"api_key","label":"API Key","secret":True,"required":True}], ["nvidia/nemotron-3-super-120b-a12b:free","openai/gpt-oss-20b:free","cohere/north-mini-code:free","google/gemma-4-26b-a4b-it:free","google/gemma-4-31b-it:free","inclusionai/ling-3.0-flash:free","nvidia/nemotron-3-nano-30b-a3b:free","nvidia/nemotron-nano-9b-v2:free","nvidia/nemotron-nano-12b-v2-vl:free","poolside/laguna-s-2.1:free","poolside/laguna-xs-2.1:free"]),
    _p("ovh", "OVHcloud AI Endpoints", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1", "https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/", [{"name":"api_key","label":"API Key (optional)","secret":True,"required":False}], ["Qwen3.5-397B-A17B","gpt-oss-120b","gpt-oss-20b","Meta-Llama-3_3-70B-Instruct","Qwen3.6-27B","Qwen3.5-9B","Qwen3-32B","Qwen3-Coder-30B-A3B-Instruct","Qwen2.5-VL-72B-Instruct","Mistral-Small-3.2-24B-Instruct-2506","Mistral-Nemo-Instruct-2407","Mistral-7B-Instruct-v0.3"], "Anonymous free tier is available.", True),
    _p("siliconflow", "SiliconFlow", "https://api.siliconflow.cn/v1", "https://cloud.siliconflow.cn/account/ak", [{"name":"api_key","label":"API Key","secret":True,"required":True}], ["Qwen/Qwen3-8B"]),
]

SLUG_BY_NAME = {p["name"].lower(): p["slug"] for p in BUILTIN_PROVIDERS}


def _normalize_source(data: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for provider in data.get("providers", []):
        slug = SLUG_BY_NAME.get(str(provider.get("name", "")).lower())
        if not slug:
            continue
        models = []
        for model in provider.get("models", []):
            if not model.get("id"):
                continue
            models.append({
                "id": model["id"],
                "name": model.get("name") or model["id"],
                "context": model.get("context"),
                "max_output": model.get("maxOutput"),
                "modality": model.get("modality"),
                "rate_limit": model.get("rateLimit"),
            })
        result[slug] = models
    return result


def load_cached_models(path: Path = CATALOG_CACHE_PATH) -> dict[str, list[dict]]:
    try:
        data = json.loads(path.read_text())
        return data.get("models", {})
    except Exception:
        return {}


def catalog() -> list[dict]:
    cached = load_cached_models()
    result = []
    for provider in BUILTIN_PROVIDERS:
        item = dict(provider)
        if provider["slug"] in cached:
            item["model_details"] = cached[provider["slug"]]
            item["models"] = [m["id"] for m in cached[provider["slug"]]]
        else:
            item["model_details"] = [{"id": m, "name": m} for m in provider["models"]]
        result.append(item)
    return result


def provider_by_slug(slug: str) -> dict | None:
    return next((p for p in catalog() if p["slug"] == slug), None)


async def sync_catalog(path: Path = CATALOG_CACHE_PATH) -> dict:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(SOURCE_CATALOG_URL)
        response.raise_for_status()
        data = response.json()
    normalized = _normalize_source(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": SOURCE_CATALOG_URL, "source_last_updated": data.get("lastUpdated"), "synced_at": int(time.time()), "models": normalized}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def cache_is_stale(path: Path = CATALOG_CACHE_PATH, max_age: int = 86400) -> bool:
    try:
        data = json.loads(path.read_text())
        return int(time.time()) - int(data.get("synced_at", 0)) > max_age
    except Exception:
        return True


def model_kind(model_id: str, details: dict | None = None) -> set[str]:
    text = " ".join([model_id, (details or {}).get("name", ""), (details or {}).get("modality", "")]).lower()
    kinds = {"general"}
    if re.search(r"coder|codestral|code\b|laguna", text):
        kinds.add("code")
    if re.search(r"reason|r1|gpt-oss|thinking", text):
        kinds.add("reasoning")
    if re.search(r"vision|image|multimodal|vl\b", text):
        kinds.add("vision")
    return kinds
