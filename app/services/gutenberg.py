"""
app/services/gutenberg.py
Sumber: Project Gutenberg — 70.000+ buku klasik bebas hak cipta
API: https://gutendex.com (wrapper JSON untuk Gutenberg)
"""
from app.utils.http import get
from app.utils.normalizer import make_document

BASE_URL = "https://gutendex.com/books"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari buku di Project Gutenberg via Gutendex API.
    Gutendex mendukung paginasi via parameter 'page'.
    """
    try:
        resp = get(BASE_URL, params={
            "search":   query,
            "page":     page,
        })
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return _error(str(e))

    total   = data.get("count", 0)
    results = data.get("results", [])
    docs    = []

    for item in results[:page_size]:
        authors = []
        for a in item.get("authors", []):
            name      = a.get("name", "")
            birth     = a.get("birth_year")
            death     = a.get("death_year")
            full_name = name
            if birth or death:
                full_name += f" ({birth or '?'}–{death or '?'})"
            if full_name.strip():
                authors.append(full_name)

        subjects  = item.get("subjects", [])
        bookshelves = item.get("bookshelves", [])
        all_subjects = subjects + bookshelves

        formats    = item.get("formats", {})
        pdf_url    = formats.get("application/pdf")
        epub_url   = formats.get("application/epub+zip")
        txt_url    = formats.get("text/plain; charset=utf-8") or formats.get("text/plain")
        download_url = pdf_url or epub_url or txt_url

        book_id  = item.get("id")
        book_url = f"https://www.gutenberg.org/ebooks/{book_id}"

        # Bahasa — Gutenberg mengembalikan list kode bahasa
        langs = item.get("languages", [])
        lang  = langs[0] if langs else None

        docs.append(make_document(
            source       = "Project Gutenberg",
            title        = item.get("title", "(Tanpa judul)"),
            authors      = authors,
            doc_type     = "book",
            subjects     = all_subjects,
            url          = book_url,
            download_url = download_url,
            pdf_url      = pdf_url,
            language     = lang,
            identifier   = str(book_id),
            thumbnail    = formats.get("image/jpeg"),
        ))

    return {
        "source":    "Project Gutenberg",
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "results":   docs,
        "error":     None,
    }


def _error(msg):
    return {"source": "Project Gutenberg", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
