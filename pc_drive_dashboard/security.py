import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any


PBKDF2_ITERATIONS = 390_000


class SecurityStore:
    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def is_configured(self) -> bool:
        return bool(self._read().get("password_hash"))

    def set_password(self, password: str) -> None:
        if len(password) < 10:
            raise ValueError("Password must be at least 10 characters.")

        config = self._read()
        salt = secrets.token_bytes(16)
        digest = self._pbkdf2(password, salt)
        config["password_hash"] = {
            "algorithm": "pbkdf2_sha256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": _b64encode(salt),
            "hash": _b64encode(digest),
        }
        config.setdefault("trusted_tokens", [])
        self._write(config)

    def verify_password(self, password: str) -> bool:
        password_hash = self._read().get("password_hash")
        if not password_hash:
            return False

        if password_hash.get("algorithm") != "pbkdf2_sha256":
            return False

        salt = _b64decode(password_hash["salt"])
        expected = _b64decode(password_hash["hash"])
        actual = self._pbkdf2(password, salt, int(password_hash["iterations"]))
        return hmac.compare_digest(actual, expected)

    def create_trusted_token(self, name: str, ttl_seconds: int, now: float | None = None) -> str:
        timestamp = time.time() if now is None else now
        token = secrets.token_urlsafe(48)
        config = self._read()
        tokens = config.setdefault("trusted_tokens", [])
        tokens.append(
            {
                "id": str(uuid.uuid4()),
                "name": name[:120] or "Trusted browser",
                "token_hash": self._hash_token(token),
                "created_at": timestamp,
                "expires_at": timestamp + ttl_seconds,
                "last_seen": None,
                "revoked_at": None,
            }
        )
        self._write(config)
        return token

    def verify_trusted_token(self, token: str | None, now: float | None = None) -> bool:
        if not token:
            return False

        timestamp = time.time() if now is None else now
        token_hash = self._hash_token(token)
        config = self._read()
        matched = False

        for trusted in config.get("trusted_tokens", []):
            if not hmac.compare_digest(trusted.get("token_hash", ""), token_hash):
                continue
            if trusted.get("revoked_at") is not None:
                return False
            if float(trusted.get("expires_at", 0)) <= timestamp:
                return False
            trusted["last_seen"] = timestamp
            matched = True
            break

        if matched:
            self._write(config)

        return matched

    def revoke_token(self, token: str, now: float | None = None) -> bool:
        token_hash = self._hash_token(token)
        return self.revoke_token_hash(token_hash, now=now)

    def revoke_token_id(self, token_id: str, now: float | None = None) -> bool:
        timestamp = time.time() if now is None else now
        config = self._read()
        revoked = False
        for trusted in config.get("trusted_tokens", []):
            if trusted.get("id") == token_id:
                trusted["revoked_at"] = timestamp
                revoked = True
        if revoked:
            self._write(config)
        return revoked

    def revoke_token_hash(self, token_hash: str, now: float | None = None) -> bool:
        timestamp = time.time() if now is None else now
        config = self._read()
        revoked = False
        for trusted in config.get("trusted_tokens", []):
            if hmac.compare_digest(trusted.get("token_hash", ""), token_hash):
                trusted["revoked_at"] = timestamp
                revoked = True
        if revoked:
            self._write(config)
        return revoked

    def list_trusted_tokens(self, now: float | None = None) -> list[dict[str, Any]]:
        timestamp = time.time() if now is None else now
        items = []
        for trusted in self._read().get("trusted_tokens", []):
            items.append(
                {
                    "id": trusted.get("id"),
                    "name": trusted.get("name"),
                    "created_at": trusted.get("created_at"),
                    "expires_at": trusted.get("expires_at"),
                    "last_seen": trusted.get("last_seen"),
                    "revoked_at": trusted.get("revoked_at"),
                    "active": trusted.get("revoked_at") is None
                    and float(trusted.get("expires_at", 0)) > timestamp,
                }
            )
        return items

    def token_hash(self, token: str) -> str:
        return self._hash_token(token)

    def _pbkdf2(
        self, password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS
    ) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _read(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"trusted_tokens": []}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _write(self, config: dict[str, Any]) -> None:
        temp_path = self.config_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.config_path)


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))
