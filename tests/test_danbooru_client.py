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
        self.assertEqual([t["name"] for t in tags], ["miku"])
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


class TestTagLimitAndBlacklist(unittest.TestCase):
    """Sem login o Danbooru aceita 2 tags por busca: a blacklist é filtrada
    no app e o 422 de limite vira uma mensagem que explica o que fazer."""

    def test_parse_tag_list_normalizes(self):
        from src.core.danbooru import parse_tag_list
        self.assertEqual(parse_tag_list("  Gore -blood gore "), ["gore", "blood"])
        self.assertEqual(parse_tag_list(""), [])
        self.assertEqual(parse_tag_list(None), [])

    def test_filter_blacklisted_removes_posts_with_any_tag(self):
        from src.core.danbooru import filter_blacklisted
        posts = [
            {"id": 1, "tag_string": "hatsune_miku solo"},
            {"id": 2, "tag_string": "hatsune_miku gore"},
            {"id": 3, "tag_string": "Blood hatsune_miku"},
            {"id": 4},
        ]
        kept = filter_blacklisted(posts, "gore blood")
        self.assertEqual([p["id"] for p in kept], [1, 4])
        self.assertEqual(filter_blacklisted(posts, ""), posts)
        self.assertEqual([p["id"] for p in filter_blacklisted(posts, ["gore"])], [1, 3, 4])

    def test_tag_limit_422_has_actionable_message(self):
        client = DanbooruClient()
        response = FakeResponse(
            status_code=422,
            payload={
                "success": False,
                "error": "PostQuery::TagLimitError",
                "message": "You cannot search for more than 2 tags at a time.",
            },
        )
        with patch.object(client.session, "get", return_value=response):
            with self.assertRaises(RuntimeError) as ctx:
                client.search_posts("hatsune_miku solo order:score")
        message = str(ctx.exception)
        self.assertIn("limite de tags", message)
        self.assertIn("Mais recentes", message)
        client.close()

    def test_other_422_keeps_generic_message(self):
        client = DanbooruClient()
        response = FakeResponse(status_code=422, payload={"error": "Outra coisa"})
        with patch.object(client.session, "get", return_value=response):
            with self.assertRaises(RuntimeError) as ctx:
                client.search_posts("x")
        self.assertIn("422", str(ctx.exception))
        client.close()


class TestImportSource(unittest.TestCase):
    """Importar usa a versão large quando ela tem resolução suficiente."""

    MIN = (450, 700)

    def _post(self, w, h, ext="png", large="https://cdn/sample/x.jpg"):
        return {
            "image_width": w, "image_height": h, "file_ext": ext,
            "file_url": f"https://cdn/original/x.{ext}", "large_file_url": large,
        }

    def test_tall_image_uses_large_with_its_own_extension(self):
        from src.core.danbooru import import_source
        url, ext = import_source(self._post(3497, 5000), self.MIN)
        self.assertEqual((url, ext), ("https://cdn/sample/x.jpg", "jpg"))

    def test_wide_image_falls_back_to_original(self):
        from src.core.danbooru import import_source
        # 4490x2480 -> large 850x469: menos de 700 de altura
        url, ext = import_source(self._post(4490, 2480, ext="jpg"), self.MIN)
        self.assertEqual((url, ext), ("https://cdn/original/x.jpg", "jpg"))

    def test_small_image_uses_original(self):
        from src.core.danbooru import import_source
        post = self._post(683, 685, ext="jpg")
        post["large_file_url"] = post["file_url"]
        self.assertEqual(import_source(post, self.MIN)[0], post["file_url"])

    def test_missing_dimensions_or_urls(self):
        from src.core.danbooru import import_source
        self.assertEqual(import_source({"file_url": "https://cdn/a.png"}, self.MIN), ("https://cdn/a.png", "png"))
        self.assertEqual(import_source({}, self.MIN), (None, None))


class TestSearchRequestsOnlyUsedFields(unittest.TestCase):
    def test_search_sends_only_param_with_fields_the_app_reads(self):
        from src.core.danbooru import POST_FIELDS
        client = DanbooruClient()
        with patch.object(client.session, "get", return_value=FakeResponse(payload=[])) as get:
            client.search_posts("hatsune_miku", limit=40, page=2)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["only"], POST_FIELDS)
        self.assertEqual(params["limit"], 40)
        for field in ("id", "rating", "tag_string", "file_url", "large_file_url", "preview_file_url"):
            self.assertIn(field, POST_FIELDS.split(","))
        client.close()
