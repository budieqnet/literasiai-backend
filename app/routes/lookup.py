"""
app/routes/lookup.py
Endpoint lookup berdasarkan DOI, ISBN, atau URL langsung.
"""
from flask import Blueprint, request, jsonify
from app.services.openaccess import lookup_doi
from app.services.openlibrary import search_by_isbn
from app.utils.http import get as http_get
from app.utils.normalizer import make_document

lookup_bp = Blueprint("lookup", __name__, url_prefix="/api/lookup")

CROSSREF_URL = "https://api.crossref.org/works"


# ── DOI Lookup ─────────────────────────────────────────────────────────────────

@lookup_bp.route("/doi", methods=["GET"])
def lookup_by_doi():
    """
    Lookup metadata dan URL open access berdasarkan DOI.

    GET /api/lookup/doi?doi=10.1007/s10462-023-10517-4

    Alur:
    1. Ambil metadata dari Crossref API
    2. Cek ketersediaan OA via Unpaywall
    3. Kembalikan metadata + URL download bila tersedia
    """
    doi = (request.args.get("doi") or "").strip()
    if not doi:
        return jsonify({"error": "Parameter 'doi' wajib diisi."}), 400

    doi_clean = doi.lstrip("https://doi.org/").lstrip("http://dx.doi.org/")
    result    = {"doi": doi_clean, "metadata": None, "open_access": None, "error": None}

    # 1. Crossref — metadata lengkap
    try:
        cr_resp = http_get(f"{CROSSREF_URL}/{doi_clean}")
        cr_resp.raise_for_status()
        cr_data = cr_resp.json().get("message", {})

        authors = []
        for a in cr_data.get("author", []):
            name = f"{a.get('given','')} {a.get('family','')}".strip()
            if name:
                authors.append(name)

        issued = cr_data.get("issued", {}).get("date-parts", [[None]])[0]
        year   = str(issued[0]) if issued and issued[0] else None

        abstract = cr_data.get("abstract", "")
        # Bersihkan tag JATS XML dari abstrak Crossref
        import re
        abstract = re.sub(r'<[^>]+>', '', abstract).strip() if abstract else None

        result["metadata"] = make_document(
            source    = "Crossref",
            title     = (cr_data.get("title") or ["(Tanpa judul)"])[0],
            authors   = authors,
            year      = year,
            abstract  = abstract,
            doi       = doi_clean,
            url       = cr_data.get("URL"),
            doc_type  = cr_data.get("type", "journal-article"),
            publisher = cr_data.get("publisher"),
            subjects  = cr_data.get("subject", []),
            identifier= doi_clean,
        )

    except Exception as e:
        result["error"] = f"Crossref error: {e}"

    # 2. Unpaywall — open access URL
    try:
        oa = lookup_doi(doi_clean)
        result["open_access"] = {
            "is_oa":    oa.get("is_oa", False),
            "best_url": oa.get("best_url"),
            "locations": [
                {
                    "source":    doc.get("source"),
                    "url":       doc.get("url"),
                    "pdf_url":   doc.get("pdf_url"),
                }
                for doc in oa.get("results", [])
            ],
        }
    except Exception as e:
        result["open_access"] = {"is_oa": False, "error": str(e)}

    return jsonify(result)


# ── ISBN Lookup ────────────────────────────────────────────────────────────────

@lookup_bp.route("/isbn", methods=["GET"])
def lookup_by_isbn():
    """
    Lookup metadata buku berdasarkan ISBN.

    GET /api/lookup/isbn?isbn=9780140449136
    """
    isbn = (request.args.get("isbn") or "").strip().replace("-", "")
    if not isbn:
        return jsonify({"error": "Parameter 'isbn' wajib diisi."}), 400

    doc = search_by_isbn(isbn)
    if not doc:
        return jsonify({
            "isbn":  isbn,
            "found": False,
            "error": f"Buku dengan ISBN {isbn} tidak ditemukan di Open Library.",
        }), 404

    return jsonify({"isbn": isbn, "found": True, "result": doc})


# ── Sumber yang tersedia ────────────────────────────────────────────────────────

@lookup_bp.route("/sources", methods=["GET"])
def list_sources():
    """
    Daftar semua sumber yang tersedia beserta deskripsi singkat.

    GET /api/lookup/sources
    """
    from app.services import registry

    sources = []
    for info in registry.list_source_infos():
        sources.append({
            "id": info["id"],
            "name": info["name"],
            "type": info["type"],
            "language": info["language"],
            "api": info["api_available"],
            "note": info["description"],
        })
    return jsonify({"total": len(sources), "sources": sources})
