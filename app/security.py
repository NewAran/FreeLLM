from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from cryptography.fernet import Fernet


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_gateway_key() -> str:
    return "flm_" + secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 250_000)
    return f"pbkdf2_sha256$250000${_b64url(salt)}${_b64url(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), _b64url_decode(salt), int(rounds)
        )
        return hmac.compare_digest(_b64url(digest), expected)
    except Exception:
        return False


def load_or_create_master_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    env_key = os.getenv("FREELLM_MASTER_KEY")
    if env_key:
        try:
            return _b64url_decode(env_key)
        except Exception as exc:
            raise RuntimeError("FREELLM_MASTER_KEY must be url-safe base64") from exc
    if path.exists():
        return path.read_bytes()
    key = os.urandom(32)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def _fernet(master_key: bytes) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(master_key))


def encrypt_json(master_key: bytes, value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return _fernet(master_key).encrypt(raw).decode()


def decrypt_json(master_key: bytes, token: str | None) -> dict:
    if not token:
        return {}
    return json.loads(_fernet(master_key).decrypt(token.encode()).decode())


def make_admin_token(master_key: bytes, ttl_seconds: int) -> str:
    payload = {"scope": "admin", "exp": int(time.time()) + ttl_seconds}
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64url(hmac.new(master_key, body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_admin_token(master_key: bytes, token: str) -> bool:
    try:
        body, signature = token.split(".", 1)
        expected = _b64url(hmac.new(master_key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(_b64url_decode(body))
        return payload.get("scope") == "admin" and int(payload.get("exp", 0)) > int(time.time())
    except Exception:
        return False
