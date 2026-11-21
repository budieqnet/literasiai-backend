"""
app/utils/http.py
Helper untuk HTTP request ke sumber eksternal
"""
import requests
from config import Config
from app.utils.logging import get_logger

log = get_logger("http")


def get(url: str, params: dict = None, headers: dict = None, timeout: int = None) -> requests.Response:
    """
    Wrapper requests.get dengan default header dan timeout LiterasiAI.
    Raise requests.RequestException bila gagal.
    """
    default_headers = {
        "User-Agent": Config.USER_AGENT,
        "Accept": "application/json",
    }
    if headers:
        default_headers.update(headers)

    log.debug(f"GET {url}", extra={"url": url, "params": params})
    resp = requests.get(
        url,
        params=params,
        headers=default_headers,
        timeout=timeout or Config.REQUEST_TIMEOUT,
    )
    log.debug(f"Response {resp.status_code} from {url}")
    return resp
