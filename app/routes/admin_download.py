"""
app/routes/admin_download.py
Endpoint admin untuk manage download methods via JSON config.
"""
import json
import os
import sys
from flask import Blueprint, request, jsonify

from app.utils.auth import require_admin_key
from app.utils.logging import get_logger

log = get_logger("admin_download")
admin_bp = Blueprint("admin_download", __name__, url_prefix="/api/admin/download-methods")


@admin_bp.before_request
def _admin_auth_guard():
    """Semua endpoint admin wajib memakai ADMIN_API_KEY."""
    if request.method == "OPTIONS":
        return None
    return require_admin_key()


def _get_config_path():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
        external = os.path.join(base, "config", "download_methods.json")
        if os.path.exists(external):
            return external
        return os.path.join(sys._MEIPASS, "config", "download_methods.json")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "download_methods.json"
    )


CONFIG_PATH = _get_config_path()


def _load_config() -> dict:
    """Load config dari file JSON."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load config: {e}")
        return {"download_methods": [], "settings": {}, "admin": {}}


def _save_config(data: dict) -> bool:
    """Simpan config ke file JSON."""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log.error(f"Failed to save config: {e}")
        return False


@admin_bp.route("", methods=["GET"])
def list_download_methods():
    """
    Daftar semua download methods.

    GET /api/admin/download-methods
    """
    config = _load_config()
    methods = config.get("download_methods", [])
    settings = config.get("settings", {})

    return jsonify({
        "status": "success",
        "total": len(methods),
        "enabled_count": sum(1 for m in methods if m.get("enabled", False)),
        "methods": methods,
        "settings": settings,
        "admin": config.get("admin", {}),
    })


@admin_bp.route("/settings", methods=["GET"])
def get_settings():
    """Get download settings."""
    config = _load_config()
    return jsonify({
        "status": "success",
        "settings": config.get("settings", {}),
    })


@admin_bp.route("/settings", methods=["PUT"])
def update_settings():
    """
    Update download settings.

    PUT /api/admin/download-methods/settings
    Body: {"max_file_size_mb": 500, "timeout_seconds": 60, ...}
    """
    data = request.get_json() or {}
    config = _load_config()

    allowed_keys = [
        "max_file_size_mb", "chunk_size_kb", "timeout_seconds",
        "retry_attempts", "cache_ttl_seconds"
    ]

    settings = config.get("settings", {})
    for key in allowed_keys:
        if key in data:
            settings[key] = data[key]

    config["settings"] = settings

    if _save_config(config):
        log.info(f"Settings updated: {settings}")
        return jsonify({
            "status": "success",
            "message": "Settings updated",
            "settings": settings,
        })
    else:
        return jsonify({"status": "error", "message": "Failed to save settings"}), 500


@admin_bp.route("", methods=["POST"])
def add_download_method():
    """
    Tambah download method baru.

    POST /api/admin/download-methods
    Body: {
        "id": "custom_method",
        "name": "Custom Method",
        "enabled": true,
        "priority": 11,
        "description": "...",
        "config": {...}
    }
    """
    data = request.get_json() or {}
    config = _load_config()

    method_id = data.get("id")
    if not method_id:
        return jsonify({"error": "Field 'id' wajib diisi."}), 400

    methods = config.get("download_methods", [])

    if any(m.get("id") == method_id for m in methods):
        return jsonify({"error": f"Method '{method_id}' sudah ada."}), 400

    required = ["id", "name", "config"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Field '{field}' wajib diisi."}), 400

    new_method = {
        "id": data["id"],
        "name": data["name"],
        "enabled": data.get("enabled", True),
        "priority": data.get("priority", len(methods) + 1),
        "description": data.get("description", ""),
        "config": data["config"],
    }

    methods.append(new_method)
    config["download_methods"] = methods

    if _save_config(config):
        log.info(f"Method added: {method_id}")
        return jsonify({
            "status": "success",
            "message": f"Method '{method_id}' ditambahkan",
            "method": new_method,
        }), 201
    else:
        return jsonify({"status": "error", "message": "Failed to save"}), 500


@admin_bp.route("/<method_id>", methods=["GET"])
def get_download_method(method_id: str):
    """Get detail satu download method."""
    config = _load_config()
    methods = config.get("download_methods", [])

    for method in methods:
        if method.get("id") == method_id:
            return jsonify({
                "status": "success",
                "method": method,
            })

    return jsonify({"error": f"Method '{method_id}' tidak ditemukan."}), 404


@admin_bp.route("/<method_id>", methods=["PUT"])
def update_download_method(method_id: str):
    """
    Update download method.

    PUT /api/admin/download-methods/<method_id>
    Body: {"name": "...", "enabled": true, "config": {...}, ...}
    """
    data = request.get_json() or {}
    config = _load_config()

    methods = config.get("download_methods", [])
    found = False

    for i, method in enumerate(methods):
        if method.get("id") == method_id:
            updatable = ["name", "enabled", "priority", "description", "config"]
            for key in updatable:
                if key in data:
                    methods[i][key] = data[key]

            found = True
            break

    if not found:
        return jsonify({"error": f"Method '{method_id}' tidak ditemukan."}), 404

    config["download_methods"] = methods

    if _save_config(config):
        log.info(f"Method updated: {method_id}")
        return jsonify({
            "status": "success",
            "message": f"Method '{method_id}' diupdate",
            "method": methods[[m.get("id") for m in methods].index(method_id)],
        })
    else:
        return jsonify({"status": "error", "message": "Failed to save"}), 500


@admin_bp.route("/<method_id>", methods=["DELETE"])
def delete_download_method(method_id: str):
    """
    Hapus download method.

    DELETE /api/admin/download-methods/<method_id>
    """
    config = _load_config()
    methods = config.get("download_methods", [])

    initial_len = len(methods)
    methods = [m for m in methods if m.get("id") != method_id]

    if len(methods) == initial_len:
        return jsonify({"error": f"Method '{method_id}' tidak ditemukan."}), 404

    config["download_methods"] = methods

    if _save_config(config):
        log.info(f"Method deleted: {method_id}")
        return jsonify({
            "status": "success",
            "message": f"Method '{method_id}' dihapus",
        })
    else:
        return jsonify({"status": "error", "message": "Failed to save"}), 500


@admin_bp.route("/<method_id>/toggle", methods=["POST"])
def toggle_download_method(method_id: str):
    """
    Toggle enable/disable download method.

    POST /api/admin/download-methods/<method_id>/toggle
    """
    config = _load_config()
    methods = config.get("download_methods", [])

    for method in methods:
        if method.get("id") == method_id:
            method["enabled"] = not method.get("enabled", True)
            config["download_methods"] = methods

            if _save_config(config):
                status = "enabled" if method["enabled"] else "disabled"
                log.info(f"Method {method_id} {status}")
                return jsonify({
                    "status": "success",
                    "message": f"Method '{method_id}' {status}",
                    "enabled": method["enabled"],
                })
            else:
                return jsonify({"status": "error", "message": "Failed to save"}), 500

    return jsonify({"error": f"Method '{method_id}' tidak ditemukan."}), 404


@admin_bp.route("/reorder", methods=["PUT"])
def reorder_methods():
    """
    Reorder priority download methods.

    PUT /api/admin/download-methods/reorder
    Body: {"order": ["method1", "method2", "method3"]}
    """
    data = request.get_json() or {}
    order = data.get("order", [])

    if not order:
        return jsonify({"error": "Field 'order' wajib berisi list method IDs."}), 400

    config = _load_config()
    methods = config.get("download_methods", [])

    method_map = {m.get("id"): m for m in methods}
    new_methods = []

    for i, method_id in enumerate(order):
        if method_id in method_map:
            method_map[method_id]["priority"] = i + 1
            new_methods.append(method_map[method_id])
        else:
            return jsonify({"error": f"Method '{method_id}' tidak ditemukan."}), 400

    for method_id, method in method_map.items():
        if method_id not in order:
            method["priority"] = len(order) + 1
            new_methods.append(method)

    config["download_methods"] = new_methods

    if _save_config(config):
        log.info(f"Methods reordered: {order}")
        return jsonify({
            "status": "success",
            "message": "Priority diurutkan ulang",
            "methods": new_methods,
        })
    else:
        return jsonify({"status": "error", "message": "Failed to save"}), 500


@admin_bp.route("/reset", methods=["POST"])
def reset_to_default():
    """
    Reset ke default download methods.

    POST /api/admin/download-methods/reset
    """
    default_config = {
        "download_methods": [
            {"id": "unpaywall", "name": "Unpaywall (DOI → OA PDF)", "enabled": True, "priority": 1,
             "description": "Cari PDF open access via DOI menggunakan Unpaywall",
             "config": {"source": "unpaywall"}},
            {"id": "openlibrary", "name": "Open Library (ISBN)", "enabled": True, "priority": 2,
             "description": "Download buku via ISBN dari Open Library",
             "config": {"source": "openlibrary"}},
            {"id": "arxiv_pdf", "name": "arXiv PDF Direct", "enabled": True, "priority": 3,
             "description": "Download langsung PDF dari arXiv",
             "config": {"source": "arxiv", "url_pattern": "https://arxiv.org/pdf/{arxiv_id}.pdf"}},
            {"id": "doaj", "name": "DOAJ Open Access", "enabled": True, "priority": 4,
             "description": "Download dari Directory of Open Access Journals",
             "config": {"source": "doaj"}},
            {"id": "core_download", "name": "CORE Repository", "enabled": True, "priority": 5,
             "description": "Download dari CORE agregator",
             "config": {"source": "core"}},
            {"id": "pubmed_pmc", "name": "PubMed Central", "enabled": True, "priority": 6,
             "description": "Download dari PubMed Central PMC",
             "config": {"source": "pubmed", "url_pattern": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{id}/pdf/"}},
            {"id": "gutenberg", "name": "Project Gutenberg", "enabled": True, "priority": 7,
             "description": "Download buku klasik dari Project Gutenberg",
             "config": {"source": "gutenberg", "formats": ["pdf", "epub", "txt"]}},
            {"id": "archive_org", "name": "Internet Archive", "enabled": True, "priority": 8,
             "description": "Download dari Internet Archive",
             "config": {"source": "archive"}},
            {"id": "crossref", "name": "Crossref Metadata", "enabled": False, "priority": 9,
             "description": "Ambil metadata dan link dari Crossref",
             "config": {"source": "crossref"}},
            {"id": "direct_url", "name": "Direct URL", "enabled": True, "priority": 10,
             "description": "Download langsung dari URL yang provided",
             "config": {"type": "direct"}},
        ],
        "settings": {
            "max_file_size_mb": 500,
            "chunk_size_kb": 8,
            "timeout_seconds": 60,
            "retry_attempts": 3,
            "cache_ttl_seconds": 300,
        },
        "admin": {
            "allow_add_method": True,
            "allow_edit_method": True,
            "allow_delete_method": True,
            "allow_toggle_enabled": True,
        },
    }

    if _save_config(default_config):
        log.info("Config reset to default")
        return jsonify({
            "status": "success",
            "message": "Config di-reset ke default",
            "config": default_config,
        })
    else:
        return jsonify({"status": "error", "message": "Failed to reset"}), 500