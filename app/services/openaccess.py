"""
app/services/openaccess.py
Sumber: Unpaywall — menemukan versi open access legal dari paper berbayar via DOI
API: https://api.unpaywall.org/v2/{doi}
Tidak memerlukan API key, hanya email sebagai identifier (etika penggunaan API).
"""
from app.utils.http import get
from app.utils.normalizer import make_document

BASE_URL = "https://api.unpaywall.org/v2"
EMAIL    = "admin@literasiai.id"   # ganti dengan email institusi


def lookup_doi(doi: str) -> dict:
    """
    Cari versi open access dari sebuah artikel berdasarkan DOI.
    Kembalikan informasi akses beserta URL download bila tersedia.
    """
    doi_clean = doi.strip().lstrip("https://doi.org/").lstrip("http://dx.doi.org/")

    try:
        resp = get(f"{BASE_URL}/{doi_clean}", params={"email": EMAIL})
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "doi": doi, "is_oa": False, "results": []}

    is_oa = data.get("is_oa", False)

    if not is_oa:
        return {
            "doi":     doi,
            "is_oa":   False,
            "title":   data.get("title"),
            "results": [],
            "error":   None,
            "note":    "Artikel ini tidak memiliki versi open access yang terdeteksi oleh Unpaywall.",
        }

    # Kumpulkan semua lokasi OA
    oa_locations = data.get("oa_locations", [])
    best         = data.get("best_oa_location", {}) or {}

    authors = []
    for a in data.get("z_authors", []):
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)

    docs = []
    for loc in oa_locations:
        url_for_pdf = loc.get("url_for_pdf") or loc.get("url")
        docs.append(make_document(
            source       = f"Unpaywall ({loc.get('host_type','unknown')})",
            title        = data.get("title", "(Tanpa judul)"),
            authors      = authors,
            year         = str(data.get("year", "")) or None,
            doi          = doi_clean,
            url          = loc.get("url"),
            download_url = url_for_pdf,
            pdf_url      = loc.get("url_for_pdf"),
            doc_type     = "journal",
            publisher    = data.get("publisher"),
            identifier   = doi_clean,
        ))

    return {
        "doi":       doi_clean,
        "is_oa":     is_oa,
        "title":     data.get("title"),
        "best_url":  best.get("url_for_pdf") or best.get("url"),
        "results":   docs,
        "error":     None,
    }


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Unpaywall tidak mendukung pencarian teks bebas.
    Endpoint ini mengembalikan petunjuk penggunaan yang benar.
    """
    return {
        "source":    "Unpaywall",
        "total":     0,
        "page":      1,
        "page_size": page_size,
        "results":   [],
        "error":     None,
        "note":      (
            "Unpaywall hanya mendukung lookup berdasarkan DOI. "
            "Gunakan endpoint GET /api/openaccess/doi?doi=10.xxxx/xxxxx"
        ),
    }
