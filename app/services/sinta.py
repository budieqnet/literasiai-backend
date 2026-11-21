"""
app/services/sinta.py
Sumber: SINTA (Science and Technology Index) — Kemdikbud
URL: https://sinta.kemdikbud.go.id
Catatan: SINTA tidak menyediakan API publik berbasis JSON untuk pencarian artikel.
Implementasi ini mencari jurnal terakreditasi via endpoint pencarian SINTA
dan mengarahkan pengguna ke halaman jurnal yang relevan.
"""
import re
from app.utils.http import get
from app.utils.normalizer import make_document

JOURNAL_SEARCH_URL = "https://sinta.kemdikbud.go.id/journals"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari jurnal terakreditasi di SINTA.
    Kembalikan daftar jurnal (bukan artikel individual) beserta link ke halaman jurnalnya.
    """
    try:
        resp = get(JOURNAL_SEARCH_URL, params={
            "q":    query,
            "page": page,
        }, headers={"Accept": "text/html,application/xhtml+xml"})
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return _error(str(e))

    docs = _parse_journals(html, page_size)

    return {
        "source":    "SINTA",
        "total":     len(docs),
        "page":      page,
        "page_size": page_size,
        "results":   docs[:page_size],
        "error":     None,
        "note":      (
            "SINTA menampilkan jurnal terakreditasi, bukan artikel individual. "
            "Kunjungi halaman jurnal untuk mengakses artikel di dalamnya."
        ),
    }


def _parse_journals(html: str, page_size: int = 10) -> list:
    """
    Parse daftar jurnal dari halaman pencarian SINTA.
    Ekstrak nama jurnal, akreditasi, institusi, dan link.
    """
    docs = []

    # Cari blok jurnal
    blocks = re.findall(
        r'<(?:div|article)[^>]*class="[^"]*journal[^"]*"[^>]*>(.*?)</(?:div|article)>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    # Fallback: cari berdasarkan link profil jurnal
    if not blocks:
        links = re.findall(
            r'href="(https://sinta\.kemdikbud\.go\.id/journals/profile/\d+)"[^>]*>\s*([^<]{5,200})',
            html,
        )
        for url, title in links[:page_size]:
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > 5:
                docs.append(make_document(
                    source   = "SINTA",
                    title    = title,
                    url      = url,
                    doc_type = "journal",
                ))
        return docs

    for block in blocks:
        # Judul jurnal
        title_match = re.search(
            r'<(?:h\d|a)[^>]*>(.*?)</(?:h\d|a)>',
            block, re.DOTALL | re.IGNORECASE
        )
        title = _strip_tags(title_match.group(1)) if title_match else "(Tanpa judul)"

        # Link jurnal
        url_match = re.search(
            r'href="(https://sinta\.kemdikbud\.go\.id/journals/profile/\d+)"',
            block
        )
        url = url_match.group(1) if url_match else None

        # Akreditasi SINTA (S1–S6)
        sinta_match = re.search(r'\bS([1-6])\b', block)
        subjects = [f"SINTA {sinta_match.group(0)}"] if sinta_match else []

        # Institusi / publisher
        inst_match = re.search(
            r'<[^>]*class="[^"]*(?:publisher|institution|affil)[^"]*"[^>]*>(.*?)</[^>]+>',
            block, re.DOTALL | re.IGNORECASE
        )
        publisher = _strip_tags(inst_match.group(1)) if inst_match else None

        docs.append(make_document(
            source    = "SINTA",
            title     = title,
            url       = url,
            doc_type  = "journal",
            subjects  = subjects,
            publisher = publisher,
        ))

    return docs


def _strip_tags(text: str) -> str:
    clean = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', clean).strip()


def _error(msg):
    return {"source": "SINTA", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
