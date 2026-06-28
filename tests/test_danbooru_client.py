import unittest
from unittest.mock import patch

import requests

from src.core.danbooru import DanbooruClient


class DummyConfig:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.content = content
        self.headers = headers or {"Content-Type": "image/png"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"http {self.status_code}", response=self
            )

    def json(self):
        return self._payload


class TestDanbooruClient(unittest.TestCase):
    def test_configures_http_adapter_with_pool_and_retry(self):
        config = DummyConfig(
            {
                "danbooru_pool_connections": 11,
                "danbooru_pool_maxsize": 22,
                "danbooru_retry_total": 3,
                "danbooru_retry_backoff": 0.4,
            }
        )
        client = DanbooruClient(config=config)

        adapter = client.session.get_adapter("https://")
        self.assertEqual(adapter._pool_connections, 11)
        self.assertEqual(adapter._pool_maxsize, 22)
        self.assertEqual(adapter.max_retries.total, 3)
        self.assertAlmostEqual(adapter.max_retries.backoff_factor, 0.4)
        self.assertIn(429, adapter.max_retries.status_forcelist)
        self.assertIn("GET", adapter.max_retries.allowed_methods)
        client.close()

    def test_uses_configured_timeouts_per_operation(self):
        config = DummyConfig(
            {
                "danbooru_timeout_search_s": 12,
                "danbooru_timeout_tags_s": 7,
                "danbooru_timeout_download_s": 18,
            }
        )
        client = DanbooruClient(config=config)
        calls = []

        def fake_get(url, *args, **kwargs):
            calls.append({"url": url, "timeout": kwargs.get("timeout")})
            if url.endswith("/posts.json"):
                return FakeResponse(status_code=200, payload=[{"id": 1}])
            if url.endswith("/tags.json"):
                return FakeResponse(status_code=200, payload=[{"name": "miku"}])
            return FakeResponse(status_code=200, content=b"image-bytes")

        with patch.object(client.session, "get", side_effect=fake_get):
            posts = client.search_posts("hatsune_miku")
            tags = client.fetch_tags("mi")
            image = client.download_image("https://example.com/test.png")

        self.assertEqual(posts, [{"id": 1}])
        self.assertEqual(tags, ["miku"])
        self.assertEqual(image, b"image-bytes")
        self.assertEqual(calls[0]["timeout"], 12)
        self.assertEqual(calls[1]["timeout"], 7)
        self.assertEqual(calls[2]["timeout"], 18)
        client.close()

    def test_close_calls_session_close(self):
        client = DanbooruClient()
        with patch.object(client.session, "close") as close_mock:
            client.close()
            close_mock.assert_called_once()

    def test_download_uses_pixiv_referer_header(self):
        client = DanbooruClient()
        calls = []

        def fake_get(url, *args, **kwargs):
            calls.append(kwargs.get("headers") or {})
            return FakeResponse(status_code=200, content=b"ok", headers={"Content-Type": "image/jpeg"})

        with patch.object(client.session, "get", side_effect=fake_get):
            data = client.download_image("https://i.pximg.net/img-original/abc.jpg")

        self.assertEqual(data, b"ok")
        self.assertEqual(calls[0].get("Referer"), "https://www.pixiv.net/")
        client.close()

    def test_download_rejects_non_image_content_type(self):
        client = DanbooruClient()

        with patch.object(
            client.session,
            "get",
            return_value=FakeResponse(status_code=200, content=b"<html></html>", headers={"Content-Type": "text/html"}),
        ):
            data = client.download_image("https://example.com/page")

        self.assertIsNone(data)
        client.close()

    def test_search_posts_raises_permission_error_on_403(self):
        client = DanbooruClient()
        with patch.object(
            client.session,
            "get",
            return_value=FakeResponse(status_code=403),
        ):
            with self.assertRaises(PermissionError) as ctx:
                client.search_posts("restricted_tag")
        self.assertIn("403", str(ctx.exception))
        client.close()

    def test_search_posts_raises_lookup_error_on_404(self):
        client = DanbooruClient()
        with patch.object(
            client.session,
            "get",
            return_value=FakeResponse(status_code=404),
        ):
            with self.assertRaises(LookupError) as ctx:
                client.search_posts("missing_tag")
        self.assertIn("404", str(ctx.exception))
        client.close()

    def test_search_posts_raises_runtime_error_on_429(self):
        client = DanbooruClient()
        with patch.object(
            client.session,
            "get",
            return_value=FakeResponse(status_code=429),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                client.search_posts("popular_tag")
        self.assertIn("429", str(ctx.exception))
        client.close()
