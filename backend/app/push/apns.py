"""APNs push — HTTP/2 + ES256 JWT provider token (httpx[http2] + cryptography)."""
import base64
import json
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_provider_token(auth_key: bytes, team_id: str, key_id: str) -> str:
    header = _b64url(json.dumps({"alg": "ES256", "kid": key_id}).encode())
    claims = _b64url(json.dumps({"iss": team_id, "iat": int(time.time())}).encode())
    key = serialization.load_pem_private_key(auth_key, password=None)
    sig = key.sign(f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    return f"{header}.{claims}.{_b64url(sig)}"


def send_push(token: str, payload: dict, cfg: dict, sandbox: bool = False) -> bool:
    """Send one push notification to one device token. True when APNs accepted it (HTTP 200)."""
    try:
        auth_key = Path(cfg.get("auth_key_path", "")).read_bytes()
    except Exception:  # noqa: BLE001 — missing key = not configured
        return False
    host = "api.sandbox.push.apple.com" if sandbox else "api.push.apple.com"
    headers = {
        "authorization": f"bearer {make_provider_token(auth_key, cfg.get('team_id', ''), cfg.get('key_id', ''))}",
        "apns-topic": cfg.get("bundle_id", ""),
        "apns-push-type": "alert",
        "apns-priority": "10",
    }
    try:
        with httpx.Client(http2=True, timeout=10.0) as client:
            res = client.post(f"https://{host}/3/device/{token}", json=payload, headers=headers)
            return res.status_code == 200
    except Exception:  # noqa: BLE001
        return False
