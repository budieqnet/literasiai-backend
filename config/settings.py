"""
config/settings.py
Konfigurasi terpusat LiterasiAI
"""
import os
import sys
from dotenv import load_dotenv


def _load_env():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
        env_path = os.path.join(base, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
            return
    load_dotenv()


_load_env()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    # Default aman: debug hanya aktif bila FLASK_DEBUG=1 secara eksplisit.
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

    # Cache
    CACHE_TTL = int(os.getenv("CACHE_TTL", 600))

    # API Keys (opsional)
    CORE_API_KEY = os.getenv("CORE_API_KEY", "")

    # Auth endpoint admin (wajib untuk /api/admin/download-methods)
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()

    # NVIDIA Nemotron — klasifikasi dokumen
    NVIDIA_API_KEY = (
        os.getenv("NVIDIA_API_KEY")
        or os.getenv("NVIDIA_API_KEY_3", os.getenv("NVIDIA_API_KEY_2", os.getenv("NVIDIA_API_KEY_1", "")))
    )
    NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    NVIDIA_TIMEOUT = int(os.getenv("NVIDIA_TIMEOUT", "60"))
    NVIDIA_MAX_RETRIES = int(os.getenv("NVIDIA_MAX_RETRIES", "2"))
    NVIDIA_MAX_TOKENS = int(os.getenv("NVIDIA_MAX_TOKENS", "512"))
    NVIDIA_TEMPERATURE = float(os.getenv("NVIDIA_TEMPERATURE", "0.2"))
    NVIDIA_TOP_P = float(os.getenv("NVIDIA_TOP_P", "0.9"))

    # Cache klasifikasi — mengurangi panggilan API untuk dokumen yang sama.
    NVIDIA_CACHE_ENABLED = os.getenv("NVIDIA_CACHE_ENABLED", "1") == "1"
    NVIDIA_CACHE_TTL = int(os.getenv("NVIDIA_CACHE_TTL", "86400"))
    NVIDIA_CACHE_SIZE = int(os.getenv("NVIDIA_CACHE_SIZE", "2048"))

    # Batas hasil per sumber saat pencarian
    DEFAULT_PAGE_SIZE = 10

    # User-Agent sopan untuk HTTP request
    USER_AGENT = (
        "LiterasiAI/1.0 (academic research tool; "
        "contact: admin@literasiai.id)"
    )

    # Timeout request ke sumber eksternal (detik)
    REQUEST_TIMEOUT = 15

    # MySQL
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "budi")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Budi@123")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "literasiai")
    MYSQL_CONNECT_TIMEOUT = int(os.getenv("MYSQL_CONNECT_TIMEOUT", "5"))

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
