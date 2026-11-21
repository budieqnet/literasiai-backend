"""
tests/test_classifier.py
Unit test untuk klasifikasi NVIDIA — tanpa memanggil API asli.

Jalankan:
    python tests/test_classifier.py
"""
import json
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config  # noqa: E402
from app.services.nvidia import (  # noqa: E402
    CATEGORIES,
    NvidiaClassifyError,
    _cache_key,
    _get_api_keys,
    _parse_classification,
    cache_info,
    classify_document,
    clear_cache,
)
from app.routes.classify import _classify_document  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("respons bukan JSON")
        return self._payload


def success_payload(content):
    return {"choices": [{"message": {"content": content}}]}


def classification_json(**overrides):
    data = {
        "category": "Computer Vision",
        "confidence": 0.95,
        "keywords": ["object detection", "YOLO"],
        "summary": "Deteksi objek secara real-time.",
    }
    data.update(overrides)
    return json.dumps(data)


class TestParser(unittest.TestCase):
    def test_plain_json(self):
        result = _parse_classification(classification_json())
        self.assertEqual(result["category"], "Computer Vision")
        self.assertEqual(result["confidence"], 0.95)
        self.assertEqual(result["provider"], "nvidia")

    def test_fenced_json(self):
        content = "```json\n" + classification_json() + "\n```"
        result = _parse_classification(content)
        self.assertEqual(result["category"], "Computer Vision")

    def test_json_with_prefix_suffix(self):
        content = "Berikut hasilnya:\n" + classification_json() + "\nSemoga membantu."
        result = _parse_classification(content)
        self.assertEqual(result["category"], "Computer Vision")

    def test_invalid_category_becomes_other(self):
        result = _parse_classification(classification_json(category="Astrology"))
        self.assertEqual(result["category"], "Other")

    def test_confidence_clamped(self):
        result = _parse_classification(classification_json(confidence=7))
        self.assertEqual(result["confidence"], 1.0)

    def test_keywords_limited_and_deduplicated(self):
        result = _parse_classification(classification_json(
            keywords=["AI", "ai", "ML", "NLP", "CV", "IoT", "Law", "Arts", "History", "Physics"]
        ))
        self.assertLessEqual(len(result["keywords"]), 8)
        self.assertEqual(result["keywords"][0], "AI")
        self.assertNotIn("ai", result["keywords"])

    def test_empty_content_raises(self):
        with self.assertRaises(NvidiaClassifyError):
            _parse_classification("")


class TestClassifyDocument(unittest.TestCase):
    def setUp(self):
        # Cache bersifat global per proses; bersihkan agar call-count test stabil.
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_success_uses_expected_payload(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post:
            post.return_value = FakeResponse(200, success_payload(classification_json()))

            result = classify_document(
                title="Real-Time Object Detection for Autonomous Vehicles",
                abstract="YOLOv8 is used for object detection.",
                authors=["A. Researcher"],
                year="2026",
                source="arXiv",
                subjects=["computer vision"],
            )

        self.assertEqual(result["provider"], "nvidia")
        self.assertEqual(result["category"], "Computer Vision")

        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["stream"])
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(
            payload["response_format"]["json_schema"]["schema"]["properties"]["category"]["enum"],
            CATEGORIES,
        )
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")

    def test_retry_on_server_error(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post, \
             patch("app.services.nvidia.time.sleep") as sleep:
            post.side_effect = [
                FakeResponse(500, text="server error"),
                FakeResponse(200, success_payload(classification_json())),
            ]

            result = classify_document("A title")

        self.assertEqual(result["provider"], "nvidia")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once()

    def test_key_rotation_on_rate_limit(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["key-1", "key-2"]), \
             patch("app.services.nvidia.requests.post") as post:
            post.side_effect = [
                FakeResponse(429, text="rate limit"),
                FakeResponse(200, success_payload(classification_json())),
            ]

            result = classify_document("A title")

        self.assertEqual(result["provider"], "nvidia")
        self.assertEqual(post.call_count, 2)
        first_auth = post.call_args_list[0].kwargs["headers"]["Authorization"]
        second_auth = post.call_args_list[1].kwargs["headers"]["Authorization"]
        self.assertEqual(first_auth, "Bearer key-1")
        self.assertEqual(second_auth, "Bearer key-2")

    def test_all_attempts_fail_raises(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post, \
             patch("app.services.nvidia.time.sleep"):
            post.return_value = FakeResponse(500, text="server error")

            with self.assertRaises(NvidiaClassifyError):
                classify_document("A title")

        self.assertEqual(post.call_count, 3)

    def test_missing_key_raises(self):
        with patch("app.services.nvidia._get_api_keys", return_value=[]):
            with self.assertRaises(NvidiaClassifyError):
                classify_document("A title")

    def test_http_400_is_not_retried(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post:
            post.return_value = FakeResponse(400, text="schema tidak valid")

            with self.assertRaises(NvidiaClassifyError):
                classify_document("A title")

        self.assertEqual(post.call_count, 1)

    def test_error_inside_http_200_is_retried(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post, \
             patch("app.services.nvidia.time.sleep"):
            post.side_effect = [
                FakeResponse(200, {"error": {"code": 503, "message": "overloaded"}}),
                FakeResponse(200, success_payload(classification_json())),
            ]

            result = classify_document("A title")

        self.assertEqual(result["provider"], "nvidia")
        self.assertEqual(post.call_count, 2)


class TestCache(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def tearDown(self):
        clear_cache()

    def test_identical_document_uses_cache(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post:
            post.return_value = FakeResponse(200, success_payload(classification_json()))

            first = classify_document("Cached title", abstract="Same abstract")
            second = classify_document("Cached title", abstract="Same abstract")

        self.assertEqual(post.call_count, 1)
        self.assertEqual(first["category"], second["category"])
        self.assertEqual(cache_info()["size"], 1)

    def test_different_document_bypasses_cache(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post:
            post.return_value = FakeResponse(200, success_payload(classification_json()))

            classify_document("Title A")
            classify_document("Title B")

        self.assertEqual(post.call_count, 2)
        self.assertEqual(cache_info()["size"], 2)

    def test_cache_disabled_calls_api_every_time(self):
        with patch.object(Config, "NVIDIA_CACHE_ENABLED", False), \
             patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post:
            post.return_value = FakeResponse(200, success_payload(classification_json()))

            classify_document("No cache title")
            classify_document("No cache title")

        self.assertEqual(post.call_count, 2)
        self.assertEqual(cache_info()["size"], 0)

    def test_failed_request_is_not_cached(self):
        with patch("app.services.nvidia._get_api_keys", return_value=["test-key"]), \
             patch("app.services.nvidia.requests.post") as post, \
             patch("app.services.nvidia.time.sleep"):
            post.return_value = FakeResponse(500, text="server error")

            with self.assertRaises(NvidiaClassifyError):
                classify_document("Failing title")

        self.assertEqual(cache_info()["size"], 0)

    def test_cache_key_depends_on_model_and_fields(self):
        base = _cache_key("Title", "Abstract", ["A"], "2026", "arXiv", ["cv"])
        self.assertEqual(base, _cache_key(" Title ", " Abstract ", [" A "], "2026", "arXiv", [" cv "]))
        self.assertNotEqual(base, _cache_key("Title", "Abstract", ["A"], "2026", "arXiv", ["nlp"]))

        with patch.object(Config, "NVIDIA_MODEL", "model/other"):
            self.assertNotEqual(base, _cache_key("Title", "Abstract", ["A"], "2026", "arXiv", ["cv"]))


class TestApiKeys(unittest.TestCase):
    def test_comma_list_and_numbered_keys_dedup(self):
        env = {
            "NVIDIA_API_KEY": "key-a",
            "NVIDIA_API_KEYS": "key-b, key-c,key-a",
            "NVIDIA_API_KEY_1": "key-c",
            "NVIDIA_API_KEY_2": "key-d",
        }
        with patch.dict(os.environ, env, clear=True), \
             patch.object(Config, "NVIDIA_API_KEY", ""):
            self.assertEqual(_get_api_keys(), ["key-a", "key-b", "key-c", "key-d"])

    def test_no_keys_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(Config, "NVIDIA_API_KEY", ""):
            self.assertEqual(_get_api_keys(), [])


class TestFallback(unittest.TestCase):
    @patch(
        "app.routes.classify.classify_with_nvidia",
        side_effect=NvidiaClassifyError("API down"),
    )
    def test_fallback_uses_keywords(self, _mock_classify):
        result = _classify_document(
            title="Detecting Phishing Attacks Using Machine Learning",
            abstract="Phishing URLs are classified using random forests.",
            authors=[],
            year="",
            source="",
            subjects=[],
        )
        self.assertEqual(result["provider"], "fallback")
        self.assertEqual(result["category"], "Cybersecurity")
        self.assertIn("phishing", result["keywords"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
