"""
app/services/doaj.py
Sumber: Directory of Open Access Journals
API: https://doaj.org/api/v3/docs
"""
from app.utils.http import get
from app.utils.normalizer import make_document

BASE_URL = "https://doaj.org/api/v3"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari artikel di DOAJ.
    Endpoint: GET /api/v3/search/articles/{search_query}
    """
    try:
        resp = get(f"{BASE_URL}/search/articles/{query}", params={
            "pageSize": page_size,
            "page":     page,
        })
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return _error(str(e))

    results = data.get("results", [])
    docs = []

    for item in results:
        bib    = item.get("bibjson", {})
        idents = {i.get("type"): i.get("id") for i in bib.get("identifier", [])}
        links  = {ln.get("type"): ln.get("url") for ln in bib.get("link", [])}

        authors = [
            a.get("name", "") for a in bib.get("author", []) if a.get("name")
        ]
        subjects = [
            s.get("term", "") for s in bib.get("subject", [])
        ]

        docs.append(make_document(
            source       = "DOAJ",
            title        = bib.get("title", "(Tanpa judul)"),
            authors      = authors,
            year         = str(bib.get("year", "")) or None,
            abstract     = bib.get("abstract"),
            doi          = idents.get("doi"),
            url          = links.get("fulltext") or links.get("abstract"),
            download_url = links.get("fulltext"),
            language     = bib.get("language", [None])[0] if bib.get("language") else None,
            doc_type     = "journal",
            subjects     = subjects,
            publisher    = bib.get("journal", {}).get("publisher"),
            identifier   = item.get("id"),
        ))

    return {
        "source":     "DOAJ",
        "total":      data.get("total", len(docs)),
        "page":       page,
        "page_size":  page_size,
        "results":    docs,
        "error":      None,
    }


def _error(msg: str) -> dict:
    return {"source": "DOAJ", "total": 0, "page": 1, "page_size": 0, "results": [], "error": msg}