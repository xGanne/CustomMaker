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
# espera a confirmação do exe novo (só se extrair já leva segundos); passado
# isto ele é dado como aberto: pode ser só um antivírus demorando
START_TIMEOUT_SECONDS = 60
STARTED_FILE_ENV = "CUSTOMMAKER_UPDATE_STARTED_FILE"
INSTANCE_LOCK_NAME = "instance.lock"

_instance_lock = None


def updates_dir():
    return app_data_path("updates")


def hold_instance_lock(folder=None):
    """Mantém um arquivo aberto enquanto este processo vive (ver abaixo)."""
    global _instance_lock
    folder = folder or updates_dir()
    try:
        os.makedirs(folder, exist_ok=True)
        _instance_lock = open(os.path.join(folder, INSTANCE_LOCK_NAME), "ab")
    except OSError as exc:
        logger.info("Sem trava de instância: %s", exc)


def other_instances_running(folder=None, attempts=5, delay=0.2):
    """Há outro CustomMaker aberto? Não dá para trocar o exe com ele rodando: o
    PyInstaller relê o exe a cada import, e a outra janela passaria a ler o
    arquivo novo com os endereços do antigo. O Windows não apaga arquivo aberto:
    soltando a nossa trava, se o apagar falhar, alguém mais a segura. Tenta
    algumas vezes: uma janela recém-fechada (ou o antivírus) solta o arquivo
    com um pequeno atraso."""
    global _instance_lock
    folder = folder or updates_dir()
    if _instance_lock is not None:
        _instance_lock.close()
        _instance_lock = None
    busy = True
    for attempt in range(attempts):
        try:
            os.remove(os.path.join(folder, INSTANCE_LOCK_NAME))
            busy = False
        except FileNotFoundError:
            busy = False
        except OSError:
            if attempt < attempts - 1:
                time.sleep(delay)
            continue
        break
    hold_instance_lock(folder)
    return busy


def mark_started():
    """O app novo avisa que abriu de verdade: quem atualizou pode sair."""
    path = os.environ.pop(STARTED_FILE_ENV, None)
    if path:
        try:
            with open(path, "w", encoding="utf-8"):
                pass
        except OSError as exc:
            logger.info("Não foi possível confirmar a abertura: %s", exc)


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
    try:
        shutil.copyfile(downloaded, staged)
    except BaseException:
        _remove(staged)  # disco cheio: não deixa meia cópia
        raise
    return staged


def discard_staged(staged):
    _remove(staged)


def _launch(exe_path, args=(), started_file=None):
    env = dict(os.environ)
    # sem isto o exe novo herda o estado do PyInstaller deste processo e se
    # comporta como filho dele (usaria a pasta temporária que está sendo apagada)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if started_file:
        env[STARTED_FILE_ENV] = started_file
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [exe_path, *args], env=env, close_fds=True, creationflags=flags, cwd=os.path.dirname(exe_path),
    )


def _replace_with_retry(source, target, attempts=6, delay=0.5):
    """O antivírus costuma segurar um exe recém-gravado por um instante."""
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def _wait_started(process, started_file, timeout):
    """Espera o exe novo confirmar que abriu; exceção se ele morrer antes."""
    deadline = time.monotonic() + timeout
    while True:
        if os.path.exists(started_file):
            return
        code = process.poll()
        if code == 0:
            return  # terminou bem sem janela (--self-test)
        if code is not None:
            raise RuntimeError(f"o exe novo saiu com código {code}")
        if time.monotonic() >= deadline:
            logger.warning("Atualização: o exe novo não confirmou em %s s.", timeout)
            return
        time.sleep(0.2)


FAILED_UPDATE_NAME = "update_failed.json"


def _record_failure(version, reason, folder=None):
    """O app antigo reaberto conta ao usuário por que continua na mesma versão."""
    import json
    folder = folder or updates_dir()
    try:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, FAILED_UPDATE_NAME), "w", encoding="utf-8") as file_obj:
            json.dump({"version": version, "reason": str(reason)}, file_obj)
    except OSError as exc:
        logger.warning("Não foi possível registrar a atualização desfeita: %s", exc)


def pop_failed_update(folder=None):
    """{"version", "reason"} da última atualização desfeita (uma vez só), ou None."""
    import json
    path = os.path.join(folder or updates_dir(), FAILED_UPDATE_NAME)
    try:
        with open(path, encoding="utf-8") as file_obj:
            data = json.load(file_obj)
    except (OSError, ValueError):
        return None
    finally:
        _remove(path)
    return data if isinstance(data, dict) else None


def apply_update(staged, exe_path, args=(), start_timeout=START_TIMEOUT_SECONDS, version=None, folder=None):
    """Troca o exe e abre o novo. Chamar com a janela já fechada, logo antes de
    sair. Nunca deixa o usuário sem app: se o novo não abrir, o antigo volta e é
    aberto (e avisa na abertura, ver pop_failed_update). Devolve True se o novo abriu."""
    old = exe_path + ".old"
    started_file = exe_path + ".started"
    _remove(started_file)
    _remove(old)  # sobra de uma atualização anterior
    try:
        os.replace(exe_path, old)
    except OSError as exc:
        logger.error("Atualização: não foi possível liberar o exe atual: %s", exc)
        _remove(staged)
        _record_failure(version, f"o exe atual não pôde ser substituído ({exc})", folder)
        _relaunch_quietly(exe_path, args)
        return False
    try:
        _replace_with_retry(staged, exe_path)
        _wait_started(_launch(exe_path, args, started_file), started_file, start_timeout)
        return True
    except Exception as exc:
        logger.error("Atualização desfeita, voltando ao exe anterior: %s", exc)
        _restore(old, exe_path)
        _remove(staged)
        _record_failure(version, exc, folder)
        _relaunch_quietly(exe_path, args)
        return False
    finally:
        _remove(started_file)


def _restore(old, exe_path):
    try:
        _replace_with_retry(old, exe_path)
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
