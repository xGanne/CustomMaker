"""Leitura e atualização do arquivo .env de segredos (tokens e chaves de API).

Segredos ficam só aqui — nunca no custommaker_config.json nem no log.
"""
import logging
import os

from dotenv import dotenv_values

from src.utils.resource_loader import app_data_path


logger = logging.getLogger(__name__)

ENV_FILE = app_data_path(".env")


def read_env_values(path=None):
    """Valores atuais do .env (relidos do disco a cada chamada)."""
    path = path or ENV_FILE
    if not os.path.exists(path):
        return {}
    try:
        return {k: v for k, v in dotenv_values(path).items() if v is not None}
    except OSError as exc:
        logger.warning("Não foi possível ler %s: %s", path, exc)
        return {}


def _quote(value):
    value = str(value)
    if value and all(ch.isalnum() or ch in "-_.@" for ch in value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def update_env_values(updates, path=None):
    """Grava/atualiza chaves no .env preservando as demais linhas.

    Valor vazio ou None remove a chave. Escrita atômica (tmp + replace).
    """
    path = path or ENV_FILE
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    pending = dict(updates)
    output = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in pending:
            value = pending.pop(key)
            if value:
                output.append(f"{key}={_quote(value)}")
            continue
        output.append(line)
    for key, value in pending.items():
        if value:
            output.append(f"{key}={_quote(value)}")
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output) + "\n")
    os.replace(tmp_path, path)
