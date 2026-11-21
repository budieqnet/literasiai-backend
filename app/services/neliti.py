"""
app/services/neliti.py
Sumber: Neliti — repositori riset Indonesia
URL: https://www.neliti.com
API: https://www.neliti.com/api/publications/search
"""
from app.utils.http import get
from app.utils.normalizer import make_document

SEARCH_URL = "https://www.neliti.com/api/publications/search"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari publikasi di Neliti via API publiknya.
    """
    try:
        resp = get(SEARCH_URL, params={
            "q":     query,
            "page":  page,
            "limit": page_size,
            "type":  "journal-article",
        })
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return _error(str(e))

    # Neliti bisa kembalikan list langsung atau dict dengan key 'data'
    if isinstance(data, list):
        items = data
        total = len(data)
    else:
        items = data.get("data", data.get("results", []))
        total = data.get("total", data.get("count", len(items)))

    docs = []
    for item in items:
        # Normalisasi penulis
        authors = []
        for a in item.get("authors", []):
            if isinstance(a, str):
                authors.append(a)
            elif isinstance(a, dict):
                name = a.get("name") or f"{a.get('first_name','')} {a.get('last_name','')}".strip()
                if name:
                    authors.append(name)

        doi_val = item.get("doi")
        pub_id  = item.get("id") or item.get("slug", "")
        url     = (
            item.get("url")
            or (f"https://www.neliti.com/publications/{pub_id}" if pub_id else None)
        )
        pdf_url = item.get("pdf_url") or item.get("download_url")

        year = None
        for field in ("year", "published_year", "publication_year"):
            if item.get(field):
                year = str(item[field])[:4]
                break

        subjects = item.get("subjects", []) or item.get("keywords", []) or []
        subjects = [s if isinstance(s, str) else s.get("name", "") for s in subjects]

        docs.append(make_document(
            source       = "Neliti",
            title        = item.get("title", "(Tanpa judul)"),
            authors      = authors,
            year         = year,
            abstract     = item.get("abstract"),
            doi          = doi_val,
            url          = url,
            download_url = pdf_url,
            pdf_url      = pdf_url,
            language     = item.get("language", "id"),
            doc_type     = "journal",
            subjects     = subjects,
            publisher    = item.get("journal") or item.get("publisher"),
            identifier   = str(pub_id),
        ))

    return {
        "source":    "Neliti",
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "results":   docs,
        "error":     None,
    }


def _error(msg):
    return {"source": "Neliti", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
