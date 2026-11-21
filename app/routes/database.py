"""
app/routes/database.py
Endpoint untuk melihat dan mengelola koleksi dokumen (buku & jurnal) di database MySQL.
"""
from flask import Blueprint, request, jsonify
from app.services.database import db_service
from app.utils.logging import get_logger

log = get_logger("database_route")
database_bp = Blueprint("database", __name__, url_prefix="/api/database")


@database_bp.route("/documents", methods=["GET"])
def list_documents():
    """
    Ambil daftar dokumen yang sudah tersimpan di database MySQL.
    Mendukung filter berdasarkan doc_type, classification, source, keyword q, serta pagination.
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(100, max(1, int(request.args.get("page_size", 10))))
    except ValueError:
        page = 1
        page_size = 10

    doc_type = request.args.get("doc_type")
    classification = request.args.get("classification")
    source = request.args.get("source")
    q = request.args.get("q")

    data = db_service.get_documents(
        page=page,
        page_size=page_size,
        doc_type=doc_type,
        classification=classification,
        source=source,
        q=q,
    )
    return jsonify(data)


@database_bp.route("/stats", methods=["GET"])
def get_stats():
    """Ambil ringkasan statistik koleksi buku & jurnal di database."""
    stats = db_service.get_stats()
    return jsonify(stats)


@database_bp.route("/documents/<int:doc_id>", methods=["DELETE"])
def delete_document(doc_id: int):
    """Hapus satu dokumen dari database."""
    success = db_service.delete_document(doc_id)
    if success:
        return jsonify({"status": "success", "message": f"Dokumen ID {doc_id} berhasil dihapus."})
    return jsonify({"error": f"Dokumen ID {doc_id} tidak ditemukan atau gagal dihapus."}), 404
