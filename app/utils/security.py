"""
app/utils/security.py
Utilitas keamanan: validasi URL publik (anti-SSRF), validasi filename,
dan confinement path download.
"""
import ipaddress
import os
import socket
from urllib.parse import quote, urljoin, urlparse

import requests

from app.utils.logging import get_logger

log = get_logger("security")

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home",
    ".lan",
    ".corp",
    ".intranet",
)
MAX_REDIRECTS = 5
MAX_URL_LENGTH = 8192
MAX_FILENAME_BYTES = 255
WINDOWS_INVALID_FILENAME_CHARS = set('<>:"|?*')

# Rentang IPv6 yang membawa/menyamar sebagai IPv4. Ini bisa dipakai untuk
# melewati pengecekan IPv4 private bila tidak diblokir eksplisit.
IPV4_COMPATIBLE_NETWORK = ipaddress.ip_network("::/96")
IPV4_TRANSLATED_NETWORK = ipaddress.ip_network("::ffff:0:0/96")
NAT64_WELL_KNOWN_NETWORK = ipaddress.ip_network("64:ff9b::/96")
NAT64_LOCAL_NETWORK = ipaddress.ip_network("64:ff9b:1::/48")


class UnsafeURLError(ValueError):
    """URL ditolak oleh guard SSRF."""


def _parse_url(url: str):
    if not isinstance(url, str):
        raise UnsafeURLError("URL harus berupa string")

    raw = url.strip()
    if not raw or len(raw) > MAX_URL_LENGTH:
        raise UnsafeURLError("URL kosong atau terlalu panjang")
    if "\\" in raw:
        raise UnsafeURLError("URL tidak boleh mengandung backslash")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise UnsafeURLError("URL mengandung karakter kontrol")

    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise UnsafeURLError(f"URL tidak valid: {exc}") from exc

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError("Hanya URL http/https yang diizinkan")
    if not parsed.hostname:
        raise UnsafeURLError("URL tidak memiliki host")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URL dengan credential tidak diizinkan")

    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURLError("Port URL tidak valid") from exc
    if port is not None and not (1 <= port <= 65535):
        raise UnsafeURLError("Port URL tidak valid")
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80

    host = parsed.hostname.rstrip(".").lower()
    if not host:
        raise UnsafeURLError("Host URL tidak valid")

    return parsed, host, port


def _resolve_addresses(host: str, port: int) -> list:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Host tidak dapat di-resolve: {host}") from exc

    addresses = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addresses.append(sockaddr[0])
    if not addresses:
        raise UnsafeURLError(f"Host tidak memiliki alamat IP: {host}")
    return addresses


def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    if isinstance(ip, ipaddress.IPv6Address):
        # IPv4-mapped IPv6 (::ffff:127.0.0.1) harus dicek sebagai IPv4.
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        else:
            # Blokir IPv4-compatible/translated dan NAT64 yang menyembunyikan IPv4.
            if ip in IPV4_COMPATIBLE_NETWORK or ip in IPV4_TRANSLATED_NETWORK:
                return False
            if ip in NAT64_WELL_KNOWN_NETWORK or ip in NAT64_LOCAL_NETWORK:
                return False
            if ip.sixtofour is not None or ip.teredo is not None:
                return False

    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return False
    if ip.is_reserved or ip.is_unspecified:
        return False
    if getattr(ip, "is_site_local", False):
        return False
    return ip.is_global


def validate_public_url(url: str) -> str:
    """
    Validasi bahwa URL hanya menuju host publik.

    Menolak scheme selain http/https, credential di URL, host lokal/internal,
    serta semua alamat private/loopback/link-local/reserved/multicast.
    Return URL yang sudah di-strip, atau raise UnsafeURLError.
    """
    _parsed, host, port = _parse_url(url)

    if host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise UnsafeURLError("Host lokal/internal tidak diizinkan")

    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False

    # Hostname single-label hampir selalu host internal (mis. "intranet").
    if not is_ip_literal and "." not in host:
        raise UnsafeURLError("Hostname tanpa domain tidak diizinkan")

    for address in _resolve_addresses(host, port):
        if not _is_public_ip(address):
            raise UnsafeURLError(f"Host menuju alamat non-publik: {address}")

    return url.strip()


def safe_request(
    method: str,
    url: str,
    *,
    headers: dict = None,
    timeout: int = 30,
    stream: bool = False,
    max_redirects: int = MAX_REDIRECTS,
    **kwargs,
) -> requests.Response:
    """
    requests.request() dengan validasi SSRF di setiap hop redirect.

    Redirect tidak diikuti otomatis oleh requests; Location divalidasi dulu
    sebelum request berikutnya. Response final tetap terbuka untuk caller.
    """
    current = validate_public_url(url)

    for _ in range(max_redirects + 1):
        response = requests.request(
            method,
            current,
            headers=headers,
            timeout=timeout,
            stream=stream,
            allow_redirects=False,
            **kwargs,
        )

        location = response.headers.get("Location")
        if not response.is_redirect or not location:
            return response

        response.close()
        current = urljoin(current, location)
        validate_public_url(current)

    raise requests.TooManyRedirects(f"Terlalu banyak redirect (>{max_redirects})")


def validate_filename(filename, default: str = None) -> str:
    """
    Validasi filename custom agar tidak bisa keluar dari folder download.

    Menolak path separator, karakter kontrol, karakter ilegal Windows,
    nama kosong/./.., dan filename yang terlalu panjang.
    """
    if filename is None:
        if default is None:
            raise ValueError("filename wajib diisi")
        return default
    if not isinstance(filename, str):
        raise ValueError("filename harus berupa string")

    name = filename.strip()
    if not name:
        raise ValueError("filename tidak boleh kosong")
    if name in (".", ".."):
        raise ValueError("filename tidak valid")
    if "/" in name or "\\" in name:
        raise ValueError("filename tidak boleh mengandung path")
    if any(char in WINDOWS_INVALID_FILENAME_CHARS for char in name):
        raise ValueError("filename mengandung karakter yang tidak diizinkan")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("filename mengandung karakter kontrol")
    if len(name.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise ValueError("filename terlalu panjang")

    return name


def resolve_download_path(base_dir: str, filename: str) -> str:
    """
    Gabungkan base_dir + filename dan pastikan hasilnya tetap di dalam base_dir.

    Ini lapisan pertahanan kedua setelah validate_filename(), termasuk untuk
    symlink yang sudah ada di folder download.
    """
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, filename))

    try:
        common = os.path.commonpath([base, target])
    except ValueError as exc:
        raise ValueError("Path berada di luar folder download") from exc

    if common != base or target == base:
        raise ValueError("Path berada di luar folder download")
    return target


def content_disposition(filename: str) -> str:
    """Header Content-Disposition aman untuk filename Unicode."""
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
