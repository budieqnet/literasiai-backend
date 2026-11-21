"""
tests/test_database.py
Unit test helper DatabaseService + integration test MySQL.

Integration test membuat database sementara `literasiai_test_*`, menjalankan
save/dedup, lalu menghapusnya. Tidak menyentuh database produksi.

Jalankan:
    python tests/test_database.py
"""
import os
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mysql.connector import Error as MySQLError  # noqa: E402

from app.services.database import DatabaseService  # noqa: E402


def _doc(**overrides):
    data = {
        "source": "test-source",
        "doc_type": "journal",
        "title": "Database Connection Integration Test",
        "authors": ["Alice", "Bob"],
        "year": "2026",
        "abstract": "Testing save and dedup.",
        "doi": None,
        "url": "https://example.org/test",
        "language": "en",
        "subjects": ["Testing"],
        "publisher": "Test Publisher",
        "identifier": "test-1",
    }
    data.update(overrides)
    return data


class TestHelpers(unittest.TestCase):
    def setUp(self):
        self.service = DatabaseService()

    def test_author_texts_normalizes_dict_and_string(self):
        authors = [{"name": "Alice"}, " Bob ", {"term": "Carol"}]
        self.assertEqual(self.service._author_texts(authors), ["alice", "bob", "carol"])

    def test_author_texts_handles_empty(self):
        self.assertEqual(self.service._author_texts(None), [])
        self.assertEqual(self.service._author_texts(""), [])

    def test_normalize_authors_is_sorted_json(self):
        normalized = self.service._normalize_authors(["Bob", "alice"])
        self.assertEqual(normalized, '["alice", "bob"]')

    def test_safe_val(self):
        self.assertIsNone(self.service._safe_val(None))
        self.assertIsNone(self.service._safe_val([]))
        self.assertEqual(self.service._safe_val(["a", "b"]), "a; b")
        self.assertEqual(self.service._safe_val("abcdef", max_len=4), "abcd")
        self.assertEqual(self.service._safe_val(123), "123")

    def test_normalize_doi(self):
        self.assertIsNone(self.service._normalize_doi(None))
        self.assertIsNone(self.service._normalize_doi(""))
        self.assertEqual(self.service._normalize_doi("10.1038/nature12373"), "10.1038/nature12373")
        self.assertEqual(self.service._normalize_doi("https://doi.org/10.1038/nature12373"), "10.1038/nature12373")
        self.assertEqual(self.service._normalize_doi("http://dx.doi.org/10.1038/nature12373"), "10.1038/nature12373")
        self.assertEqual(self.service._normalize_doi("doi: 10.1038/nature12373"), "10.1038/nature12373")

    def test_extract_isbn(self):
        self.assertIsNone(self.service._extract_isbn({}))
        self.assertEqual(self.service._extract_isbn({"isbn": "978-0-13-468599-1"}), "9780134685991")
        self.assertEqual(self.service._extract_isbn({"doc_type": "book", "identifier": "0-201-63361-2"}), "0201633612")
        self.assertEqual(self.service._extract_isbn({"doc_type": "book", "identifier": "9780134685991"}), "9780134685991")
        self.assertIsNone(self.service._extract_isbn({"doc_type": "preprint", "identifier": "2306.04338v1"}))


class TestDatabaseIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = DatabaseService()
        cls.db_name = f"literasiai_test_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        cls.service.database = cls.db_name

        try:
            ok = cls.service.init_db()
        except MySQLError as exc:
            raise unittest.SkipTest(f"MySQL tidak tersedia: {exc}")

        if not ok:
            raise unittest.SkipTest(
                f"MySQL tidak tersedia: {cls.service.last_error}"
            )

    @classmethod
    def tearDownClass(cls):
        try:
            conn = cls.service._connect(database=False)
            try:
                cursor = conn.cursor()
                cursor.execute(f"DROP DATABASE IF EXISTS `{cls.db_name}`")
                conn.commit()
                cursor.close()
            finally:
                conn.close()
        except MySQLError:
            pass

    def setUp(self):
        conn = self.service.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM search_results")
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    def _count_rows(self):
        conn = self.service.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM search_results")
            return cursor.fetchone()[0]
        finally:
            cursor.close()
            conn.close()

    def test_health_reports_up(self):
        status = self.service.health()
        self.assertEqual(status["status"], "up")
        self.assertEqual(status["database"], self.db_name)
        self.assertIn("host", status)
        self.assertIn("port", status)

    def test_save_and_dedup(self):
        doc = _doc()

        self.assertEqual(self.service.save_search_results([doc], "query-1"), (1, 0))
        self.assertEqual(self._count_rows(), 1)

        # Dokumen identik harus dianggap duplikat.
        self.assertEqual(self.service.save_search_results([doc], "query-1"), (0, 1))
        self.assertEqual(self._count_rows(), 1)

        # Judul/source sama tetapi authors berbeda -> dokumen baru.
        other = _doc(authors=["Carol"])
        self.assertEqual(self.service.save_search_results([other], "query-1"), (1, 0))
        self.assertEqual(self._count_rows(), 2)

    def test_document_without_title_is_skipped(self):
        doc = _doc(title="", source="test-source")
        self.assertEqual(self.service.save_search_results([doc], "query-1"), (0, 0))
        self.assertEqual(self._count_rows(), 0)

    def test_empty_docs_returns_zero(self):
        self.assertEqual(self.service.save_search_results([], "query-1"), (0, 0))

    def test_complex_fields_are_stored_as_json(self):
        doc = _doc(
            title="JSON Field Test",
            authors=["Alice", "Bob"],
            subjects=["Computer Vision", "Testing"],
        )
        self.assertEqual(self.service.save_search_results([doc], "query-json"), (1, 0))

        conn = self.service.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT authors, subjects, search_query FROM search_results WHERE title = %s",
                ("JSON Field Test",),
            )
            row = cursor.fetchone()
            cursor.close()
        finally:
            conn.close()

        self.assertEqual(row["authors"], '["Alice", "Bob"]')
        self.assertEqual(row["subjects"], '["Computer Vision", "Testing"]')
        self.assertEqual(row["search_query"], "query-json")

    def test_dedup_by_doi(self):
        # Dokumen pertama dengan DOI
        doc1 = _doc(title="Paper Pertama", source="DOAJ", doi="10.1038/nature12373")
        self.assertEqual(self.service.save_search_results([doc1], "test"), (1, 0))
        self.assertEqual(self._count_rows(), 1)

        # Dokumen kedua dari sumber berbeda, judul berbeda, tapi DOI SAMA (URL format) -> harus di-skip!
        doc2 = _doc(title="Paper Kedua Alias", source="Crossref", doi="https://doi.org/10.1038/nature12373")
        self.assertEqual(self.service.save_search_results([doc2], "test"), (0, 1))
        self.assertEqual(self._count_rows(), 1)

    def test_dedup_by_isbn(self):
        # Buku pertama dengan ISBN
        book1 = _doc(title="Clean Code", doc_type="book", source="Open Library", identifier="978-0-13-235088-4")
        self.assertEqual(self.service.save_search_results([book1], "test"), (1, 0))
        self.assertEqual(self._count_rows(), 1)

        # Buku kedua dari sumber berbeda, format ISBN tanpa strip -> harus di-skip!
        book2 = _doc(title="Clean Code Alternative", doc_type="book", source="Internet Archive", isbn="9780132350884")
        self.assertEqual(self.service.save_search_results([book2], "test"), (0, 1))
        self.assertEqual(self._count_rows(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
