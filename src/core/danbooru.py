import logging
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


class DanbooruClient:
    def __init__(self, user_agent="CustomMakerv2/1.0 (by xGanne on GitHub)", config=None):
        self.base_url = "https://danbooru.donmai.us"
        self.headers = {"User-Agent": user_agent}
        self.config = config
        self.session = requests.Session()

        self.timeout_search_s = self._cfg_int("danbooru_timeout_search_s", 10, minimum=1, maximum=120)
        self.timeout_tags_s = self._cfg_int("danbooru_timeout_tags_s", 5, minimum=1, maximum=120)
        self.timeout_download_s = self._cfg_int("danbooru_timeout_download_s", 15, minimum=1, maximum=300)
        self._configure_session()

    def _cfg_int(self, key, default, minimum=None, maximum=None):
        value = default
        if self.config and hasattr(self.config, "get"):
            value = self.config.get(key, default)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default

        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _cfg_float(self, key, default, minimum=None, maximum=None):
        value = default
        if self.config and hasattr(self.config, "get"):
            value = self.config.get(key, default)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = default

        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _configure_session(self):
        pool_connections = self._cfg_int("danbooru_pool_connections", 16, minimum=1, maximum=256)
        pool_maxsize = self._cfg_int("danbooru_pool_maxsize", 32, minimum=1, maximum=256)
        retry_total = self._cfg_int("danbooru_retry_total", 2, minimum=0, maximum=10)
        retry_backoff = self._cfg_float("danbooru_retry_backoff", 0.35, minimum=0.0, maximum=10.0)

        retry = Retry(
            total=retry_total,
            connect=retry_total,
            read=retry_total,
            status=retry_total,
            backoff_factor=retry_backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            max_retries=retry,
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        logger.debug(
            "Danbooru session configured: pool_connections=%s pool_maxsize=%s retry_total=%s backoff=%.2f",
            pool_connections,
            pool_maxsize,
            retry_total,
            retry_backoff,
        )

    @staticmethod
    def _is_pixiv_asset(url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return "pximg.net" in host

    def _build_download_headers(self, url: str) -> dict:
        headers = dict(self.headers)
        if self._is_pixiv_asset(url):
            headers["Referer"] = "https://www.pixiv.net/"
        return headers

    def search_posts(self, tags, limit=20, page=1):
        """Searches posts on Danbooru."""
        url = f"{self.base_url}/posts.json"
        params = {"tags": tags, "limit": limit, "page": page}
        start = time.perf_counter()
        response = None

        try:
            response = self.session.get(
                url,
                params=params,
                headers=self.headers,
                timeout=self.timeout_search_s,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as exc:
            status_code = response.status_code if response is not None else None
            if status_code == 429:
                logger.warning("Danbooru rate limit atingido.")
                return []
            logger.warning("HTTP Error Danbooru (status=%s): %s", status_code, exc)
            return []
        except requests.exceptions.RequestException as exc:
            logger.warning("Erro ao buscar posts Danbooru: %s", exc)
            return []
        except ValueError as exc:
            logger.warning("Resposta JSON invalida em search_posts: %s", exc)
            return []
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug("Danbooru search_posts latency: %.1fms tags='%s' page=%s", elapsed_ms, tags, page)

    def fetch_tags(self, query):
        """Fetches tags starting with query from Danbooru."""
        if not query or len(query) < 2:
            return []

        url = f"{self.base_url}/tags.json"
        params = {
            "search[name_matches]": f"{query}*",
            "search[order]": "count",
            "limit": 10,
        }
        start = time.perf_counter()

        try:
            response = self.session.get(
                url,
                params=params,
                headers=self.headers,
                timeout=self.timeout_tags_s,
            )
            if response.status_code == 200:
                data = response.json()
                return [t["name"] for t in data if "name" in t]
            return []
        except requests.exceptions.RequestException as exc:
            logger.debug("Falha ao buscar tags Danbooru para query='%s': %s", query, exc)
            return []
        except ValueError as exc:
            logger.debug("JSON invalido em fetch_tags query='%s': %s", query, exc)
            return []
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug("Danbooru fetch_tags latency: %.1fms query='%s'", elapsed_ms, query)

    def download_image(self, url):
        start = time.perf_counter()
        try:
            response = self.session.get(
                url,
                headers=self._build_download_headers(url),
                timeout=self.timeout_download_s,
            )
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type and not (
                content_type.startswith("image/")
                or content_type.startswith("video/")
                or content_type.startswith("application/octet-stream")
            ):
                logger.warning("Download ignorado (Content-Type nao suportado) %s: %s", url, content_type)
                return None
            return response.content
        except requests.exceptions.RequestException as exc:
            logger.warning("Falha no download %s: %s", url, exc)
            return None
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug("Danbooru download latency: %.1fms url='%s'", elapsed_ms, url)

    def close(self):
        try:
            self.session.close()
        except Exception as exc:
            logger.debug("Falha ao fechar sessao Danbooru: %s", exc)
