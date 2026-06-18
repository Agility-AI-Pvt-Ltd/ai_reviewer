import base64
import hashlib
import hmac
import secrets

from fastapi import HTTPException, status

from app.core.config import settings

_VERSION = "v1"
_NONCE_BYTES = 16


def _key() -> bytes:
    secret = settings.github_token_encryption_key or settings.effective_jwt_secret
    if not secret or secret == "dev-change-me":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub token encryption key is not configured.",
        )
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        chunks.append(
            hmac.new(
                key,
                nonce + counter.to_bytes(8, "big"),
                hashlib.sha256,
            ).digest()
        )
        counter += 1
    return b"".join(chunks)[:length]


def encrypt_secret(value: str) -> str:
    key = _key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    plaintext = value.encode("utf-8")
    keystream = _stream(key, nonce, len(plaintext))
    ciphertext = bytes(left ^ right for left, right in zip(plaintext, keystream, strict=True))
    mac = hmac.new(key, _VERSION.encode("ascii") + nonce + ciphertext, hashlib.sha256).digest()
    payload = base64.urlsafe_b64encode(nonce + mac + ciphertext).decode("ascii")
    return f"{_VERSION}.{payload}"


def decrypt_secret(value: str) -> str:
    try:
        version, payload = value.split(".", 1)
        if version != _VERSION:
            raise ValueError("unsupported encrypted secret version")
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        nonce = raw[:_NONCE_BYTES]
        mac = raw[_NONCE_BYTES : _NONCE_BYTES + 32]
        ciphertext = raw[_NONCE_BYTES + 32 :]
    except Exception as exc:
        raise ValueError("invalid encrypted secret") from exc

    key = _key()
    expected_mac = hmac.new(key, version.encode("ascii") + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("encrypted secret failed integrity check")

    keystream = _stream(key, nonce, len(ciphertext))
    plaintext = bytes(left ^ right for left, right in zip(ciphertext, keystream, strict=True))
    return plaintext.decode("utf-8")
