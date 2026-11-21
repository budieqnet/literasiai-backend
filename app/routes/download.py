"""
app/routes/download.py
Endpoint download file — ebook, ejournal, PDF dari berbagai sumber.
Konfigurasi download methods via JSON file (config/download_methods.json).
"""
import json
import os
import sys
import uuid
import requests
from flask import Blueprint, Response, jsonify, request, stream_with_context

from config import Config
from app.utils.logging import get_logger
from app.utils.security import (
    UnsafeURLError,
    content_disposition,
    resolve_download_path,
    safe_request,
    validate_filename,
    validate_public_url,
)

log = get_logger("download")
download_bp = Blueprint("download", __name__, url_prefix="/api/download")

CHUNK_SIZE = 8 * 1024


def _get_base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _get_download_dir():
    d = os.path.join(_get_base_dir(), "downloads")
    os.makedirs(d, exist_ok=True)
    return d


def _get_config_path():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
        external = os.path.join(base, "config", "download_methods.json")
        if os.path.exists(external):
            return external
        return os.path.join(sys._MEIPASS, "config", "download_methods.json")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "download_methods.json"
    )


DOWNLOAD_DIR = _get_download_dir()
CONFIG_PATH = _get_config_path()


def _load_download_config() -> dict:
    """Load download config dari JSON file."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load download config: {e}")
        return {"download_methods": [], "settings": {}}


def _get_settings() -> dict:
    """Get download settings dari config."""
    config = _load_download_config()
    settings = config.get("settings", {})
    return {
        "max_file_size": (settings.get("max_file_size_mb", 500)) * 1024 * 1024,
        "chunk_size": (settings.get("chunk_size_kb", 8)) * 1024,
        "timeout": settings.get("timeout_seconds", 60),
        "retry_attempts": settings.get("retry_attempts", 3),
    }


def _get_enabled_methods() -> list:
    """Get enabled download methods, diurutkan berdasarkan priority."""
    config = _load_download_config()
    methods = config.get("download_methods", [])
    enabled = [m for m in methods if m.get("enabled", False)]
    enabled.sort(key=lambda x: x.get("priority", 999))
    return enabled


def _stream_download(url: str, filepath: str, settings: dict = None) -> tuple:
    """
    Download file via streaming dengan progress.
    Return (success, filename, filesize, error).
    """
    if settings is None:
        settings = _get_settings()

    max_size = settings.get("max_file_size", 500 * 1024 * 1024)
    chunk_size = settings.get("chunk_size", CHUNK_SIZE)
    timeout = settings.get("timeout", 60)

    resp = None
    try:
        headers = {"User-Agent": Config.USER_AGENT}
        resp = safe_request(
            "GET",
            url,
            headers=headers,
            timeout=timeout,
            stream=True,
        )
        resp.raise_for_status()

        if resp.is_redirect:
            return False, None, None, "Redirect tanpa Location"

        content_length = resp.headers.get("content-length")
        try:
            declared_size = int(content_length) if content_length else 0
        except (TypeError, ValueError):
            declared_size = 0
        if declared_size > max_size:
            return False, None, None, (
                f"File terlalu besar ({declared_size / 1024 / 1024:.1f}MB, "
                f"max {max_size / 1024 / 1024:.0f}MB)"
            )

        total = 0
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
                    if total > max_size:
                        os.remove(filepath)
                        return False, None, None, "File terlalu besar saat download"

        return True, os.path.basename(filepath), total, None

    except UnsafeURLError as e:
        return False, None, None, f"URL tidak diizinkan: {e}"
    except requests.exceptions.Timeout:
        return False, None, None, "Timeout saat download"
    except requests.exceptions.RequestException as e:
        return False, None, None, f"Request error: {e}"
    except IOError as e:
        return False, None, None, f"IO error: {e}"
    finally:
        if resp is not None:
            resp.close()


def _build_filename(doc: dict, extension: str = "pdf") -> str:
    """Bikin filename dari metadata dokumen."""
    title = doc.get("title", "unknown")[:50]
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    year = doc.get("year", "")
    return f"{safe_title}_{year}.{extension}".strip()


@download_bp.route("", methods=["POST"])
def download_document():
    """
    Download dokumen dari URL, DOI, atau ISBN.
    Menggunakan download methods dari config.

    POST /api/download

    Body (JSON):
      url        : URL langsung ke file (prioritas utama)
      doi        : DOI dokumen → cari PDF via configured methods
      isbn       : ISBN buku → cari di Open Library
      source     : Sumber spesifik (arxiv, gutenberg, dll.)
      id         : ID dokumen di sumber (optional, sebagai fallback)
      filename   : Nama file custom (optional)
    """
    data = request.get_json() or {}
    url = data.get("url")
    doi = (data.get("doi") or "").strip()
    isbn = (data.get("isbn") or "").strip().replace("-", "")
    filename = data.get("filename")

    if filename:
        try:
            filename = validate_filename(filename)
        except ValueError as e:
            return jsonify({"error": f"Filename tidak valid: {e}"}), 400

    if not url and not doi and not isbn:
        return jsonify({
            "error": "Pilih salah satu: url, doi, atau isbn.",
            "hint": '{"url": "https://..."} atau {"doi": "10.xxxx/xxx"} atau {"isbn": "978..."}',
        }), 400

    settings = _get_settings()
    methods = _get_enabled_methods()
    resolved_url = url
    doc = None

    if not resolved_url and doi:
        log.info(f"Resolving DOI {doi} for download using {len(methods)} methods")
        resolved_url, doc = _resolve_by_doi(doi, methods, settings)
        if not resolved_url:
            return jsonify({
                "error": f"Tidak bisa menemukan PDF untuk DOI {doi}",
                "doi": doi,
                "methods_tried": [m.get("id") for m in methods],
            }), 404

    if not resolved_url and isbn:
        log.info(f"Resolving ISBN {isbn} for download")
        resolved_url, doc = _resolve_by_isbn(isbn)
        if not resolved_url:
            return jsonify({
                "error": f"Tidak bisa menemukan PDF untuk ISBN {isbn}",
                "isbn": isbn,
            }), 404

    if not resolved_url:
        return jsonify({"error": "Tidak ada URL yang bisa di-resolve."}), 400

    try:
        resolved_url = validate_public_url(resolved_url)
    except UnsafeURLError as e:
        return jsonify({
            "error": f"URL tidak diizinkan: {e}",
            "url": resolved_url,
        }), 400

    log.info(f"Downloading {resolved_url}")

    file_id = uuid.uuid4().hex[:8]
    ext = _get_extension(resolved_url)
    if not filename:
        filename = f"literasiai_{file_id}.{ext}"

    try:
        filepath = resolve_download_path(DOWNLOAD_DIR, filename)
    except ValueError as e:
        return jsonify({"error": f"Filename tidak valid: {e}"}), 400

    success, fname, fsize, error = _stream_download(resolved_url, filepath, settings)

    if not success:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": error, "url": resolved_url}), 502

    log.info(f"Download complete: {fname} ({fsize / 1024:.1f}KB)")
    try:
        display_path = os.path.relpath(filepath, _get_base_dir())
    except ValueError:
        display_path = fname
    return jsonify({
        "status": "success",
        "filename": fname,
        "filesize": fsize,
        "filepath": display_path,
        "url": resolved_url,
        "doc": doc,
    })


@download_bp.route("/methods", methods=["GET"])
def list_download_methods():
    """
    Daftar download methods yang dikonfigurasi.

    GET /api/download/methods
    """
    config = _load_download_config()
    methods = config.get("download_methods", [])
    settings = config.get("settings", {})

    return jsonify({
        "status": "success",
        "total": len(methods),
        "enabled_count": sum(1 for m in methods if m.get("enabled", False)),
        "methods": methods,
        "settings": settings,
    })


@download_bp.route("/stream", methods=["GET"])
def stream_download():
    """
    Stream file untuk di-download langsung.

    GET /api/download/stream?url=<url>&filename=<name>
    """
    url = request.args.get("url")
    try:
        filename = validate_filename(
            request.args.get("filename"),
            default="document.pdf",
        )
    except ValueError as e:
        return jsonify({"error": f"Filename tidak valid: {e}"}), 400

    if not url:
        return jsonify({"error": "Parameter 'url' wajib."}), 400

    try:
        validate_public_url(url)
    except UnsafeURLError as e:
        return jsonify({"error": f"URL tidak diizinkan: {e}"}), 400

    settings = _get_settings()
    resp = None

    try:
        headers = {"User-Agent": Config.USER_AGENT}
        resp = safe_request(
            "GET",
            url,
            headers=headers,
            timeout=settings.get("timeout", 60),
            stream=True,
        )
        resp.raise_for_status()

        if resp.is_redirect:
            resp.close()
            return jsonify({"error": "Redirect tanpa Location."}), 502

        content_length = resp.headers.get("content-length")
        try:
            declared_size = int(content_length) if content_length else 0
        except (TypeError, ValueError):
            declared_size = 0
        max_size = settings.get("max_file_size", 500 * 1024 * 1024)
        if declared_size > max_size:
            resp.close()
            return jsonify({
                "error": (
                    f"File terlalu besar ({declared_size / 1024 / 1024:.1f}MB, "
                    f"max {max_size / 1024 / 1024:.0f}MB)"
                )
            }), 413

        chunk_size = settings.get("chunk_size", CHUNK_SIZE)

        def generate():
            total = 0
            try:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_size:
                        log.warning("Stream melebihi batas ukuran; dihentikan")
                        break
                    yield chunk
            finally:
                resp.close()

        content_type = resp.headers.get(
            "content-type", "application/octet-stream"
        ).split(";", 1)[0].strip() or "application/octet-stream"

        response = Response(
            stream_with_context(generate()),
            mimetype=content_type,
        )
        response.headers["Content-Disposition"] = content_disposition(filename)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    except UnsafeURLError as e:
        if resp is not None:
            resp.close()
        return jsonify({"error": f"URL tidak diizinkan: {e}"}), 400
    except requests.exceptions.Timeout:
        if resp is not None:
            resp.close()
        return jsonify({"error": "Timeout saat stream."}), 504
    except requests.exceptions.RequestException as e:
        if resp is not None:
            resp.close()
        return jsonify({"error": f"Request error: {e}"}), 502
    except Exception as e:
        if resp is not None:
            resp.close()
        log.error(f"Stream failed: {e}")
        return jsonify({"error": str(e)}), 502


@download_bp.route("/info", methods=["POST"])
def download_info():
    """
    Cek info download (size, content-type) tanpa download.

    POST /api/download/info
    Body: {"url": "..."} atau {"doi": "..."} atau {"isbn": "..."}
    """
    data = request.get_json() or {}
    url = data.get("url")
    doi = (data.get("doi") or "").strip()
    isbn = (data.get("isbn") or "").strip().replace("-", "")

    resolved_url = url

    if not resolved_url and doi:
        methods = _get_enabled_methods()
        resolved_url, _ = _resolve_by_doi(doi, methods, _get_settings())
    if not resolved_url and isbn:
        resolved_url, _ = _resolve_by_isbn(isbn)

    if not resolved_url:
        return jsonify({"error": "Tidak bisa resolve URL."}), 400

    try:
        resolved_url = validate_public_url(resolved_url)
    except UnsafeURLError as e:
        return jsonify({
            "error": f"URL tidak diizinkan: {e}",
            "url": resolved_url,
        }), 400

    resp = None
    try:
        headers = {"User-Agent": Config.USER_AGENT}
        resp = safe_request("HEAD", resolved_url, headers=headers, timeout=10)
        return jsonify({
            "url": resolved_url,
            "content_type": resp.headers.get("content-type"),
            "content_length": resp.headers.get("content-length"),
            "status_code": resp.status_code,
        })
    except UnsafeURLError as e:
        return jsonify({
            "error": f"URL tidak diizinkan: {e}",
            "url": resolved_url,
        }), 400
    except Exception as e:
        return jsonify({"error": str(e), "url": resolved_url}), 502
    finally:
        if resp is not None:
            resp.close()


def _resolve_by_doi(doi: str, methods: list, settings: dict) -> tuple:
    """
    Resolve DOI ke PDF URL menggunakan configured methods.
    Return (url, doc).
    """
    clean_doi = doi.lstrip("https://doi.org/").lstrip("http://dx.doi.org/")

    for method in methods:
        method_id = method.get("id")
        config = method.get("config", {})
        source = config.get("source", "")

        log.debug(f"Trying method: {method_id} for DOI {clean_doi}")

        try:
            if source == "unpaywall":
                url, doc = _try_unpaywall(clean_doi)
            elif source == "crossref":
                url, doc = _try_crossref(clean_doi)
            elif source == "pubmed":
                url, doc = _try_pubmed(clean_doi)
            else:
                continue

            if url:
                log.info(f"Resolved via {method_id}: {url}")
                return url, doc

        except Exception as e:
            log.debug(f"Method {method_id} failed: {e}")
            continue

    return None, None


def _try_unpaywall(doi: str) -> tuple:
    """Coba Unpaywall."""
    from app.services.openaccess import lookup_doi

    oa = lookup_doi(doi)
    if oa.get("is_oa"):
        best_url = oa.get("best_url")
        if best_url:
            if not best_url.lower().endswith(".pdf"):
                best_url = best_url.replace("/pdf", "").replace("/full", "") + ".pdf"
            doc = oa.get("results", [{}])[0] if oa.get("results") else {}
            return best_url, doc
    return None, None


def _try_crossref(doi: str) -> tuple:
    """Coba Crossref untuk dapat link PDF."""
    from app.utils.http import get

    try:
        resp = get(f"https://api.crossref.org/works/{doi}")
        if resp.ok:
            data = resp.json().get("message", {})
            links = data.get("link", [])
            for link in links:
                if link.get("content-type", "").startswith("application/pdf"):
                    return link.get("URL"), {"title": data.get("title", [""])[0]}
    except Exception:
        pass
    return None, None


def _try_pubmed(doi: str) -> tuple:
    """Coba PubMed Central untuk DOI."""
    from app.utils.http import get

    try:
        resp = get(
            "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
            params={"ids": doi, "format": "json", "tool": "literasiai", "email": "admin@literasiai.id"}
        )
        if resp.ok:
            data = resp.json()
            records = data.get("records", [])
            if records:
                pmcid = records[0].get("pmcid")
                if pmcid:
                    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/"
                    return pdf_url, {"title": records[0].get("title", "")}
    except Exception:
        pass
    return None, None


def _resolve_by_isbn(isbn: str) -> tuple:
    """Resolve ISBN ke PDF URL via Open Library."""
    from app.services.openlibrary import search_by_isbn

    doc = search_by_isbn(isbn)
    if not doc:
        return None, None

    download_url = doc.get("download_url") or doc.get("pdf_url")
    return download_url, doc


def _get_extension(url: str) -> str:
    """Deteksi extension dari URL."""
    url_lower = url.lower()
    for ext in ("pdf", "epub", "txt", "html", "zip"):
        if f".{ext}" in url_lower:
            return ext
    return "pdf"