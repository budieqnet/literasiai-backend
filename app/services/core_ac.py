"""
app/services/core_ac.py
Sumber: CORE (core.ac.uk) — agregator open access terbesar
API v3: https://api.core.ac.uk/v3/
Catatan: API key meningkatkan rate limit, tapi tidak wajib untuk pencarian dasar.
"""
from app.utils.http import get
from app.utils.normalizer import make_document
from config import Config

BASE_URL = "https://api.core.ac.uk/v3/search/works"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari paper di CORE. Gunakan API key bila tersedia.
    """
    headers = {}
    if Config.CORE_API_KEY:
        headers["Authorization"] = f"Bearer {Config.CORE_API_KEY}"

    offset = (page - 1) * page_size
    try:
        resp = get(BASE_URL, params={
            "q":      query,
            "limit":  page_size,
            "offset": offset,
        }, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return _error(str(e))

    total   = data.get("totalHits", 0)
    results = data.get("results", [])
    docs    = []

    for item in results:
        authors = []
        for a in item.get("authors", []):
            name = a.get("name") or f"{a.get('firstName','')} {a.get('lastName','')}".strip()
            if name:
                authors.append(name)

        subjects = item.get("subjects", []) or []
        subjects = [s if isinstance(s, str) else str(s) for s in subjects]

        doi_val     = item.get("doi")
        source_urls = item.get("sourceFulltextUrls") or []
        download_url = item.get("downloadUrl") or (source_urls[0] if source_urls else None)
        pdf_url      = item.get("pdfUrl")

        docs.append(make_document(
            source       = "CORE",
            title        = item.get("title", "(Tanpa judul)"),
            authors      = authors,
            year         = str(item.get("yearPublished", "")) or None,
            abstract     = item.get("abstract"),
            doi          = doi_val,
            url          = source_urls[0] if source_urls else None,
            download_url = download_url,
            pdf_url      = pdf_url,
            doc_type     = "journal",
            subjects     = subjects,
            publisher    = item.get("publisher"),
            identifier   = str(item.get("id", "")),
        ))

    return {
        "source":    "CORE",
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "results":   docs,
        "error":     None,
    }


def _error(msg):
    return {"source": "CORE", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
