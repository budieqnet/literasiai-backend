import re
from app.utils.http import get as http_get
from app.utils.normalizer import make_document
from app.utils.logging import get_logger
from config import Config

log = get_logger("generic_json")


def _get_value(obj, path):
    if not path:
        return None
    parts = path.split(".")
    current = obj
    for part in parts:
        if current is None:
            return None
        if "[" in part and part.endswith("]"):
            name, idx = part[:-1].split("[")
            try:
                idx = int(idx)
                if isinstance(current, dict):
                    current = current.get(name)
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return None
            except (ValueError, IndexError, TypeError):
                return None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
    return current


def _extract_list(items, sub_field):
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        val = _get_value(item, sub_field) if sub_field else item
        if val is not None:
            result.append(val)
    return result


def _filter_extract(items, filter_key, filter_val, sub_field):
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get(filter_key) == filter_val:
            val = _get_value(item, sub_field) if sub_field else item
            if val is not None:
                return val
    return None


def _extract_field(item, field_config):
    if isinstance(field_config, str):
        if field_config.startswith("[") and field_config.endswith("]"):
            idx = int(field_config.strip("[]"))
            return item if isinstance(item, list) and idx < len(item) else None
        val = _get_value(item, field_config)
        if val is None:
            return None
        if isinstance(val, (list, dict)):
            return val
        return str(val)

    if isinstance(field_config, dict):
        if "static" in field_config:
            return field_config["static"]

        if "custom" in field_config:
            return None

        if "path" in field_config:
            raw = _get_value(item, field_config["path"])
            if raw is None:
                return None
            # filter dicek sebelum extract: konfigurasi seperti DOAJ memakai
            # filter + extract sekaligus (mis. hanya identifier type=doi).
            if "filter" in field_config:
                fk = list(field_config["filter"].keys())[0]
                fv = field_config["filter"][fk]
                sub = field_config.get("extract", "")
                result = _filter_extract(raw, fk, fv, sub)
                return result if result is not None else None
            if "extract" in field_config:
                # path bisa menunjuk dict (mis. formats Gutendex), bukan list.
                if isinstance(raw, dict):
                    val = raw.get(field_config["extract"])
                    return val if val is not None else None
                return _extract_list(raw, field_config["extract"])
            return raw

        if "combine" in field_config:
            combined = []
            for p in field_config["combine"]:
                vals = _get_value(item, p)
                if isinstance(vals, list):
                    combined.extend(vals)
                elif vals:
                    combined.append(vals)
            return combined

    return None


def _gutenberg_url(item, source_id):
    book_id = item.get("id")
    return f"https://www.gutenberg.org/ebooks/{book_id}" if book_id else None


def _gutenberg_download(item, source_id):
    formats = item.get("formats", {})
    for fmt in ["application/pdf", "application/epub+zip", "text/plain; charset=utf-8", "text/plain"]:
        url = formats.get(fmt)
        if url:
            return url
    return None


def _ol_url(item, source_id):
    key = item.get("key")
    return f"https://openlibrary.org{key}" if key else None


def _ol_thumbnail(item, source_id):
    cover_id = item.get("cover_i")
    return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None


def _archive_year(item, source_id):
    date = item.get("date", "")
    m = re.search(r"\b(19|20)\d{2}\b", str(date))
    return m.group(0) if m else None


def _archive_url(item, source_id):
    ident = item.get("identifier")
    return f"https://archive.org/details/{ident}" if ident else None


def _archive_download(item, source_id):
    ident = item.get("identifier")
    if not ident:
        return None
    formats = item.get("format", [])
    if isinstance(formats, str):
        formats = [formats]
    has_pdf = any("pdf" in f.lower() for f in formats)
    if has_pdf:
        return f"https://archive.org/download/{ident}/{ident}.pdf"
    return f"https://archive.org/details/{ident}"


def _archive_type(item, source_id):
    formats = item.get("format", [])
    if isinstance(formats, str):
        formats = [formats]
    if any(kw in f.lower() for kw in ["journal", "article"] for f in formats):
        return "journal"
    return "book"


CUSTOM_FIELD_HANDLERS = {
    "gutenberg_url": _gutenberg_url,
    "gutenberg_download": _gutenberg_download,
    "ol_url": _ol_url,
    "ol_thumbnail": _ol_thumbnail,
    "archive_year": _archive_year,
    "archive_url": _archive_url,
    "archive_download": _archive_download,
    "archive_type": _archive_type,
}


def _build_item(source_id, item, fields_config, custom_handlers):
    doc_kwargs = {"source": source_id}
    field_map = {
        "title": "title",
        "authors": "authors",
        "year": "year",
        "abstract": "abstract",
        "doi": "doi",
        "url": "url",
        "download_url": "download_url",
        "pdf_url": "pdf_url",
        "language": "language",
        "doc_type": "doc_type",
        "subjects": "subjects",
        "publisher": "publisher",
        "identifier": "identifier",
        "thumbnail": "thumbnail",
        "source_name": "source",
    }

    overrides = {}
    for json_field, doc_field in field_map.items():
        if json_field not in fields_config:
            continue
        field_cfg = fields_config[json_field]
        if isinstance(field_cfg, dict) and field_cfg.get("custom"):
            handler_key = field_cfg["custom"]
            handler_fn = custom_handlers.get(handler_key)
            if handler_fn:
                overrides[doc_field] = handler_fn(item, source_id)
        else:
            val = _extract_field(item, field_cfg)
            if val is not None:
                overrides[doc_field] = val

    for json_field, doc_field in field_map.items():
        if doc_field in overrides:
            doc_kwargs[doc_field] = overrides[doc_field]
        elif json_field in fields_config:
            val = _extract_field(item, fields_config[json_field])
            if val is not None:
                doc_kwargs[doc_field] = val

    source_final = doc_kwargs.pop("source", source_id)
    doc_type = doc_kwargs.pop("doc_type", "journal")
    return make_document(source=source_final, doc_type=doc_type, **doc_kwargs)


def _build_query(params_config, query, page, page_size, source_config):
    built = {}
    offset = (page - 1) * page_size
    for key, val in params_config.items():
        if val == "query":
            built[key] = query
        elif val == "page":
            built[key] = page
        elif val == "page_size":
            built[key] = page_size
        elif val == "offset":
            built[key] = offset
        elif val == "custom_query":
            media_type = source_config.get("media_type", "texts")
            built[key] = _build_archive_query(query, media_type)
        else:
            built[key] = val
    return built


def _build_archive_query(query, media_type="texts"):
    if media_type == "all":
        return f'({query}) AND licenseurl:(*creativecommons* OR *publicdomain*)'
    return f'({query}) AND mediatype:{media_type}'


class GenericJsonHandler:

    def __init__(self, source_config):
        self.source_config = source_config
        self.config = source_config.get("config", {})

    def search(self, query, page=1, page_size=10):
        sc = self.source_config
        cfg = self.config
        mapping = sc.get("response_mapping", {})
        fields_cfg = mapping.get("fields", {})

        base_url = cfg.get("base_url", "")
        endpoint = cfg.get("search_endpoint", "")
        method = cfg.get("method", "GET")
        params_cfg = cfg.get("params", {})
        auth_cfg = cfg.get("auth")
        headers_cfg = cfg.get("headers")

        url = base_url + endpoint
        if "{query}" in url:
            url = url.replace("{query}", query)

        params = _build_query(params_cfg, query, page, page_size, sc)

        headers = {}
        if headers_cfg:
            headers.update(headers_cfg)

        auth_headers = {}
        if auth_cfg:
            if auth_cfg.get("type") == "bearer":
                key_env = auth_cfg.get("key_env", "")
                api_key = getattr(Config, key_env, "") if key_env else ""
                if api_key:
                    auth_headers["Authorization"] = f"Bearer {api_key}"

        if auth_headers:
            headers.update(auth_headers)

        try:
            resp = http_get(url, params=params, headers=headers if headers else None)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error(f"[{sc['id']}] Request failed: {e}")
            return {
                "source": sc.get("name", sc["id"]),
                "total": 0,
                "page": page,
                "page_size": page_size,
                "results": [],
                "error": str(e),
            }

        results_path = mapping.get("results_path", "results")
        total_path = mapping.get("total_path", "total")
        raw_results = _get_value(data, results_path) or []
        total = _get_value(data, total_path) or 0

        if not isinstance(raw_results, list):
            raw_results = [raw_results] if raw_results else []

        docs = []
        for item in raw_results:
            doc = _build_item(sc["id"], item, fields_cfg, CUSTOM_FIELD_HANDLERS)
            if doc:
                docs.append(doc)

        return {
            "source": sc.get("name", sc["id"]),
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": docs,
            "error": None,
        }
