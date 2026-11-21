# LiterasiAI — Agent Guide

## Run

```bash
cd /root/literasiai
source venv/bin/activate
python run.py           # serves on 0.0.0.0:5008
```

## Test (no pytest — standalone script)

```bash
source venv/bin/activate
python tests/test_services.py          # smoke test semua sumber
python tests/test_classifier.py       # unit test classifier (tanpa API)
python tests/test_classifier_accuracy.py  # akurasi classifier (memanggil API NVIDIA)
python tests/benchmark_classifier.py  # benchmark multi-model pada dataset 120 sampel (API NVIDIA)
python tests/compare_benchmarks.py    # bandingkan dua file hasil benchmark
python tests/test_database.py         # unit + integrasi MySQL (DB sementara)
python tests/test_data_fixes.py       # regresi filter/extract + normalisasi dokumen
python tests/test_security.py         # auth admin, SSRF, path traversal, debug
```

## Architecture

- **Flask app factory** in `app/__init__.py`, blueprints registered there (no `routes/__init__.py`).
- **Config-driven sources**: `config/setting_sumber.json` is SOT for all 16 sources. Three handler types:
  - `generic_json` — fully config-driven via JSON response mapping; no Python needed.
  - `custom_*` — Python handler in `app/services/<name>.py`, registered in `registry.py:_import_custom_handler()` mapping dict.
  - `subscription` — Crossref-based handler for 5 subscription publishers, registered in `handlers/__init__.py:HANDLER_MAP`.
- **Generic JSON handler** (`app/services/handlers/generic_json.py`) — supports path extraction, filter, extract, combine, custom field handlers (Gutenberg, Open Library, Archive.org derived fields).
- **Custom handler mapping** lives in `registry.py` lines 32–37. Add new custom handlers there.
- **Database**: `DatabaseService` (`app/services/database.py`) auto-saves search results to MySQL table `search_results` with deduplication (title+source+authors). `db_service.init_db()` is called at startup in `create_app()`. Config: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_CONNECT_TIMEOUT`. `health()` runs `SELECT 1`; `/health` exposes DB status. Failures degrade gracefully (no crash), but there is no automatic reconnect yet.
- **Subscription handler**: `SubscriptionHandler` (`app/services/handlers/subscription.py`) queries Crossref API filtered by DOI prefix for ScienceDirect, Wiley, SpringerLink, Emerald, T&F. Metadata-only (no full text).
- **Download pipeline**: `config/download_methods.json` defines chained priority methods (1–10). `_resolve_by_doi()` tries each until one succeeds.
- **Parallel search**: `concurrent.futures.ThreadPoolExecutor` in `search.py`.
- **Cache**: `TTLCache` (256 items, 600s TTL) in `search.py`.
- **Classifier**: `app/services/nvidia.py` calls NVIDIA Nemotron via the OpenAI-compatible NIM endpoint (`integrate.api.nvidia.com/v1`), uses JSON-schema `response_format`, disables thinking, retries/rotates keys, then falls back to keyword matching in `app/routes/classify.py`. Default model is `nvidia/nemotron-3.5-lightning-30b-a3b`; override with `NVIDIA_MODEL`.
- **Classifier cache**: `TTLCache` keyed by model + prompt hash + normalized document fields. Defaults: 24 h TTL, 2,048 entries, enabled. Helpers: `clear_cache()`, `cache_info()` in `nvidia.py`. Disable with `NVIDIA_CACHE_ENABLED=0`.
- **Content filter**: `filter_unsafe()` in `app/utils/normalizer.py` — blocks porn/gambling/violence/drug docs by keyword.
- **Security**: `app/utils/security.py` validates download URLs (http/https only, public IPs only, redirects revalidated) and sanitizes/confines filenames. `app/utils/auth.py` protects `/api/admin/download-methods` with `ADMIN_API_KEY` (Bearer or `X-Admin-Key`); unset key fails closed with 503.

## Key files

| Path | Role |
|---|---|
| `run.py` | Entrypoint, port **5008** |
| `app/__init__.py` | create_app(), CORS, blueprint registration |
| `config/setting_sumber.json` | Source definitions (add sources here) |
| `config/download_methods.json` | Download method chain |
| `config/settings.py` | Env loading, Config class |
| `app/services/registry.py` | SourceRegistry singleton, custom handler mapping |
| `app/services/database.py` | DatabaseService — MySQL auto-save, dedup, health check |
| `app/services/handlers/generic_json.py` | Config-driven handler |
| `app/services/handlers/subscription.py` | Crossref handler for 5 subscription sources |
| `app/routes/download.py` | Download with chained method resolution; SSRF-safe fetch + filename confinement |
| `app/utils/security.py` | SSRF guard (`validate_public_url`, `safe_request`) + filename/path helpers |
| `app/utils/auth.py` | Admin auth (`ADMIN_API_KEY`, fail closed) |
| `app/services/nvidia.py` | NVIDIA Nemotron classifier (NIM API, JSON schema, retry, cache, multi-key) |
| `app/routes/classify.py` | Classifier endpoint + keyword fallback, 30 categories |
| `app/utils/normalizer.py` | `make_document()` canonical schema, `filter_unsafe()` |
| `session_literasi.md` | Historical bugfix notes (venv arch, sinta NameError, list→str bug) |
| `PROJECT_ANALYSIS.md` | Analysis snapshot 2026-10-22: verified bugs, security risks, priorities |

## Known issues

- **Neliti** — 403 Forbidden (Cloudflare)
- **Garuda, SINTA** — DNS blocked (regional restriction); not code bugs
- **CORE** — needs API key in production for reasonable rate limits
- **Database** — MySQL connection failures caught gracefully (backend still works); no reconnect logic yet. Connection timeout is configurable via `MYSQL_CONNECT_TIMEOUT`.
- **NVIDIA free endpoint** — trial/evaluation only (not production), ~40 RPM shared per account; production needs a paid endpoint or self-hosted NIM
- **Admin API** — `/api/admin/download-methods` requires `ADMIN_API_KEY`; if unset, requests fail closed with 503
- These five gracefully degrade (errors are handled, no crash)

## .env

NVIDIA classifier keys are read from `.env` by `_get_api_keys()`: `NVIDIA_API_KEY`, `NVIDIA_API_KEYS` (comma-separated), then `NVIDIA_API_KEY_1..3` (deduplicated, in that order). Keys are tried in sequence on auth/quota errors before falling back to keyword matching. Model settings: `NVIDIA_MODEL` (default `nvidia/nemotron-3.5-lightning-30b-a3b`), `NVIDIA_BASE_URL`, `NVIDIA_TIMEOUT`, `NVIDIA_MAX_RETRIES`. Cache settings: `NVIDIA_CACHE_ENABLED`, `NVIDIA_CACHE_TTL`, `NVIDIA_CACHE_SIZE`.

Admin auth uses `ADMIN_API_KEY` (generated in `.env`). `FLASK_DEBUG` defaults to `0`; set it to `1` only for local development. The PyInstaller binary does not bundle `.env`.

## Apache proxy

`/etc/apache2/sites-enabled/000-default.conf` proxies `/api/` and `/health` to port 5008. Setup script: `setup_apache_proxy.sh`.

## PyInstaller build

```bash
source venv/bin/activate
pyinstaller --clean --noconfirm literasiai.spec
```

Output: `dist/literasiai/literasiai`. Config loading order: external (same dir as binary) > `_internal/config/`.
