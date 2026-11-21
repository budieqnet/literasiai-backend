"""
app/services/handlers/subscription.py
Handler untuk sumber berlangganan (ScienceDirect, Wiley, Springer, Emerald, T&F).
Menggunakan Crossref API untuk pencarian metadata.
Full text membutuhkan akses berlangganan institusi.
"""
import re
import html
from app.utils.http import get as http_get
from app.utils.normalizer import make_document
from app.utils.logging import get_logger

log = get_logger("subscription")

CROSSREF_BASE = "https://api.crossref.org/works"


def _clean_abstract(raw):
    """Bersihkan tag HTML dari abstract Crossref."""
    if not raw:
        return None
    text = re.sub(r'<[^>]+>', '', raw)
    text = html.unescape(text)
    return " ".join(text.split())[:1000]


def _parse_authors(author_list):
    """Parse daftar author dari format Crossref."""
    if not author_list:
        return []
    result = []
    for a in author_list:
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{given} {family}".strip()
        if name:
            result.append(name)
    return result


def _parse_year(item):
    """Ekstrak tahun publikasi dari berbagai field Crossref."""
    for key in ("published-print", "published-online", "created"):
        parts = item.get(key, {})
        if isinstance(parts, dict):
            dp = parts.get("date-parts")
            if dp and len(dp) > 0 and len(dp[0]) > 0:
                return str(dp[0][0])
    return None


class SubscriptionHandler:

    def __init__(self, source_config):
        self.source_config = source_config
        self.cfg = source_config.get("config", {})

    def search(self, query, page=1, page_size=10):
        sc = self.source_config
        cfg = self.cfg
        prefixes = cfg.get("doi_prefixes", [])
        url_template = cfg.get("url_template", "https://doi.org/{doi}")
        source_name = sc.get("name", sc["id"])

        if not prefixes:
            return self._error(source_name, "No DOI prefixes configured")

        offset = (page - 1) * page_size
        prefix_filter = ",".join(f"prefix:{p}" for p in prefixes)

        params = {
            "query": query,
            "filter": prefix_filter,
            "rows": page_size,
            "offset": offset,
        }

        try:
            resp = http_get(CROSSREF_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error(f"[{sc['id']}] Crossref request failed: {e}")
            return self._error(source_name, str(e))

        message = data.get("message", {})
        total = message.get("total-results", 0)
        items = message.get("items", [])

        docs = []
        for item in items:
            doi = item.get("DOI", "")
            titles = item.get("title", [])
            title = titles[0] if titles else "(Tanpa judul)"

            authors = _parse_authors(item.get("author", []))
            year = _parse_year(item)
            abstract = _clean_abstract(item.get("abstract"))
            subjects = item.get("subject", [])
            publisher = item.get("publisher", "")
            url = url_template.replace("{doi}", doi)

            docs.append(make_document(
                source=source_name,
                doc_type="journal",
                title=title,
                authors=authors,
                year=year,
                abstract=abstract,
                doi=doi,
                url=url,
                download_url=None,
                pdf_url=None,
                subjects=subjects,
                publisher=publisher,
                identifier=doi,
            ))

        return {
            "source": source_name,
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": docs,
            "error": None,
        }

    def _error(self, source_name, msg):
        return {
            "source": source_name,
            "total": 0,
            "page": 1,
            "page_size": 0,
            "results": [],
            "error": msg,
        }
