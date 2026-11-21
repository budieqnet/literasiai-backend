"""
app/services/garuda.py
Sumber: Garuda — Portal Jurnal Nasional Indonesia (Kemdikbud)
URL: https://garuda.kemdikbud.go.id
Catatan: Garuda tidak menyediakan API publik resmi berbasis JSON.
Implementasi ini menggunakan endpoint pencarian web dengan parsing HTML ringan.
Bila Kemdikbud menyediakan API resmi di masa mendatang, ganti implementasi ini.
"""
import re
from app.utils.http import get
from app.utils.normalizer import make_document

SEARCH_URL = "https://garuda.kemdikbud.go.id/documents"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari artikel di portal Garuda Kemdikbud.
    Menggunakan scraping ringan karena tidak ada API publik resmi.
    """
    try:
        resp = get(SEARCH_URL, params={
            "q":    query,
            "page": page,
        }, headers={"Accept": "text/html,application/xhtml+xml"})
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return _error(str(e))

    docs = _parse_html(html)

    return {
        "source":    "Garuda",
        "total":     len(docs),   # Garuda tidak expose total count di HTML
        "page":      page,
        "page_size": page_size,
        "results":   docs[:page_size],
        "error":     None,
        "note":      "Garuda tidak menyediakan API publik. Data diekstrak dari halaman web.",
    }


def _parse_html(html: str) -> list:
    """
    Parse hasil pencarian Garuda dari HTML.
    Ekstrak judul, penulis, jurnal, tahun, dan link dokumen.
    """
    docs = []

    # Cari blok artikel — Garuda menggunakan struktur div.document-result
    # Pattern fleksibel untuk mengakomodasi perubahan minor template
    blocks = re.findall(
        r'class="[^"]*document[^"]*"[^>]*>(.*?)</article',
        html,
        re.DOTALL | re.IGNORECASE
    )

    # Fallback: cari berdasarkan link artikel
    if not blocks:
        links = re.findall(
            r'href="(/documents/detail/\d+)"[^>]*>\s*<[^>]+>\s*([^<]{10,200})',
            html,
            re.DOTALL
        )
        for path, title in links[:10]:
            title = re.sub(r'\s+', ' ', title).strip()
            url   = f"https://garuda.kemdikbud.go.id{path}"
            docs.append(make_document(
                source   = "Garuda",
                title    = title,
                url      = url,
                doc_type = "journal",
            ))
        return docs

    for block in blocks:
        # Judul
        title_match = re.search(
            r'<(?:h\d|a)[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</(?:h\d|a)>',
            block, re.DOTALL | re.IGNORECASE
        )
        title = _strip_tags(title_match.group(1)) if title_match else "(Tanpa judul)"

        # URL
        url_match = re.search(r'href="(/documents/detail/\d+)"', block)
        url = f"https://garuda.kemdikbud.go.id{url_match.group(1)}" if url_match else None

        # Penulis
        author_match = re.search(
            r'<[^>]*class="[^"]*author[^"]*"[^>]*>(.*?)</[^>]+>',
            block, re.DOTALL | re.IGNORECASE
        )
        authors = []
        if author_match:
            raw = _strip_tags(author_match.group(1))
            authors = [a.strip() for a in re.split(r'[;,]', raw) if a.strip()]

        # Tahun
        year_match = re.search(r'\b(19|20)\d{2}\b', block)
        year = year_match.group(0) if year_match else None

        # Jurnal / publisher
        journal_match = re.search(
            r'<[^>]*class="[^"]*journal[^"]*"[^>]*>(.*?)</[^>]+>',
            block, re.DOTALL | re.IGNORECASE
        )
        publisher = _strip_tags(journal_match.group(1)) if journal_match else None

        docs.append(make_document(
            source    = "Garuda",
            title     = title,
            authors   = authors,
            year      = year,
            url       = url,
            doc_type  = "journal",
            publisher = publisher,
        ))

    return docs


def _strip_tags(text: str) -> str:
    """Hapus semua HTML tag dari string."""
    clean = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', clean).strip()


def _error(msg):
    return {"source": "Garuda", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
