from app.catalog import BUILTIN_PROVIDERS, model_kind


def test_provider_catalog_has_all_source_providers():
    slugs = {p["slug"] for p in BUILTIN_PROVIDERS}
    assert len(slugs) == 16
    assert {"google", "groq", "mistral", "cloudflare", "openrouter", "nvidia", "ovh"} <= slugs


def test_model_classification():
    assert "code" in model_kind("Qwen3-Coder-30B-A3B-Instruct")
    assert "reasoning" in model_kind("deepseek-r1-distill-qwen")
    assert "vision" in model_kind("qwen-vl", {"modality": "Text + Vision"})
