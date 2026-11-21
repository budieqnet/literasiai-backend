"""
app/routes/search.py
Endpoint pencarian — per sumber dan unified (semua sumber sekaligus).
"""
import concurrent.futures
from flask import Blueprint, request, jsonify
from cachetools import TTLCache
from app.services import SOURCE_MAP, JOURNAL_SOURCES, BOOK_SOURCES, ALL_SOURCES
from app.utils.normalizer import filter_unsafe
from app.services.database import db_service
from app.routes.classify import _fallback_classify
from config import Config

search_bp = Blueprint("search", __name__, url_prefix="/api/search")

# Cache in-memory sederhana (key = query+source+page)
_cache = TTLCache(maxsize=256, ttl=Config.CACHE_TTL)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_params() -> tuple:
    """Ekstrak dan validasi parameter umum dari request."""
    query     = (request.args.get("q") or "").strip()
    page      = max(1, int(request.args.get("page", 1)))
    page_size = min(50, max(1, int(request.args.get("page_size", Config.DEFAULT_PAGE_SIZE))))
    return query, page, page_size


def _cache_key(source: str, query: str, page: int, page_size: int) -> str:
    return f"{source}|{query}|{page}|{page_size}"


def _run_source(source_key: str, query: str, page: int, page_size: int) -> dict:
    """Jalankan satu sumber dengan cache."""
    key = _cache_key(source_key, query, page, page_size)
    if key in _cache:
        return _cache[key]

    fn     = SOURCE_MAP[source_key]
    result = fn(query=query, page=page, page_size=page_size)
    _cache[key] = result
    return result


def _enrich_classification(docs: list) -> list:
    """Enrich setiap dokumen dengan kategori klasifikasi awal."""
    for doc in docs:
        if not doc.get("classification"):
            res = _fallback_classify(
                title=doc.get("title") or "",
                abstract=doc.get("abstract") or "",
                subjects=doc.get("subjects") or [],
            )
            cat = res.get("category")
            if cat and cat != "Other":
                doc["classification"] = cat
            else:
                doc_type = (doc.get("doc_type") or "").lower()
                if doc_type == "book":
                    doc["classification"] = "Literature"
                elif doc_type == "preprint":
                    doc["classification"] = "Preprint"
                else:
                    doc["classification"] = "Umum"
    return docs


# ── Endpoint: pencarian satu sumber ───────────────────────────────────────────

@search_bp.route("/<source>", methods=["GET"])
def search_source(source: str):
    """
    Cari di satu sumber tertentu.

    GET /api/search/<source>?q=<query>&page=1&page_size=10

    source: doaj | pubmed | arxiv | core | garuda | sinta |
            neliti | gutenberg | openlibrary | archive
    """
    if source not in SOURCE_MAP:
        return jsonify({
            "error":            f"Sumber '{source}' tidak dikenali.",
            "available_sources": list(SOURCE_MAP.keys()),
        }), 404

    query, page, page_size = _get_params()

    if not query:
        return jsonify({"error": "Parameter 'q' wajib diisi."}), 400

    result = _run_source(source, query, page, page_size)
    result["results"] = _enrich_classification(filter_unsafe(result.get("results", [])))
    result["count"] = len(result["results"])
    db_service.save_search_results(result["results"], query)
    return jsonify(result)


# ── Endpoint: unified search (semua / grup sumber) ─────────────────────────────

@search_bp.route("", methods=["GET"])
def search_all():
    """
    Cari di semua sumber atau grup sumber secara paralel.

    GET /api/search?q=<query>&sources=doaj,arxiv&page=1&page_size=5
    GET /api/search?q=<query>&type=journal   (hanya sumber jurnal)
    GET /api/search?q=<query>&type=book      (hanya sumber buku)

    Parameter opsional:
      sources    : daftar sumber dipisah koma (override type)
      type       : 'journal' | 'book' | 'all' (default: all)
      page       : halaman (default: 1)
      page_size  : hasil per sumber (default: 5 untuk unified)
    """
    query, page, _ = _get_params()
    page_size = min(20, max(1, int(request.args.get("page_size", 5))))

    if not query:
        return jsonify({"error": "Parameter 'q' wajib diisi."}), 400

    # Tentukan sumber yang akan digunakan
    sources_param = request.args.get("sources", "")
    content_type  = request.args.get("type", "all")

    if sources_param:
        requested = [s.strip() for s in sources_param.split(",")]
        sources   = [s for s in requested if s in SOURCE_MAP]
        if not sources:
            return jsonify({
                "error":            "Tidak ada sumber valid dalam parameter 'sources'.",
                "available_sources": list(SOURCE_MAP.keys()),
            }), 400
    elif content_type == "journal":
        sources = JOURNAL_SOURCES
    elif content_type == "book":
        sources = BOOK_SOURCES
    else:
        sources = ALL_SOURCES

    # Jalankan semua sumber secara paralel
    results_by_source = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = {
            executor.submit(_run_source, src, query, page, page_size): src
            for src in sources
        }
        for future in concurrent.futures.as_completed(futures):
            src = futures[future]
            try:
                results_by_source[src] = future.result()
            except Exception as e:
                results_by_source[src] = {
                    "source":    src,
                    "total":     0,
                    "results":   [],
                    "error":     str(e),
                }

    # Gabungkan semua hasil
    all_docs    = []
    source_meta = {}
    for src in sources:
        r = results_by_source.get(src, {})
        all_docs.extend(r.get("results", []))
        source_meta[src] = {
            "total":  r.get("total", 0),
            "error":  r.get("error"),
            "count":  len(r.get("results", [])),
        }

    all_docs = _enrich_classification(filter_unsafe(all_docs))
    db_service.save_search_results(all_docs, query)

    return jsonify({
        "query":        query,
        "page":         page,
        "page_size":    page_size,
        "sources_used": sources,
        "total_results": len(all_docs),
        "source_summary": source_meta,
        "results":      all_docs,
    })
