from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "FreeLLM Gateway"
APP_VERSION = "0.1.0"
DATA_DIR = Path(os.getenv("FREELLM_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "freellm.db"
MASTER_KEY_PATH = DATA_DIR / "master.key"
CATALOG_CACHE_PATH = DATA_DIR / "catalog.json"
SOURCE_CATALOG_URL = os.getenv(
    "FREELLM_CATALOG_URL",
    "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json",
)
ADMIN_TOKEN_TTL_SECONDS = int(os.getenv("FREELLM_ADMIN_TOKEN_TTL", "43200"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("FREELLM_REQUEST_TIMEOUT", "90"))
COOLDOWN_SECONDS = int(os.getenv("FREELLM_COOLDOWN_SECONDS", "60"))
