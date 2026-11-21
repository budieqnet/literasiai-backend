"""
app/services/__init__.py
Registry semua sumber data LiterasiAI — dikonfigurasi via setting_sumber.json.
Import dari sini untuk konsistensi.
"""
from .registry import SourceRegistry
from .openaccess import lookup_doi
from .openlibrary import search_by_isbn

registry = SourceRegistry()

SOURCE_MAP = registry.SOURCE_MAP
JOURNAL_SOURCES = registry.JOURNAL_SOURCES
BOOK_SOURCES = registry.BOOK_SOURCES
ALL_SOURCES = registry.ALL_SOURCES
