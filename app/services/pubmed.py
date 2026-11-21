"""
app/services/pubmed.py
Sumber: PubMed Central (NCBI E-utilities)
API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
"""
import xmltodict
from app.utils.http import get
from app.utils.normalizer import make_document

BASE_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
BASE_FETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BASE_SUMM   = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Cari artikel di PubMed Central (PMC).
    Menggunakan esearch → esummary pipeline.
    """
    try:
        # Langkah 1: dapatkan daftar ID
        retstart = (page - 1) * page_size
        search_resp = get(BASE_SEARCH, params={
            "db":         "pmc",
            "term":       query,
            "retmax":     page_size,
            "retstart":   retstart,
            "retmode":    "json",
            "usehistory": "n",
        })
        search_resp.raise_for_status()
        search_data = search_resp.json()

        esr    = search_data.get("esearchresult", {})
        ids    = esr.get("idlist", [])
        total  = int(esr.get("count", 0))

        if not ids:
            return _empty(total, page, page_size)

        # Langkah 2: ambil summary tiap ID
        summ_resp = get(BASE_SUMM, params={
            "db":      "pmc",
            "id":      ",".join(ids),
            "retmode": "json",
        })
        summ_resp.raise_for_status()
        summ_data = summ_resp.json()

    except Exception as e:
        return _error(str(e))

    docs = []
    uids = summ_data.get("result", {}).get("uids", [])

    for uid in uids:
        item    = summ_data["result"].get(uid, {})
        authors = [a.get("name", "") for a in item.get("authors", [])]
        pmcid   = item.get("ids", [{}])
        doi_val = next(
            (i.get("value") for i in item.get("articleids", []) if i.get("idtype") == "doi"),
            None
        )
        pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{uid}/"
        pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{uid}/pdf/"

        docs.append(make_document(
            source       = "PubMed Central",
            title        = item.get("title", "(Tanpa judul)"),
            authors      = authors,
            year         = item.get("pubdate", "")[:4] or None,
            doi          = doi_val,
            url          = pmc_url,
            download_url = pdf_url,
            pdf_url      = pdf_url,
            doc_type     = "journal",
            publisher    = item.get("source"),
            identifier   = f"PMC{uid}",
        ))

    return {
        "source":    "PubMed Central",
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "results":   docs,
        "error":     None,
    }


def _empty(total, page, page_size):
    return {"source": "PubMed Central", "total": total, "page": page,
            "page_size": page_size, "results": [], "error": None}

def _error(msg):
    return {"source": "PubMed Central", "total": 0, "page": 1,
            "page_size": 0, "results": [], "error": msg}
