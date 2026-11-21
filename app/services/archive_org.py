"""
app/services/archive_org.py
Sumber: Internet Archive (archive.org)
API: https://archive.org/advancedsearch.php
Mendukung pencarian buku, jurnal, teks, dan dokumen historis.
"""
from app.utils.http import get
from app.utils.normalizer import make_document

SEARCH_URL = "https://archive.org/advancedsearch.php"
DETAIL_URL = "https://archive.org/details"
DOWNLOAD_URL = "https://archive.org/download"


def search(query: str, page: int = 1, page_size: int = 10, media_type: str = "texts") -> dict:
    """
    Cari dokumen di Internet Archive.
    media_type: 'texts' (default) | 'journals' | 'all'
    """
    rows  = page_size
    start = (page - 1) * page_size

    # Bangun query — filter ke media teks dan open access
    if media_type == "all":
        q = f'({query}) AND licenseurl:(*creativecommons* OR *publicdomain*)'
    else:
        q = f'({query}) AND mediatype:{media_type}'

    try:
        resp = get(SEARCH_URL, params={
            "q":      q,
            "fl[]":   ["identifier", "title", "creator", "date", "description",
                       "subject", "publisher", "language", "format", "licenseurl"],
            "rows":   rows,
            "page":   page,
            "output": "json",
            "sort[]": "downloads desc",
        })
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return _error(str(e))

    response = data.get("response", {})
    total    = response.get("numFound", 0)
    items    = response.get("docs", [])
    docs     = []

    for item in items:
        identifier = item.get("identifier", "")
        detail_url = f"{DETAIL_URL}/{identifier}"
        pdf_url    = f"{DOWNLOAD_URL}/{identifier}/{identifier}.pdf"

        # Penulis bisa string atau list
        creator = item.get("creator", [])
        if isinstance(creator, str):
            creator = [creator]
        authors = creator or []

        # Subjek bisa string atau list
        subjects = item.get("subject", [])
        if isinstance(subjects, str):
            subjects = [subjects]

        # Tahun: ambil 4 digit dari field date
        date = str(item.get("date", "") or "")
        import re
        year_match = re.search(r'\b(19|20)\d{2}\b', date)
        year = year_match.group(0) if year_match else None

        # Deteksi tipe dokumen dari format yang tersedia
        formats   = item.get("format", [])
        if isinstance(formats, str):
            formats = [formats]
        doc_type = "book"
        if any("journal" in f.lower() for f in formats):
            doc_type = "journal"
        elif any("article" in f.lower() for f in formats):
            doc_type = "journal"

        # Cek apakah PDF tersedia di format list
        has_pdf = any("pdf" in f.lower() for f in formats)

        docs.append(make_document(
            source       = "Internet Archive",
            title        = item.get("title", "(Tanpa judul)"),
            authors      = authors,
            year         = year,
            abstract     = item.get("description"),
            url          = detail_url,
            download_url = pdf_url if has_pdf else detail_url,
            pdf_url      = pdf_url if has_pdf else None,
            language     = item.get("language"),
            doc_type     = doc_type,
            subjects     = subjects,
            publisher    = item.get("publisher"),
            identifier   = identifier,
        ))

    return {
        "source":    "Internet Archive",
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "results":   docs,
        "error":     None,
    }


def _error(msg):
    return {"source": "Internet Archive", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
