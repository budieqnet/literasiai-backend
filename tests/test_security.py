"""
tests/test_security.py
Regresi paket keamanan:
- autentikasi endpoint admin
- validasi URL publik / anti-SSRF (termasuk redirect)
- sanitasi filename dan confinement folder download
- debug default off

Jalankan:
    python tests/test_security.py
"""
import os
import socket
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
import requests  # noqa: E402

from config import Config  # noqa: E402
from app.routes import download as download_module  # noqa: E402
from app.routes.admin_download import admin_bp  # noqa: E402
from app.routes.download import download_bp  # noqa: E402
from app.utils import security  # noqa: E402


def _resolver(*addresses):
    """Bikin fake socket.getaddrinfo yang mengembalikan alamat tertentu."""
    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
            for address in addresses
        ]
    return fake_getaddrinfo


class TestAdminAuth(unittest.TestCase):
    def setUp(self):
        self.original_key = Config.ADMIN_API_KEY
        Config.ADMIN_API_KEY = "test-admin-key"
        app = Flask(__name__)
        app.register_blueprint(admin_bp)
        self.client = app.test_client()

    def tearDown(self):
        Config.ADMIN_API_KEY = self.original_key

    def test_tanpa_auth_ditolak(self):
        response = self.client.get("/api/admin/download-methods")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.headers.get("WWW-Authenticate"),
            'Bearer realm="admin"',
        )

    def test_key_salah_ditolak(self):
        response = self.client.get(
            "/api/admin/download-methods",
            headers={"Authorization": "Bearer key-salah"},
        )
        self.assertEqual(response.status_code, 401)

    def test_bearer_key_benar_diterima(self):
        response = self.client.get(
            "/api/admin/download-methods",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "success")

    def test_x_admin_key_benar_diterima(self):
        response = self.client.get(
            "/api/admin/download-methods",
            headers={"X-Admin-Key": "test-admin-key"},
        )
        self.assertEqual(response.status_code, 200)

    def test_fail_closed_bila_key_belum_dikonfigurasi(self):
        Config.ADMIN_API_KEY = ""
        response = self.client.get("/api/admin/download-methods")
        self.assertEqual(response.status_code, 503)

    def test_preflight_options_tidak_diblokir(self):
        response = self.client.options("/api/admin/download-methods")
        self.assertNotEqual(response.status_code, 401)


class TestValidatePublicUrl(unittest.TestCase):
    def test_url_publik_diterima(self):
        with patch(
            "app.utils.security.socket.getaddrinfo",
            side_effect=_resolver("93.184.216.34"),
        ):
            result = security.validate_public_url(" https://example.com/file.pdf ")
        self.assertEqual(result, "https://example.com/file.pdf")

    def test_url_internal_ditolak(self):
        cases = [
            "http://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://100.64.0.1/",
            "http://192.0.2.1/",
            "http://[::1]/",
            "http://0.0.0.0/",
            "http://2130706433/",
        ]
        with patch(
            "app.utils.security.socket.getaddrinfo",
            side_effect=_resolver("127.0.0.1"),
        ):
            for url in cases:
                with self.subTest(url=url):
                    with self.assertRaises(security.UnsafeURLError):
                        security.validate_public_url(url)

    def test_scheme_selain_http_ditolak(self):
        for url in ("file:///etc/passwd", "ftp://example.com/file", "gopher://example.com/"):
            with self.subTest(url=url):
                with self.assertRaises(security.UnsafeURLError):
                    security.validate_public_url(url)

    def test_url_dengan_credential_ditolak(self):
        with self.assertRaises(security.UnsafeURLError):
            security.validate_public_url("http://user:pass@example.com/")

    def test_host_lokal_dan_single_label_ditolak(self):
        for url in (
            "http://localhost/",
            "http://metadata.google.internal/",
            "http://intranet/",
            "http://example.local/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(security.UnsafeURLError):
                    security.validate_public_url(url)

    def test_backslash_dan_port_invalid_ditolak(self):
        for url in (
            "http://example.com\\@127.0.0.1/",
            "http://example.com:99999/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(security.UnsafeURLError):
                    security.validate_public_url(url)

    def test_satu_alamat_privat_dalam_dns_ditolak(self):
        with patch(
            "app.utils.security.socket.getaddrinfo",
            side_effect=_resolver("93.184.216.34", "10.0.0.7"),
        ):
            with self.assertRaises(security.UnsafeURLError):
                security.validate_public_url("https://example.com/")

    def test_ipv4_mapped_ipv6_privat_ditolak(self):
        with patch(
            "app.utils.security.socket.getaddrinfo",
            side_effect=_resolver("::ffff:127.0.0.1"),
        ):
            with self.assertRaises(security.UnsafeURLError):
                security.validate_public_url("https://example.com/")

    def test_ipv6_transition_ke_ipv4_privat_ditolak(self):
        for address in ("::127.0.0.1", "::ffff:0:7f00:1", "64:ff9b::7f00:1"):
            with self.subTest(address=address):
                with patch(
                    "app.utils.security.socket.getaddrinfo",
                    side_effect=_resolver(address),
                ):
                    with self.assertRaises(security.UnsafeURLError):
                        security.validate_public_url("https://example.com/")


class TestSafeRequest(unittest.TestCase):
    def test_redirect_ke_internal_diblokir_sebelum_request_kedua(self):
        redirect = Mock()
        redirect.is_redirect = True
        redirect.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        redirect.close = Mock()

        def fake_getaddrinfo(host, port, **kwargs):
            address = "169.254.169.254" if host == "169.254.169.254" else "93.184.216.34"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

        with patch(
            "app.utils.security.socket.getaddrinfo",
            side_effect=fake_getaddrinfo,
        ), patch(
            "app.utils.security.requests.request",
            return_value=redirect,
        ) as request_mock:
            with self.assertRaises(security.UnsafeURLError):
                security.safe_request("GET", "https://example.com/start")

        self.assertEqual(request_mock.call_count, 1)
        redirect.close.assert_called_once()

    def test_redirect_ke_host_publik_diikuti(self):
        first = Mock()
        first.is_redirect = True
        first.headers = {"Location": "https://cdn.example.org/file.pdf"}
        first.close = Mock()

        second = Mock()
        second.is_redirect = False
        second.headers = {}
        second.close = Mock()

        with patch(
            "app.utils.security.socket.getaddrinfo",
            side_effect=_resolver("93.184.216.34"),
        ), patch(
            "app.utils.security.requests.request",
            side_effect=[first, second],
        ) as request_mock:
            response = security.safe_request("GET", "https://example.com/start")

        self.assertIs(response, second)
        self.assertEqual(request_mock.call_count, 2)
        first.close.assert_called_once()

    def test_redirect_berlebihan_ditolak(self):
        redirect = Mock()
        redirect.is_redirect = True
        redirect.headers = {"Location": "https://example.com/next"}
        redirect.close = Mock()

        with patch(
            "app.utils.security.socket.getaddrinfo",
            side_effect=_resolver("93.184.216.34"),
        ), patch(
            "app.utils.security.requests.request",
            return_value=redirect,
        ):
            with self.assertRaises(requests.TooManyRedirects):
                security.safe_request("GET", "https://example.com/start")


class TestFilenameSecurity(unittest.TestCase):
    def test_filename_normal_diterima(self):
        self.assertEqual(
            security.validate_filename("Laporan Penelitian.pdf"),
            "Laporan Penelitian.pdf",
        )

    def test_path_traversal_dan_filename_berbahaya_ditolak(self):
        cases = [
            "../../etc/passwd",
            "..\\..\\Windows\\system.ini",
            "/etc/passwd",
            "C:\\evil.pdf",
            "C:evil.pdf",
            "..",
            ".",
            "",
            "a\x00b",
            "a" * 256,
        ]
        for filename in cases:
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    security.validate_filename(filename)

    def test_default_dipakai_bila_none(self):
        self.assertEqual(
            security.validate_filename(None, default="document.pdf"),
            "document.pdf",
        )

    def test_resolve_path_tetap_di_dalam_base_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = security.resolve_download_path(tmpdir, "file.pdf")
            self.assertEqual(os.path.dirname(path), os.path.realpath(tmpdir))
            with self.assertRaises(ValueError):
                security.resolve_download_path(tmpdir, "../outside.pdf")


class TestDownloadRouteSecurity(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base_dir = self.tempdir.name
        self.download_dir = os.path.join(self.base_dir, "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

        self.original_download_dir = download_module.DOWNLOAD_DIR
        download_module.DOWNLOAD_DIR = self.download_dir
        self.addCleanup(
            setattr,
            download_module,
            "DOWNLOAD_DIR",
            self.original_download_dir,
        )

        base_patch = patch(
            "app.routes.download._get_base_dir",
            return_value=self.base_dir,
        )
        base_patch.start()
        self.addCleanup(base_patch.stop)

        app = Flask(__name__)
        app.register_blueprint(download_bp)
        self.client = app.test_client()

    def test_post_url_internal_ditolak(self):
        response = self.client.post(
            "/api/download",
            json={"url": "http://127.0.0.1:8080/secret"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tidak diizinkan", response.get_json()["error"])

    def test_post_filename_traversal_ditolak_tanpa_request_keluar(self):
        response = self.client.post(
            "/api/download",
            json={
                "url": "https://example.com/file.pdf",
                "filename": "../../tmp/evil.pdf",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Filename tidak valid", response.get_json()["error"])

    def test_stream_url_internal_ditolak(self):
        response = self.client.get(
            "/api/download/stream",
            query_string={"url": "http://169.254.169.254/latest/meta-data/"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tidak diizinkan", response.get_json()["error"])

    def test_stream_filename_traversal_ditolak(self):
        response = self.client.get(
            "/api/download/stream",
            query_string={
                "url": "https://example.com/file.pdf",
                "filename": "../evil.pdf",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Filename tidak valid", response.get_json()["error"])

    def test_info_url_internal_ditolak(self):
        response = self.client.post(
            "/api/download/info",
            json={"url": "http://10.0.0.1/private"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tidak diizinkan", response.get_json()["error"])

    def test_download_sukses_tidak_membocorkan_path_absolut(self):
        upstream = Mock()
        upstream.headers = {"content-length": "4"}
        upstream.is_redirect = False
        upstream.iter_content.return_value = [b"data"]
        upstream.raise_for_status.return_value = None
        upstream.close.return_value = None

        with patch.object(
            download_module,
            "validate_public_url",
            side_effect=lambda url: url,
        ), patch.object(
            download_module,
            "safe_request",
            return_value=upstream,
        ):
            response = self.client.post(
                "/api/download",
                json={
                    "url": "https://example.com/file.pdf",
                    "filename": "safe.pdf",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["filename"], "safe.pdf")
        self.assertEqual(data["filepath"], os.path.join("downloads", "safe.pdf"))
        self.assertFalse(os.path.isabs(data["filepath"]))
        self.assertTrue(os.path.exists(os.path.join(self.download_dir, "safe.pdf")))

    def test_stream_sukses_mengirim_file(self):
        upstream = Mock()
        upstream.headers = {
            "content-length": "4",
            "content-type": "application/pdf",
        }
        upstream.is_redirect = False
        upstream.iter_content.return_value = [b"%PDF"]
        upstream.raise_for_status.return_value = None
        upstream.close.return_value = None

        with patch.object(
            download_module,
            "validate_public_url",
            side_effect=lambda url: url,
        ), patch.object(
            download_module,
            "safe_request",
            return_value=upstream,
        ):
            response = self.client.get(
                "/api/download/stream",
                query_string={
                    "url": "https://example.com/file.pdf",
                    "filename": "hasil penelitian.pdf",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"%PDF")
        self.assertTrue(
            response.headers["Content-Disposition"].startswith(
                "attachment; filename*=UTF-8''"
            )
        )
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        upstream.close.assert_called_once()


class TestDebugDefault(unittest.TestCase):
    def test_debug_default_off(self):
        self.assertFalse(Config.DEBUG)

    def test_run_py_memakai_config_debug(self):
        run_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "run.py",
        )
        with open(run_path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("debug=Config.DEBUG", source)
        self.assertNotIn("debug=True", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
