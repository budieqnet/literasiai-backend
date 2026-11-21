"""
app/routes/health.py
Endpoint health check — termasuk check ke semua sumber eksternal.
"""
import concurrent.futures
from flask import Blueprint, jsonify, request

from app.services import SOURCE_MAP
from app.services.database import db_service
from app.utils.http import get
from app.utils.logging import get_logger

log = get_logger("health")
health_bp = Blueprint("health", __name__)


HEALTH_CHECK_TIMEOUT = 5


@health_bp.route("/health", methods=["GET"])
def health_check():
    """
    Health check aplikasi dan database.

    GET /health
    GET /health?detailed=true
    """
    detailed = request.args.get("detailed", "false").lower() in ("1", "true", "yes")
    db_status = db_service.health()

    if detailed:
        return _detailed_health(db_status)

    status = "healthy" if db_status["status"] == "up" else "degraded"
    return jsonify({
        "status": status,
        "version": "1.0.0",
        "database": db_status,
    })


def _detailed_health(db_status):
    """
    Health check detail: cek database dan semua sumber secara parallel.
    """
    results = {}

    def _check_source(key: str):
        """Cek satu sumber dengan timeout."""
        try:
            fn = SOURCE_MAP[key]
            result = fn(query="test", page=1, page_size=1)
            if result.get("error"):
                return key, "down", result["error"]
            return key, "up", None
        except Exception as e:
            return key, "down", str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_check_source, src): src
            for src in SOURCE_MAP.keys()
        }
        for future in concurrent.futures.as_completed(futures):
            src = futures[future]
            key, status, error = future.result()
            results[key] = {
                "status": status,
                "error": error,
            }

    up_count = sum(1 for r in results.values() if r["status"] == "up")
    total = len(results)
    db_up = db_status["status"] == "up"

    if up_count == total and db_up:
        overall = "healthy"
    elif up_count > 0 or db_up:
        overall = "degraded"
    else:
        overall = "unhealthy"

    return jsonify({
        "status": overall,
        "version": "1.0.0",
        "database": db_status,
        "sources": {
            "total": total,
            "up": up_count,
            "down": total - up_count,
        },
        "details": results,
    })