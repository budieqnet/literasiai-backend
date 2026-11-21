"""
app/utils/normalizer.py
Menyeragamkan format dokumen dari berbagai sumber menjadi satu skema bersama.
"""


def make_document(
    source: str,
    title: str,
    authors: list = None,
    year: str = None,
    abstract: str = None,
    doi: str = None,
    url: str = None,
    download_url: str = None,
    pdf_url: str = None,
    language: str = None,
    doc_type: str = "journal",   # journal | book | preprint
    subjects: list = None,
    publisher: str = None,
    identifier: str = None,
    thumbnail: str = None,
) -> dict:
    """
    Kembalikan dict dokumen dengan format standar LiterasiAI.
    Semua field opsional kecuali source dan title.
    """
    return {
        "source":        source,
        "doc_type":      doc_type,
        "title":         _as_scalar(title) or "",
        "authors":       _as_str_list(authors),
        "year":          _as_scalar(year),
        "abstract":      _as_scalar(abstract),
        "doi":           _as_scalar(doi),
        "url":           _as_scalar(url),
        "download_url":  _as_scalar(download_url),
        "pdf_url":       _as_scalar(pdf_url),
        "language":      _as_scalar(language),
        "subjects":      _as_str_list(subjects),
        "publisher":     _as_scalar(publisher),
        "identifier":    _as_scalar(identifier),
        "thumbnail":     _as_scalar(thumbnail),
        "classification": None,   # diisi oleh AI layer
    }


def _clean(text: str) -> str:
    """Hapus whitespace berlebih."""
    if not text:
        return text
    return " ".join(str(text).split())


def _as_scalar(value):
    """Ambil satu nilai string dari string/list/tuple/dict.

    Banyak sumber mengembalikan field skalar sebagai list (mis. language)
    atau dict (mis. author). Fungsi ini menjaga skema dokumen tetap konsisten.
    """
    if value is None:
        return None

    if isinstance(value, (list, tuple, set)):
        value = next(
            (item for item in value if item is not None and str(item).strip()),
            None,
        )
        if value is None:
            return None

    if isinstance(value, dict):
        value = (
            value.get("name")
            or value.get("term")
            or value.get("title")
            or value.get("value")
            or value.get("code")
        )
        if value is None:
            return None

    text = _clean(str(value))
    if text is None:
        return None
    text = str(text).strip()
    return text or None


def _as_str_list(value):
    """Normalisasi nilai tunggal/list/dict menjadi list string bersih."""
    if value is None:
        return []

    if isinstance(value, str):
        value = [value]
    elif not isinstance(value, (list, tuple, set)):
        value = [value]

    result = []
    for item in value:
        if item is None:
            continue
        if isinstance(item, dict):
            item = (
                item.get("name")
                or item.get("term")
                or item.get("title")
                or item.get("value")
            )
            if item is None:
                continue
        text = _clean(str(item))
        if text and text.strip():
            result.append(text.strip())
    return result


# ── Content Safety Filter ────────────────────────────────────────────────────

_FORBIDDEN_KEYWORDS = [
    "porno", "porn", "xxx", "dewasa", "bokep", "bugil", "telanjang", "naked",
    "nude", "nudity", "nudis", "seks", "sexy", "sex", "erotis", "erotic",
    "sensual", "vulgar", "vulva", "vagina", "penis", "testicle", "genital",
    "bikini", "lingerie", "intim", "intimate",
    "masturbasi", "masturbat", "orgasme", "orgasm",
    "playboy", "playmate", "hustler", "penthouse",
    "pornhub", "xvideos", "xnxx", "xhamster", "redtube", "onlyfans",
    "judi", "slot", "kasino", "casino", "togel", "poker", "taruhan",
    "betting", "gambling", "roulette", "blackjack",
    "kekerasan", "brutal", "sadis", "teror", "terror", "bom", "bomb",
    "senjata api", "firearm", "weapon", "genocide",
    "drug", "narkoba", "narkotika", "narcotic", "kokain", "cocaine",
    "heroin", "meth", "shabu", "ganja", "marijuana", "ecstasy",
]

_FORBIDDEN_CATEGORIES = [
    "porn", "adult", "erotic", "xxx", "nsfw",
    "gambling", "casino", "betting",
    "violence", "terrorism", "weapon",
]


def _keyword_match(text: str) -> bool:
    """Periksa apakah text mengandung forbidden keywords."""
    text_lower = text.lower()
    for kw in _FORBIDDEN_KEYWORDS:
        if kw in text_lower:
            return True
    return False


def filter_unsafe(docs: list) -> list:
    """Filter dokumen yang mengandung konten terlarang (porno, judi, kekerasan)."""
    if not docs:
        return docs

    safe = []
    for doc in docs:
        subjects = doc.get("subjects") or []
        if isinstance(subjects, str):
            subjects = [subjects]

        text = " ".join(filter(None, [
            doc.get("title", ""),
            doc.get("abstract", ""),
            " ".join(str(s) for s in subjects if s),
            doc.get("category", ""),
            doc.get("classification", "") or "",
        ]))

        if _keyword_match(text):
            continue

        cat = doc.get("category", "")
        if any(c in cat.lower() for c in _FORBIDDEN_CATEGORIES):
            continue

        safe.append(doc)
    return safe
