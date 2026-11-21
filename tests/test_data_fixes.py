"""
tests/test_data_fixes.py
Test regresi perbaikan data:
- filter vs extract di generic_json (DOAJ)
- extract dari dict (Gutenberg formats)
- normalisasi authors/subjects/language di make_document
- normalisasi authors di DatabaseService

Jalankan:
    python tests/test_data_fixes.py
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.handlers.generic_json import (  # noqa: E402
    CUSTOM_FIELD_HANDLERS,
    _build_item,
    _extract_field,
)
from app.services.database import db_service  # noqa: E402
from app.utils.normalizer import filter_unsafe, make_document  # noqa: E402


CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "setting_sumber.json",
)


def _source_config(source_id):
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    sources = data if isinstance(data, list) else data.get("sources", data)
    for source in sources:
        if source.get("id") == source_id:
            return source
    raise AssertionError(f"sumber {source_id!r} tidak ditemukan di setting_sumber.json")


class TestExtractField(unittest.TestCase):
    def test_filter_dijalankan_sebelum_extract(self):
        item = {
            "identifiers": [
                {"type": "issn", "id": "1234-5678"},
                {"type": "doi", "id": "10.1234/abc"},
            ]
        }
        field_config = {
            "path": "identifiers",
            "filter": {"type": "doi"},
            "extract": "id",
        }
        self.assertEqual(_extract_field(item, field_config), "10.1234/abc")

    def test_filter_tanpa_match_mengembalikan_none(self):
        item = {"identifiers": [{"type": "issn", "id": "1234-5678"}]}
        field_config = {
            "path": "identifiers",
            "filter": {"type": "doi"},
            "extract": "id",
        }
        self.assertIsNone(_extract_field(item, field_config))

    def test_extract_dari_dict(self):
        item = {"formats": {"application/pdf": "https://example.org/book.pdf"}}
        field_config = {"path": "formats", "extract": "application/pdf"}
        self.assertEqual(
            _extract_field(item, field_config),
            "https://example.org/book.pdf",
        )

    def test_extract_dari_list_tetap_list(self):
        item = {"authors": [{"name": "Alice"}, {"name": "Bob"}]}
        field_config = {"path": "authors", "extract": "name"}
        self.assertEqual(_extract_field(item, field_config), ["Alice", "Bob"])


class TestBuildItemDOAJ(unittest.TestCase):
    def test_doi_dan_url_hanya_mengambil_yang_sesuai_filter(self):
        item = {
            "id": "doaj-1",
            "bibjson": {
                "title": "Sample DOAJ Article",
                "author": [{"name": "Alice"}, {"name": "Bob"}],
                "year": "2024",
                "abstract": "Contoh abstrak.",
                "identifier": [
                    {"type": "issn", "id": "1234-5678"},
                    {"type": "doi", "id": "10.1234/abc"},
                    {"type": "eissn", "id": "8765-4321"},
                ],
                "link": [
                    {"type": "homepage", "url": "https://home.example"},
                    {"type": "fulltext", "url": "https://full.example/article"},
                ],
                "subject": [{"term": "Physics"}, {"term": "Mathematics"}],
                "language": ["en"],
            },
        }
        fields = _source_config("doaj")["response_mapping"]["fields"]
        doc = _build_item("doaj", item, fields, CUSTOM_FIELD_HANDLERS)

        self.assertEqual(doc["doi"], "10.1234/abc")
        self.assertEqual(doc["url"], "https://full.example/article")
        self.assertEqual(doc["pdf_url"], "https://full.example/article")
        self.assertEqual(doc["authors"], ["Alice", "Bob"])
        self.assertEqual(doc["subjects"], ["Physics", "Mathematics"])
        self.assertEqual(doc["language"], "en")


class TestBuildItemGutenberg(unittest.TestCase):
    def test_formats_dict_menghasilkan_url_string(self):
        item = {
            "id": 123,
            "title": "Sample Book",
            "authors": [{"name": "Jane Austen"}],
            "formats": {
                "text/plain; charset=utf-8": "https://example.org/123.txt",
                "application/pdf": "https://example.org/123.pdf",
                "image/jpeg": "https://example.org/123.jpg",
            },
            "subjects": ["Fiction"],
            "bookshelves": ["Classic Literature"],
            "languages": ["en"],
        }
        fields = _source_config("gutenberg")["response_mapping"]["fields"]
        doc = _build_item("gutenberg", item, fields, CUSTOM_FIELD_HANDLERS)

        self.assertEqual(doc["pdf_url"], "https://example.org/123.pdf")
        self.assertEqual(doc["thumbnail"], "https://example.org/123.jpg")
        self.assertEqual(doc["download_url"], "https://example.org/123.pdf")
        self.assertEqual(doc["url"], "https://www.gutenberg.org/ebooks/123")
        self.assertEqual(doc["authors"], ["Jane Austen"])
        self.assertEqual(doc["subjects"], ["Fiction", "Classic Literature"])
        self.assertEqual(doc["language"], "en")
        self.assertEqual(doc["identifier"], "123")
        self.assertEqual(doc["doc_type"], "book")


class TestNormalizer(unittest.TestCase):
    def test_string_authors_subjects_language_dinormalisasi(self):
        doc = make_document(
            source="test",
            title="Judul",
            authors="John Doe",
            subjects="Physics",
            language=["id", "en"],
            year=2024,
            pdf_url=["https://example.org/a.pdf"],
        )
        self.assertEqual(doc["authors"], ["John Doe"])
        self.assertEqual(doc["subjects"], ["Physics"])
        self.assertEqual(doc["language"], "id")
        self.assertEqual(doc["year"], "2024")
        self.assertEqual(doc["pdf_url"], "https://example.org/a.pdf")

    def test_list_of_dict_dinormalisasi(self):
        doc = make_document(
            source="test",
            title="Judul",
            authors=[{"name": "Alice"}, {"name": "Bob"}],
            subjects=[{"term": "AI"}, "ML"],
        )
        self.assertEqual(doc["authors"], ["Alice", "Bob"])
        self.assertEqual(doc["subjects"], ["AI", "ML"])

    def test_none_menjadi_list_kosong(self):
        doc = make_document(source="test", title="Judul")
        self.assertEqual(doc["authors"], [])
        self.assertEqual(doc["subjects"], [])
        self.assertIsNone(doc["language"])
        self.assertIsNone(doc["pdf_url"])


class TestDatabaseAuthors(unittest.TestCase):
    def test_string_author_tidak_diiterasi_per_karakter(self):
        self.assertEqual(
            db_service._normalize_authors("John Doe"),
            json.dumps(["john doe"]),
        )

    def test_list_author_diurutkan_lowercase(self):
        self.assertEqual(
            db_service._normalize_authors(["Bob", "alice"]),
            json.dumps(["alice", "bob"]),
        )

    def test_dict_author_mengambil_name(self):
        self.assertEqual(
            db_service._normalize_authors([{"name": "Alice Cooper"}]),
            json.dumps(["alice cooper"]),
        )

    def test_none_menjadi_list_kosong(self):
        self.assertEqual(db_service._normalize_authors(None), "[]")


class TestFilterUnsafeSubjects(unittest.TestCase):
    def test_subjects_string_tetap_terfilter(self):
        docs = [
            {"title": "Safe paper", "subjects": "physics"},
            {"title": "Unsafe paper", "subjects": "porn"},
        ]
        safe = filter_unsafe(docs)
        self.assertEqual([doc["title"] for doc in safe], ["Safe paper"])

    def test_subjects_list_tetap_terfilter(self):
        docs = [{"title": "Narkoba", "subjects": ["narkoba", "kriminal"]}]
        self.assertEqual(filter_unsafe(docs), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
