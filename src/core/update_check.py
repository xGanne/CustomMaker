"""Aviso de versão nova: consulta a última Release do GitHub (sem atualizar sozinho)."""

import logging
import re

logger = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/xGanne/CustomMaker/releases/latest"


def parse_version(text):
    """'v1.2.3' / '1.2' -> (1, 2, 3) / (1, 2, 0); None se não for uma versão."""
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", (text or "").strip())
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def is_newer(tag, current):
    latest, mine = parse_version(tag), parse_version(current)
    return latest is not None and mine is not None and latest > mine


def fetch_latest_release(timeout=8):
    """{'version', 'url'} da última Release, ou None (sem rede, sem release...).

    Só uma requisição anônima à API pública do GitHub — nenhum dado do usuário.
    """
    import requests  # só quando a checagem roda
    try:
        response = requests.get(
            RELEASES_API, timeout=timeout,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "CustomMaker"},
        )
        if response.status_code != 200:
            return None
        data = response.json()
    except Exception as exc:  # rede fora, JSON inválido: tenta na próxima abertura
        logger.info("Checagem de versão nova falhou: %s", exc)
        return None
    tag, url = data.get("tag_name"), data.get("html_url")
    if data.get("draft") or data.get("prerelease") or not tag or not url:
        return None
    return {"version": tag.lstrip("v"), "url": url}


def update_to_offer(release, current, dismissed=None):
    """A Release se ela for mais nova que `current` e não foi dispensada."""
    if not release or not is_newer(release["version"], current):
        return None
    if dismissed and parse_version(dismissed) == parse_version(release["version"]):
        return None
    return release
