"""
app/utils/auth.py
Autentikasi sederhana untuk endpoint admin.
"""
import hmac

from flask import jsonify, request

from config import Config
from app.utils.logging import get_logger

log = get_logger("auth")


def _provided_admin_keys() -> list:
    """Ambil kandidat key dari header Authorization atau X-Admin-Key."""
    keys = []

    authorization = request.headers.get("Authorization", "")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            keys.append(token.strip())

    explicit_key = (request.headers.get("X-Admin-Key") or "").strip()
    if explicit_key:
        keys.append(explicit_key)

    return keys


def require_admin_key():
    """
    Return response error bila request admin tidak terautentikasi.

    Return None bila request boleh dilanjutkan. Fail closed bila
    ADMIN_API_KEY belum dikonfigurasi.
    """
    expected = (Config.ADMIN_API_KEY or "").strip()

    if not expected:
        log.error("ADMIN_API_KEY belum dikonfigurasi; endpoint admin ditolak")
        return jsonify({
            "error": "Admin API belum dikonfigurasi.",
            "hint": "Set ADMIN_API_KEY di environment atau .env.",
        }), 503

    provided_keys = _provided_admin_keys()
    if not any(hmac.compare_digest(key, expected) for key in provided_keys):
        log.warning(
            "Admin auth gagal dari %s",
            request.remote_addr or "unknown",
        )
        response = jsonify({"error": "Unauthorized."})
        response.status_code = 401
        response.headers["WWW-Authenticate"] = 'Bearer realm="admin"'
        return response

    return None
