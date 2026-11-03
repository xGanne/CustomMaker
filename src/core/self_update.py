"""Atualização do exe: baixa em segundo plano, confere o hash e troca ao reiniciar.

O Windows não deixa sobrescrever um exe em execução, mas deixa renomear: o exe
atual vira `.old`, o novo entra no lugar e é aberto. Se ele não abrir, o antigo
volta. O `.old` só pode ser apagado depois que o processo antigo sai, então
quem limpa é a próxima abertura (`cleanup_previous`).
"""

import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

from src.core.update_check import parse_version
from src.utils.resource_loader import app_data_path

logger = logging.getLogger(__name__)

CHUNK_BYTES = 1024 * 1024
# o novo exe é considerado ok se ainda está rodando depois deste tempo
LAUNCH_CHECK_SECONDS = 3


def updates_dir():
    return app_data_path("updates")


def can_self_update(exe_path=None):
    """Só no exe, numa pasta onde dá para gravar (Arquivos de Programas não dá)."""
    if not getattr(sys, "frozen", False):
        return False
    return _is_writable(os.path.dirname(exe_path or sys.executable))


def _is_writable(folder):
    try:
        with tempfile.TemporaryFile(dir=folder):
            return True
    except OSError:
        return False


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def download_update(release, cancel_event=None, folder=None):
    """Baixa o exe de `release`; devolve o caminho, ou None se cancelado.

    Exceção se a rede falhar ou o hash não bater (o arquivo é descartado).
    Um download anterior íntegro da mesma versão é reaproveitado.
    """
    import requests  # só quando há atualização para baixar
    folder = folder or updates_dir()
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"CustomMaker-{release['version']}.exe")
    expected = release["sha256"].lower()
    if os.path.isfile(target):
        if _sha256_of(target) == expected:
            return target
        _remove(target)
    part = target + ".part"
    digest = hashlib.sha256()
    try:
        with requests.get(release["exe_url"], stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            with open(part, "wb") as file_obj:
                for chunk in response.iter_content(CHUNK_BYTES):
                    if cancel_event is not None and cancel_event.is_set():
                        return None
                    file_obj.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"hash do download não confere (versão {release['version']})")
        os.replace(part, target)
        return target
    finally:
        _remove(part)  # já renomeado (sucesso) ou incompleto


def stage_update(downloaded, exe_path):
    """Copia o novo exe para junto do atual. É a parte lenta e a que pode falhar
    (disco, permissão): roda antes de fechar o app e sem tocar no exe atual."""
    import shutil
    staged = exe_path + ".new"
    shutil.copyfile(downloaded, staged)
    return staged


def discard_staged(staged):
    _remove(staged)


def _launch(exe_path, args=()):
    env = dict(os.environ)
    # sem isto o exe novo herda o estado do PyInstaller deste processo e se
    # comporta como filho dele (usaria a pasta temporária que está sendo apagada)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [exe_path, *args], env=env, close_fds=True, creationflags=flags, cwd=os.path.dirname(exe_path),
    )


def apply_update(staged, exe_path, args=(), check_seconds=LAUNCH_CHECK_SECONDS):
    """Troca o exe e abre o novo. Chamar com a janela já fechada, logo antes de
    sair. Nunca deixa o usuário sem app: em qualquer falha, o antigo volta e é
    aberto. Devolve True se o novo abriu."""
    old = exe_path + ".old"
    _remove(old)  # sobra de uma atualização anterior
    try:
        os.replace(exe_path, old)
    except OSError as exc:
        logger.error("Atualização: não foi possível liberar o exe atual: %s", exc)
        _remove(staged)
        _relaunch_quietly(exe_path, args)
        return False
    try:
        os.replace(staged, exe_path)
        process = _launch(exe_path, args)
        try:
            code = process.wait(timeout=check_seconds)
        except subprocess.TimeoutExpired:
            return True  # segue rodando
        if code == 0:
            return True
        raise RuntimeError(f"o exe novo saiu com código {code}")
    except Exception as exc:
        logger.error("Atualização desfeita, voltando ao exe anterior: %s", exc)
        _restore(old, exe_path)
        _remove(staged)
        _relaunch_quietly(exe_path, args)
        return False


def _restore(old, exe_path):
    try:
        os.replace(old, exe_path)
    except OSError as exc:
        logger.critical("Atualização: não foi possível restaurar %s: %s", exe_path, exc)


def _relaunch_quietly(exe_path, args):
    try:
        _launch(exe_path, args)
    except Exception as exc:
        logger.error("Atualização: não foi possível reabrir %s: %s", exe_path, exc)


def cleanup_previous(current_version, exe_path=None, folder=None, retries=10, delay=1.0):
    """Ao abrir: apaga o `.old` (o processo antigo pode levar uns segundos para
    sair) e os downloads já instalados. Download de versão mais nova fica:
    pode ter sido baixado e o app fechado sem reiniciar por ele."""
    exe_path = exe_path or sys.executable
    folder = folder or updates_dir()
    _remove(exe_path + ".new")
    mine = parse_version(current_version)
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    for name in names:
        match = re.fullmatch(r"CustomMaker-(.+)\.exe(\.part)?", name)
        version = parse_version(match.group(1)) if match else None
        if match and (match.group(2) or (version is not None and version <= mine)):
            _remove(os.path.join(folder, name))
    old = exe_path + ".old"
    for _ in range(retries):
        if not os.path.exists(old):
            return
        _remove(old)
        if not os.path.exists(old):
            return
        time.sleep(delay)


def cleanup_previous_in_background(current_version):
    threading.Thread(target=cleanup_previous, args=(current_version,), daemon=True).start()
