"""
app/services/openlibrary.py
Sumber: Open Library (Internet Archive)
API: https://openlibrary.org/api/
Mendukung pencarian buku via judul/penulis dan lookup via ISBN.
"""
from app.utils.http import get
from app.utils.normalizer import make_document

SEARCH_URL = "https://openlibrary.org/search.json"
BOOK_URL   = "https://openlibrary.org"
COVER_URL  = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari buku di Open Library.
    """
    try:
        resp = get(SEARCH_URL, params={
            "q":      query,
            "page":   page,
            "limit":  page_size,
            "fields": (
                "key,title,author_name,first_publish_year,"
                "subject,publisher,language,isbn,cover_i,"
                "ia,has_fulltext,public_scan_b"
            ),
        })
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return _error(str(e))

    total   = data.get("numFound", 0)
    results = data.get("docs", [])
    docs    = []

    for item in results:
        key      = item.get("key", "")     # /works/OLxxxxW
        ol_url   = f"{BOOK_URL}{key}" if key else None
        cover_id = item.get("cover_i")
        thumbnail = COVER_URL.format(cover_id=cover_id) if cover_id else None

        # Download gratis hanya bila has_fulltext dan public_scan
        ia_id        = item.get("ia", [None])[0] if item.get("ia") else None
        download_url = None
        pdf_url      = None
        if ia_id and item.get("public_scan_b"):
            download_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"
            pdf_url      = download_url

        authors  = item.get("author_name", [])
        subjects = item.get("subject", [])[:10]    # batasi agar tidak terlalu panjang
        isbn_list = item.get("isbn", [])
        isbn = isbn_list[0] if isbn_list else None

        lang_list = item.get("language", [])
        language  = lang_list[0] if lang_list else None

        docs.append(make_document(
            source       = "Open Library",
            title        = item.get("title", "(Tanpa judul)"),
            authors      = authors,
            year         = str(item.get("first_publish_year", "")) or None,
            doc_type     = "book",
            subjects     = subjects,
            url          = ol_url,
            download_url = download_url,
            pdf_url      = pdf_url,
            language     = language,
            publisher    = (item.get("publisher") or [None])[0],
            identifier   = isbn or key,
            thumbnail    = thumbnail,
        ))

    return {
        "source":    "Open Library",
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "results":   docs,
        "error":     None,
    }


def search_by_isbn(isbn: str) -> dict:
    """
    Lookup buku berdasarkan ISBN via Open Library Books API.
    Kembalikan satu dokumen atau None bila tidak ditemukan.
    """
    try:
        resp = get(f"{BOOK_URL}/api/books", params={
            "bibkeys":  f"ISBN:{isbn}",
            "format":   "json",
            "jscmd":    "data",
        })
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    key  = f"ISBN:{isbn}"
    item = data.get(key)
    if not item:
        return None

    authors  = [a.get("name", "") for a in item.get("authors", [])]
    subjects = [s.get("name", "") for s in item.get("subjects", [])]
    cover    = item.get("cover", {})

    download_url = None
    for link in item.get("links", []):
        if "pdf" in link.get("title", "").lower() or "download" in link.get("title", "").lower():
            download_url = link.get("url")
            break

    return make_document(
        source       = "Open Library",
        title        = item.get("title", "(Tanpa judul)"),
        authors      = authors,
        year         = str(item.get("publish_date", ""))[:4] or None,
        doc_type     = "book",
        subjects     = subjects,
        url          = item.get("url"),
        download_url = download_url,
        publisher    = (item.get("publishers") or [{}])[0].get("name"),
        identifier   = isbn,
        thumbnail    = cover.get("medium") or cover.get("small"),
    )


def _error(msg):
    return {"source": "Open Library", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
