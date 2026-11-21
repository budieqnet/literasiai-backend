"""
app/services/database.py
Service database untuk menyimpan dan menduplikasi hasil pencarian.
"""
import json
import re

import mysql.connector
from mysql.connector import Error as MySQLError

from config import Config
from app.utils.logging import get_logger

log = get_logger("database")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


class DatabaseService:

    def __init__(self):
        self.host = Config.MYSQL_HOST
        self.port = int(getattr(Config, "MYSQL_PORT", 3306))
        self.user = Config.MYSQL_USER
        self.password = Config.MYSQL_PASSWORD
        self.database = Config.MYSQL_DATABASE
        self.connect_timeout = int(getattr(Config, "MYSQL_CONNECT_TIMEOUT", 5))
        self.last_error = None

    def _connect(self, database: bool = True):
        """Buka koneksi MySQL; `database=False` untuk operasi server-level."""
        params = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "connection_timeout": self.connect_timeout,
            "charset": "utf8mb4",
            "use_unicode": True,
        }
        if database:
            params["database"] = self.database
        return mysql.connector.connect(**params)

    def get_connection(self):
        return self._connect(database=True)

    def health(self) -> dict:
        """Cek koneksi database tanpa mengubah data."""
        try:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
            finally:
                conn.close()
            self.last_error = None
            return {
                "status": "up",
                "database": self.database,
                "host": self.host,
                "port": self.port,
            }
        except MySQLError as exc:
            self.last_error = str(exc)
            return {
                "status": "down",
                "database": self.database,
                "host": self.host,
                "port": self.port,
                "error": str(exc),
            }

    def init_db(self) -> bool:
        """Buat database dan table jika belum ada. Return True bila sukses."""
        if not _IDENTIFIER_RE.fullmatch(self.database or ""):
            self.last_error = f"Nama database tidak valid: {self.database!r}"
            log.error(self.last_error)
            return False

        try:
            conn = self._connect(database=False)
            try:
                cursor = conn.cursor()
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                               f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                conn.commit()
                cursor.close()
            finally:
                conn.close()

            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS search_results (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        source VARCHAR(50) NOT NULL,
                        doc_type VARCHAR(20) DEFAULT 'journal',
                        title TEXT NOT NULL,
                        authors JSON DEFAULT NULL,
                        year VARCHAR(10) DEFAULT NULL,
                        abstract TEXT DEFAULT NULL,
                        doi VARCHAR(255) DEFAULT NULL,
                        isbn VARCHAR(50) DEFAULT NULL,
                        url TEXT DEFAULT NULL,
                        download_url TEXT DEFAULT NULL,
                        pdf_url TEXT DEFAULT NULL,
                        language VARCHAR(10) DEFAULT NULL,
                        subjects JSON DEFAULT NULL,
                        publisher VARCHAR(255) DEFAULT NULL,
                        identifier VARCHAR(255) DEFAULT NULL,
                        thumbnail TEXT DEFAULT NULL,
                        classification VARCHAR(100) DEFAULT NULL,
                        search_query VARCHAR(500) DEFAULT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_source (source),
                        INDEX idx_title_source (title(255), source(50)),
                        INDEX idx_doi (doi(100)),
                        INDEX idx_isbn (isbn),
                        INDEX idx_classification (classification)
                    )
                """)
                conn.commit()
                cursor.close()
            finally:
                conn.close()

            self.last_error = None
            log.info("Database and table initialized successfully")
            return True
        except MySQLError as exc:
            self.last_error = str(exc)
            log.error(f"Database init failed: {exc}")
            return False

    @staticmethod
    def _author_texts(authors):
        """Ubah authors (string/list/dict) menjadi list teks lowercase."""
        if not authors:
            return []
        if isinstance(authors, str):
            authors = [authors]
        elif isinstance(authors, dict):
            authors = [authors]
        elif not isinstance(authors, (list, tuple, set)):
            authors = [authors]

        texts = []
        for author in authors:
            if isinstance(author, dict):
                author = author.get("name") or author.get("term") or ""
            text = str(author).strip().lower()
            if text:
                texts.append(text)
        return texts

    def _normalize_authors(self, authors):
        """Normalisasi authors ke string JSON terurut lowercase."""
        return json.dumps(sorted(self._author_texts(authors)))

    @staticmethod
    def _normalize_doi(doi):
        """Normalisasi DOI: hapus URL prefix https://doi.org/ atau doi:, lowercase, strip."""
        if not doi:
            return None
        d = str(doi).strip().lower()
        d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
        d = re.sub(r"^doi:\s*", "", d)
        return d.strip() if d.strip() else None

    @staticmethod
    def _extract_isbn(doc):
        """Ekstrak dan bersihkan ISBN dari doc (bisa dari field 'isbn' atau 'identifier')."""
        raw = doc.get("isbn")
        if not raw and doc.get("doc_type") == "book":
            ident = str(doc.get("identifier") or "").strip()
            cleaned = re.sub(r"[^0-9Xx]", "", ident)
            if len(cleaned) == 13 and (cleaned.startswith("978") or cleaned.startswith("979")):
                raw = cleaned
            elif len(cleaned) == 10:
                raw = cleaned
        elif raw:
            cleaned = re.sub(r"[^0-9Xx]", "", str(raw))
            if len(cleaned) in (10, 13):
                raw = cleaned
            else:
                raw = None
        else:
            return None

        return str(raw).upper() if raw else None

    @staticmethod
    def _safe_val(value, max_len=None):
        """Konversi value agar aman untuk kolom non-JSON MySQL."""
        if value is None:
            return None
        if isinstance(value, list):
            if not value:
                return None
            joined = "; ".join(str(v) for v in value if v is not None)
            return joined if joined else None
        if isinstance(value, (int, float)):
            return str(value)
        val = str(value)
        if max_len and len(val) > max_len:
            val = val[:max_len]
        return val

    def save_search_results(self, docs, search_query):
        """Simpan hasil pencarian ke database dengan deduplikasi.

        Args:
            docs: list of dict (dari make_document())
            search_query: string query pencarian

        Return:
            tuple (saved, skipped). Saat koneksi/query gagal, return (0, 0)
            dan error dicatat (graceful degradation).
        """
        if not docs:
            return 0, 0

        conn = None
        cursor = None
        saved = 0
        skipped = 0

        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            for doc in docs:
                title = (doc.get("title") or "").strip()
                source = (doc.get("source") or "").strip()
                if not title or not source:
                    continue

                norm_title = title.lower()
                norm_source = source.lower()
                norm_authors = self._normalize_authors(doc.get("authors"))
                norm_doi = self._normalize_doi(doc.get("doi"))
                norm_isbn = self._extract_isbn(doc)

                is_duplicate = False

                # 1. Cek duplikasi berdasarkan DOI (lintas sumber)
                if norm_doi:
                    cursor.execute("""
                        SELECT id FROM search_results
                        WHERE LOWER(doi) = %s 
                           OR LOWER(doi) = %s 
                           OR LOWER(doi) = %s
                        LIMIT 1
                    """, (norm_doi, f"https://doi.org/{norm_doi}", f"doi:{norm_doi}"))
                    if cursor.fetchone():
                        is_duplicate = True

                # 2. Cek duplikasi berdasarkan ISBN (lintas sumber)
                if not is_duplicate and norm_isbn:
                    cursor.execute("""
                        SELECT id FROM search_results
                        WHERE isbn = %s 
                           OR REPLACE(REPLACE(identifier, '-', ''), ' ', '') = %s
                        LIMIT 1
                    """, (norm_isbn, norm_isbn))
                    if cursor.fetchone():
                        is_duplicate = True

                # 3. Fallback duplikasi: title + source + authors
                if not is_duplicate:
                    cursor.execute("""
                        SELECT id, authors FROM search_results
                        WHERE LOWER(title) = %s AND LOWER(source) = %s
                    """, (norm_title, norm_source))

                    for row in cursor.fetchall():
                        db_authors = row["authors"]
                        if db_authors is None:
                            db_norm = "[]"
                        else:
                            try:
                                parsed = json.loads(db_authors)
                                db_norm = json.dumps(sorted(self._author_texts(parsed)))
                            except (json.JSONDecodeError, TypeError):
                                db_norm = str(db_authors).strip().lower()

                        if norm_authors == db_norm:
                            is_duplicate = True
                            break

                if is_duplicate:
                    skipped += 1
                    continue

                # INSERT dokumen baru — konversi JSON ke string untuk mysql-connector
                params = (
                    self._safe_val(doc.get("source")),
                    self._safe_val(doc.get("doc_type", "journal")),
                    self._safe_val(doc.get("title")),
                    json.dumps(doc.get("authors", [])),
                    self._safe_val(doc.get("year")),
                    self._safe_val(doc.get("abstract")),
                    self._safe_val(doc.get("doi")),
                    norm_isbn or self._safe_val(doc.get("isbn")),
                    self._safe_val(doc.get("url")),
                    self._safe_val(doc.get("download_url")),
                    self._safe_val(doc.get("pdf_url")),
                    self._safe_val(doc.get("language")),
                    json.dumps(doc.get("subjects", [])),
                    self._safe_val(doc.get("publisher")),
                    self._safe_val(doc.get("identifier")),
                    self._safe_val(doc.get("thumbnail")),
                    self._safe_val(doc.get("classification")),
                    self._safe_val(search_query),
                )
                cursor.execute("""
                    INSERT INTO search_results (
                        source, doc_type, title, authors, year, abstract,
                        doi, isbn, url, download_url, pdf_url, language,
                        subjects, publisher, identifier, thumbnail,
                        classification, search_query
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s
                    )
                """, params)

                saved += 1

            conn.commit()

            if saved > 0 or skipped > 0:
                log.info(f"DB save: {saved} baru, {skipped} duplikat dari {len(docs)} dokumen")

            return saved, skipped

        except MySQLError as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except MySQLError:
                    pass
            log.error(f"Database save failed (graceful degradation): {exc}")
            return 0, 0
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except MySQLError:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except MySQLError:
                    pass

    def get_documents(self, page=1, page_size=10, doc_type=None, classification=None, q=None, source=None):
        """Ambil dokumen dari tabel search_results dengan filter dan pagination."""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            where_clauses = []
            params = []

            if doc_type and doc_type != "all":
                where_clauses.append("doc_type = %s")
                params.append(doc_type)

            if classification and classification != "all":
                where_clauses.append("classification = %s")
                params.append(classification)

            if source and source != "all":
                where_clauses.append("source = %s")
                params.append(source)

            if q:
                search_term = f"%{q.strip()}%"
                where_clauses.append("(title LIKE %s OR abstract LIKE %s OR doi LIKE %s OR isbn LIKE %s OR identifier LIKE %s OR authors LIKE %s)")
                params.extend([search_term] * 6)

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            # Hitung total
            count_query = f"SELECT COUNT(*) as total FROM search_results {where_sql}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()["total"]

            # Query data
            offset = max(0, (page - 1) * page_size)
            data_query = f"""
                SELECT id, source, doc_type, title, authors, year, abstract,
                       doi, isbn, url, download_url, pdf_url, language,
                       subjects, publisher, identifier, thumbnail,
                       classification, search_query, created_at
                FROM search_results
                {where_sql}
                ORDER BY id DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(data_query, params + [page_size, offset])
            rows = cursor.fetchall()

            for row in rows:
                if row.get("authors"):
                    try:
                        row["authors"] = json.loads(row["authors"])
                    except Exception:
                        pass
                if row.get("subjects"):
                    try:
                        row["subjects"] = json.loads(row["subjects"])
                    except Exception:
                        pass
                if row.get("created_at"):
                    row["created_at"] = str(row["created_at"])

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total > 0 else 1,
                "documents": rows
            }
        except MySQLError as exc:
            log.error(f"get_documents failed: {exc}")
            return {"total": 0, "page": page, "page_size": page_size, "total_pages": 1, "documents": [], "error": str(exc)}
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except MySQLError:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except MySQLError:
                    pass

    def get_stats(self):
        """Ambil ringkasan statistik koleksi buku & jurnal di database."""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT COUNT(*) as total FROM search_results")
            total = cursor.fetchone()["total"]

            cursor.execute("""
                SELECT doc_type, COUNT(*) as count 
                FROM search_results 
                GROUP BY doc_type
            """)
            by_type = {row["doc_type"]: row["count"] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT classification, COUNT(*) as count 
                FROM search_results 
                WHERE classification IS NOT NULL 
                GROUP BY classification 
                ORDER BY count DESC
            """)
            by_class = {row["classification"]: row["count"] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT source, COUNT(*) as count 
                FROM search_results 
                GROUP BY source 
                ORDER BY count DESC
            """)
            by_source = {row["source"]: row["count"] for row in cursor.fetchall()}

            return {
                "total": total,
                "by_type": by_type,
                "by_classification": by_class,
                "by_source": by_source,
            }
        except MySQLError as exc:
            log.error(f"get_stats failed: {exc}")
            return {"total": 0, "by_type": {}, "by_classification": {}, "by_source": {}, "error": str(exc)}
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except MySQLError:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except MySQLError:
                    pass

    def delete_document(self, doc_id: int) -> bool:
        """Hapus satu dokumen dari database berdasarkan ID."""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM search_results WHERE id = %s", (doc_id,))
            conn.commit()
            return cursor.rowcount > 0
        except MySQLError as exc:
            log.error(f"delete_document failed: {exc}")
            return False
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except MySQLError:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except MySQLError:
                    pass


db_service = DatabaseService()
