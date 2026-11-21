"""
app/services/arxiv.py
Sumber: arXiv.org — preprint sains, teknik, AI, matematika
API: https://export.arxiv.org/api/query
"""
import xmltodict
from app.utils.http import get
from app.utils.normalizer import make_document

BASE_URL = "https://export.arxiv.org/api/query"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari preprint di arXiv menggunakan Atom feed API resmi.
    """
    start = (page - 1) * page_size
    try:
        resp = get(BASE_URL, params={
            "search_query": f"all:{query}",
            "start":        start,
            "max_results":  page_size,
        }, headers={"Accept": "application/atom+xml"})
        resp.raise_for_status()
        data = xmltodict.parse(resp.text)
    except Exception as e:
        return _error(str(e))

    feed    = data.get("feed", {})
    total_raw = feed.get("opensearch:totalResults", "0")
    total   = int(str(total_raw)) if total_raw else 0
    entries = feed.get("entry", [])

    # xmltodict kembalikan dict tunggal bila hanya 1 hasil
    if isinstance(entries, dict):
        entries = [entries]

    docs = []
    for entry in entries:
        # Penulis bisa list atau dict
        raw_authors = entry.get("author", [])
        if isinstance(raw_authors, dict):
            raw_authors = [raw_authors]
        authors = [a.get("name", "") for a in raw_authors]

        # Kategori / subjek
        cats = entry.get("category", [])
        if isinstance(cats, dict):
            cats = [cats]
        subjects = [c.get("@term", "") for c in cats]

        arxiv_id_raw = entry.get("id", "")
        if isinstance(arxiv_id_raw, dict):
            arxiv_id_raw = arxiv_id_raw.get("#text", "")
        arxiv_id  = arxiv_id_raw.split("/abs/")[-1] if arxiv_id_raw else ""
        pdf_url   = f"https://arxiv.org/pdf/{arxiv_id}"
        abs_url   = f"https://arxiv.org/abs/{arxiv_id}"

        # Cari DOI bila ada
        doi_val = None
        links = entry.get("link", [])
        if isinstance(links, dict):
            links = [links]
        for lnk in links:
            if lnk.get("@title") == "doi":
                doi_val = lnk.get("@href", "").replace("https://doi.org/", "")

        published = entry.get("published", "")[:4] or None

        docs.append(make_document(
            source       = "arXiv",
            title        = entry.get("title", "(Tanpa judul)"),
            authors      = authors,
            year         = published,
            abstract     = entry.get("summary"),
            doi          = doi_val,
            url          = abs_url,
            download_url = pdf_url,
            pdf_url      = pdf_url,
            doc_type     = "preprint",
            subjects     = subjects,
            identifier   = arxiv_id,
        ))

    return {
        "source":    "arXiv",
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "results":   docs,
        "error":     None,
    }


def _error(msg):
    return {"source": "arXiv", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
