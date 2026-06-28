import tempfile
import unittest
from unittest.mock import patch

import requests

from src.core.uploader import ImgChestUploader


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, headers=None, files=None, data=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "files": files,
                "data": data,
                "timeout": timeout,
            }
        )
        idx = len(self.calls) - 1
        if idx < len(self.responses):
            return self.responses[idx]
        return self.responses[-1]


class RetryFileAwareSession:
    def __init__(self):
        self.calls = 0

    def post(self, url, headers=None, files=None, data=None, timeout=None):
        self.calls += 1
        file_obj = files[0][1][1]
        if self.calls == 1:
            file_obj.read()  # consume stream fully to simulate requests sending body
            raise requests.exceptions.SSLError("eof")
        if file_obj.tell() != 0:
            return DummyResponse(status_code=400, text="stream not reset")
        return DummyResponse(
            status_code=200,
            payload={"data": {"images": [{"link": "https://imgchest.com/p/retry-ok"}]}},
        )


class TestUploader(unittest.TestCase):
    def test_upload_requires_token(self):
        with patch("src.core.uploader.IMG_CHEST_API_TOKEN", None):
            uploader = ImgChestUploader(api_token=None)
            with self.assertRaises(ValueError):
                uploader.upload_images([{"path": "unused.png", "filename": "unused.png"}], album_title="test")

    def test_upload_uses_content_type_by_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = f"{tmp}/image.webp"
            with open(image_path, "wb") as f:
                f.write(b"fake-bytes")

            session = DummySession(
                [
                    DummyResponse(
                        status_code=200,
                        payload={"data": {"images": [{"link": "https://imgchest.com/p/test"}]}},
                    )
                ]
            )
            uploader = ImgChestUploader(api_token="token", session=session)

            links, errors = uploader.upload_images(
                [{"path": image_path, "filename": "image.webp"}],
                album_title="album",
                retries=0,
            )

            self.assertEqual(links, ["https://imgchest.com/p/test"])
            self.assertEqual(errors, [])
            sent_content_type = session.calls[0]["files"][0][1][2]
            self.assertEqual(sent_content_type, "image/webp")

    def test_upload_partial_failure_returns_links_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = f"{tmp}/a.png"
            second = f"{tmp}/b.png"
            with open(first, "wb") as f:
                f.write(b"a")
            with open(second, "wb") as f:
                f.write(b"b")

            session = DummySession(
                [
                    DummyResponse(
                        status_code=200,
                        payload={"data": {"images": [{"link": "https://imgchest.com/p/ok"}]}},
                    ),
                    DummyResponse(status_code=500, text="server error"),
                ]
            )
            uploader = ImgChestUploader(api_token="token", session=session)

            with patch("src.core.uploader.UPLOAD_BATCH_SIZE", 1):
                links, errors = uploader.upload_images(
                    [
                        {"path": first, "filename": "a.png"},
                        {"path": second, "filename": "b.png"},
                    ],
                    album_title="album",
                    retries=0,
                )

            self.assertEqual(links, ["https://imgchest.com/p/ok"])
            self.assertEqual(len(errors), 1)
            self.assertIn("Lote 2", errors[0])

    def test_retry_reopens_files_after_network_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = f"{tmp}/image.png"
            with open(image_path, "wb") as f:
                f.write(b"image-bytes")

            session = RetryFileAwareSession()
            uploader = ImgChestUploader(api_token="token", session=session)
            links, errors = uploader.upload_images(
                [{"path": image_path, "filename": "image.png"}],
                album_title="album",
                retries=1,
            )

            self.assertEqual(links, ["https://imgchest.com/p/retry-ok"])
            self.assertEqual(errors, [])
            self.assertEqual(session.calls, 2)

    def test_upload_malformed_response_returns_error(self):
        """200 OK but body has no 'images' key — should report error, not silent success."""
        with tempfile.TemporaryDirectory() as tmp:
            image_path = f"{tmp}/img.png"
            with open(image_path, "wb") as f:
                f.write(b"bytes")

            session = DummySession([DummyResponse(status_code=200, payload={"data": {}})])
            uploader = ImgChestUploader(api_token="token", session=session)
            links, errors = uploader.upload_images(
                [{"path": image_path, "filename": "img.png"}],
                album_title="album",
                retries=0,
            )

        self.assertEqual(links, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("Lote 1", errors[0])

    def test_upload_200_with_empty_images_list_returns_error(self):
        """200 OK with images: [] — no links returned, must report error."""
        with tempfile.TemporaryDirectory() as tmp:
            image_path = f"{tmp}/img.png"
            with open(image_path, "wb") as f:
                f.write(b"bytes")

            session = DummySession([DummyResponse(status_code=200, payload={"data": {"images": []}})])
            uploader = ImgChestUploader(api_token="token", session=session)
            links, errors = uploader.upload_images(
                [{"path": image_path, "filename": "img.png"}],
                album_title="album",
                retries=0,
            )

        self.assertEqual(links, [])
        self.assertEqual(len(errors), 1)

    def test_upload_non_json_response_returns_error(self):
        """200 OK but body is not JSON — should return error, not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            image_path = f"{tmp}/img.png"
            with open(image_path, "wb") as f:
                f.write(b"bytes")

            class NonJsonResponse:
                status_code = 200
                text = "<html>error</html>"

                def json(self):
                    raise ValueError("No JSON")

            class NonJsonSession:
                def post(self, *a, **kw):
                    return NonJsonResponse()

            uploader = ImgChestUploader(api_token="token", session=NonJsonSession())
            links, errors = uploader.upload_images(
                [{"path": image_path, "filename": "img.png"}],
                album_title="album",
                retries=0,
            )

        self.assertEqual(links, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("JSON", errors[0])

    def test_does_not_retry_for_http_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = f"{tmp}/image.png"
            with open(image_path, "wb") as f:
                f.write(b"image-bytes")

            session = DummySession([DummyResponse(status_code=400, text="bad request")])
            uploader = ImgChestUploader(api_token="token", session=session)
            links, errors = uploader.upload_images(
                [{"path": image_path, "filename": "image.png"}],
                album_title="album",
                retries=2,
            )

            self.assertEqual(links, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("HTTP 400", errors[0])
            self.assertEqual(len(session.calls), 1)
