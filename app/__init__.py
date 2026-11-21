"""
app/__init__.py
Flask application factory — LiterasiAI
"""
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from app.utils.logging import setup_logging
from app.services.database import db_service

setup_logging(level=Config.LOG_LEVEL)


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db_service.init_db()

    # CORS — izinkan semua origin untuk development
    # Di produksi, ganti origins dengan domain frontend yang sebenarnya
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Register blueprints
    from app.routes.search import search_bp
    from app.routes.lookup import lookup_bp
    from app.routes.health import health_bp
    from app.routes.download import download_bp
    from app.routes.classify import classify_bp
    from app.routes.admin_download import admin_bp
    from app.routes.database import database_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(lookup_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(classify_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(database_bp)

    # ── Root endpoint ───────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return jsonify({
            "app":        "LiterasiAI API",
            "version":    "1.0.0",
            "description":"Mesin pencari & download ebook dan ejournal dengan klasifikasi AI",
"endpoints": {
                "GET /api/search?q=<query>":                        "Cari di semua sumber",
                "GET /api/search?q=<query>&type=journal":           "Cari hanya jurnal",
                "GET /api/search?q=<query>&type=book":              "Cari hanya buku",
                "GET /api/search?q=<query>&sources=doaj,arxiv":     "Cari di sumber tertentu",
                "GET /api/search/<source>?q=<query>":               "Cari di satu sumber",
                "GET /api/lookup/doi?doi=<doi>":                    "Lookup metadata + OA via DOI",
                "GET /api/lookup/isbn?isbn=<isbn>":                 "Lookup buku via ISBN",
                "GET /api/lookup/sources":                          "Daftar semua sumber tersedia",
                "GET /health":                                      "Health check semua sumber",
                "GET /health?detailed=true":                        "Health check detail",
                "POST /api/download":                               "Download file (url/doi/isbn)",
                "POST /api/classify":                               "Klasifikasi AI via NVIDIA Nemotron",
            },
        })

    # ── Error handlers ───────────────────────────────────────────────────────

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint tidak ditemukan.", "hint": "Cek GET / untuk daftar endpoint."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method tidak diizinkan."}), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Terjadi kesalahan internal server.", "detail": str(e)}), 500

    return app
