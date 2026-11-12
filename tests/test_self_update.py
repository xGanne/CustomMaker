import hashlib
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from src.core import self_update
from src.core.update_check import _exe_asset

compat = importlib.import_module("src.qt.compat")

CONTENT = b"exe novo" * 1000


def _release(content=CONTENT, version="9.0.0"):
    return {"version": version, "url": "https://page", "exe_url": "https://dl/CustomMaker.exe",
            "sha256": hashlib.sha256(content).hexdigest()}


def _response(content=CONTENT):
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [content[:100], content[100:]]
    return response


class _TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.exe = os.path.join(self.tmp, "CustomMaker.exe")
        self.staged = self.exe + ".new"
        self._write(self.exe, b"antigo")
        self._write(self.staged, b"novo")

    @staticmethod
    def _write(path, data):
        with open(path, "wb") as file_obj:
            file_obj.write(data)

    @staticmethod
    def _read(path):
        with open(path, "rb") as file_obj:
            return file_obj.read()


class TestDownload(_TempCase):
    def test_downloads_and_checks_the_hash(self):
        with patch("requests.get", return_value=_response()):
            path = self_update.download_update(_release(), folder=self.tmp)
        self.assertEqual(self._read(path), CONTENT)
        self.assertFalse(os.path.exists(path + ".part"))

    def test_corrupted_download_is_discarded(self):
        with patch("requests.get", return_value=_response(b"trocado no caminho" * 50)):
            with self.assertRaises(ValueError):
                self_update.download_update(_release(), folder=self.tmp)
        self.assertEqual([n for n in os.listdir(self.tmp) if n.startswith("CustomMaker-")], [])

    def test_intact_previous_download_is_reused(self):
        with patch("requests.get", return_value=_response()):
            first = self_update.download_update(_release(), folder=self.tmp)
        with patch("requests.get", side_effect=AssertionError("não devia baixar de novo")):
            self.assertEqual(self_update.download_update(_release(), folder=self.tmp), first)

    def test_cancel_leaves_nothing_behind(self):
        cancel = threading.Event()
        cancel.set()
        with patch("requests.get", return_value=_response()):
            self.assertIsNone(self_update.download_update(_release(), cancel, folder=self.tmp))
        self.assertEqual([n for n in os.listdir(self.tmp) if n.startswith("CustomMaker-")], [])


class TestApply(_TempCase):
    def _running(self):
        process = MagicMock()
        process.poll.return_value = None
        return process

    def test_swaps_and_launches_the_new_exe(self):
        with patch.object(self_update, "_launch", return_value=self._running()) as launch:
            self.assertTrue(self_update.apply_update(self.staged, self.exe, start_timeout=0))
        self.assertEqual(self._read(self.exe), b"novo")
        self.assertEqual(self._read(self.exe + ".old"), b"antigo")
        launch.assert_called_once_with(self.exe, (), self.exe + ".started")

    def test_new_exe_that_dies_brings_the_old_one_back(self):
        crashed = MagicMock()
        crashed.poll.return_value = 3
        with patch.object(self_update, "_launch", side_effect=[crashed, self._running()]) as launch:
            self.assertFalse(self_update.apply_update(self.staged, self.exe, start_timeout=0))
        self.assertEqual(self._read(self.exe), b"antigo")
        self.assertEqual(launch.call_count, 2)  # o antigo foi reaberto

    def test_crash_after_seconds_extracting_still_rolls_back(self):
        # um exe de arquivo único só se extrai por segundos: o crash vem depois
        slow_crash = MagicMock()
        slow_crash.poll.side_effect = [None, None, 1]
        with patch.object(self_update, "_launch", side_effect=[slow_crash, self._running()]):
            self.assertFalse(self_update.apply_update(self.staged, self.exe, start_timeout=30))
        self.assertEqual(self._read(self.exe), b"antigo")

    def test_confirmation_from_the_new_app_ends_the_wait(self):
        process = self._running()

        def launch(_exe, _args, started_file):
            with patch.dict(os.environ, {self_update.STARTED_FILE_ENV: started_file}):
                self_update.mark_started()  # o que o app novo faz ao abrir
                self.assertNotIn(self_update.STARTED_FILE_ENV, os.environ)
            return process

        with patch.object(self_update, "_launch", side_effect=launch):
            started = time.monotonic()
            self.assertTrue(self_update.apply_update(self.staged, self.exe, start_timeout=30))
        self.assertLess(time.monotonic() - started, 5)
        self.assertFalse(os.path.exists(self.exe + ".started"))

    def test_antivirus_holding_the_new_exe_is_waited(self):
        real_replace = os.replace
        calls = []

        def flaky(source, target):
            calls.append(source)
            if source == self.staged and calls.count(source) < 3:
                raise PermissionError("em análise")
            real_replace(source, target)

        with patch.object(self_update.os, "replace", side_effect=flaky), \
                patch.object(self_update.time, "sleep"), \
                patch.object(self_update, "_launch", return_value=self._running()):
            self.assertTrue(self_update.apply_update(self.staged, self.exe, start_timeout=0))
        self.assertEqual(self._read(self.exe), b"novo")

    def test_failed_copy_leaves_no_partial_file(self):
        os.remove(self.staged)

        def partial(_source, target):
            self._write(target, b"meio")
            raise OSError("disco cheio")

        with patch("shutil.copyfile", side_effect=partial):
            with self.assertRaises(OSError):
                self_update.stage_update("x", self.exe)
        self.assertFalse(os.path.exists(self.staged))

    def test_launch_failure_brings_the_old_one_back(self):
        with patch.object(self_update, "_launch", side_effect=[OSError("bloqueado"), self._running()]):
            self.assertFalse(self_update.apply_update(self.staged, self.exe, start_timeout=0))
        self.assertEqual(self._read(self.exe), b"antigo")

    def test_exe_that_cannot_be_moved_stays_and_reopens(self):
        with patch.object(self_update.os, "replace", side_effect=PermissionError("preso")), \
                patch.object(self_update, "_launch", return_value=self._running()) as launch:
            self.assertFalse(self_update.apply_update(self.staged, self.exe))
        self.assertEqual(self._read(self.exe), b"antigo")
        self.assertFalse(os.path.exists(self.staged))
        launch.assert_called_once()

    @unittest.skipUnless(os.name == "nt", "regra do Windows: exe em execução")
    def test_real_running_exe_is_swapped(self):
        ping = os.path.join(os.environ["SystemRoot"], "System32", "PING.EXE")
        shutil.copyfile(ping, self.exe)
        shutil.copyfile(ping, self.staged)
        running = subprocess.Popen([self.exe, "-n", "3", "127.0.0.1"], stdout=subprocess.DEVNULL)
        self.addCleanup(running.wait)
        self.assertTrue(self_update.apply_update(self.staged, self.exe, args=["-n", "1", "127.0.0.1"]))
        self.assertTrue(os.path.exists(self.exe + ".old"))
        self.assertFalse(os.path.exists(self.staged))


@unittest.skipUnless(os.name == "nt", "o Windows não apaga arquivo aberto")
class TestInstanceLock(_TempCase):
    def setUp(self):
        super().setUp()

        def release():
            if self_update._instance_lock is not None:
                self_update._instance_lock.close()
                self_update._instance_lock = None

        self.addCleanup(release)

    def test_detects_another_process_holding_the_lock(self):
        self_update.hold_instance_lock(self.tmp)
        self.assertFalse(self_update.other_instances_running(self.tmp))  # só este processo

        path = os.path.join(self.tmp, self_update.INSTANCE_LOCK_NAME)
        code = f"import sys,time; f=open({path!r},'ab'); print('ok',flush=True); time.sleep(30)"
        other = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        other.stdout.readline()
        self.assertTrue(self_update.other_instances_running(self.tmp))

        other.kill()
        other.wait()
        self.assertFalse(self_update.other_instances_running(self.tmp))
        self.assertIsNotNone(self_update._instance_lock)  # continua segurando a própria


class TestCleanup(_TempCase):
    def test_removes_leftovers_and_keeps_newer_downloads(self):
        folder = os.path.join(self.tmp, "updates")
        os.makedirs(folder)
        for name in ("CustomMaker-1.0.0.exe", "CustomMaker-2.0.0.exe", "CustomMaker-3.0.0.exe.part",
                     "CustomMaker-3.0.0.exe"):
            self._write(os.path.join(folder, name), b"x")
        self._write(self.exe + ".old", b"antigo")
        self_update.cleanup_previous("2.0.0", exe_path=self.exe, folder=folder, retries=1, delay=0)
        self.assertEqual(os.listdir(folder), ["CustomMaker-3.0.0.exe"])
        self.assertFalse(os.path.exists(self.exe + ".old"))
        self.assertFalse(os.path.exists(self.staged))


class TestReleaseAsset(unittest.TestCase):
    def test_needs_the_exe_with_its_hash(self):
        asset = {"name": "CustomMaker.exe", "browser_download_url": "https://dl/x.exe", "digest": "sha256:abc"}
        self.assertEqual(_exe_asset([asset]), {"exe_url": "https://dl/x.exe", "sha256": "abc"})
        self.assertEqual(_exe_asset([dict(asset, digest=None)]), {})
        self.assertEqual(_exe_asset([dict(asset, browser_download_url="http://dl/x.exe")]), {})
        self.assertEqual(_exe_asset([dict(asset, name="outro.zip")]), {})
        self.assertEqual(_exe_asset(None), {})


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestUpdateInWindow(_TempCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def setUp(self):
        super().setUp()
        from _qt_helpers import dispose_window
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(self.tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(self.tmp, "presets.json")),
            # a trava real fica na pasta de dados do usuário
            patch("src.core.self_update.other_instances_running", return_value=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        self.window = QtMainWindow(AppConfig())
        self.addCleanup(dispose_window, self.app, self.window)
        self.pages = []
        self.window._offer_update = self.pages.append

    def _settle(self):
        end = time.monotonic() + 5
        while self.window.task_runner._tasks and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

    def _check(self, can_update=True, download=None, manual=False):
        download = download or (lambda *_a, **_k: self.exe)
        with patch("src.core.update_check.fetch_latest_release", return_value=_release()), \
                patch("src.core.self_update.can_self_update", return_value=can_update), \
                patch("src.core.self_update.download_update", side_effect=download):
            self.window.check_for_updates(manual=manual)
            self._settle()
            self._settle()  # a consulta dispara o download

    def test_downloads_in_background_and_offers_restart(self):
        self._check()
        self.assertEqual(self.pages, [])  # nenhuma janela interrompendo
        self.assertEqual(self.window._update_ready["version"], "9.0.0")
        self.assertIn("9.0.0", self.window._update_button.text())

    def test_without_self_update_offers_the_page(self):
        self._check(can_update=False)
        self.assertIsNone(self.window._update_ready)
        self.assertEqual(len(self.pages), 1)

    def test_turned_off_only_warns(self):
        self.window.app_config.set("auto_download_updates", False)
        self._check()
        self.assertIsNone(self.window._update_ready)
        self.assertEqual(len(self.pages), 1)

    def test_failed_download_is_silent_unless_requested(self):
        def fail(*_a, **_k):
            raise OSError("sem rede")
        self._check(download=fail)
        self.assertEqual((self.window._update_ready, self.pages), (None, []))
        self._check(download=fail, manual=True)
        self.assertEqual(len(self.pages), 1)

    def test_other_window_open_blocks_the_swap(self):
        self.window._update_ready = {"version": "9.0.0", "path": self.staged}
        self.window.show_warning = MagicMock()
        with patch("src.core.self_update.other_instances_running", return_value=True), \
                patch.object(self.window, "close") as close, \
                patch("src.core.self_update.apply_update") as apply:
            self.window.restart_to_update()
        close.assert_not_called()
        apply.assert_not_called()
        self.window.show_warning.assert_called_once()

    def test_refused_exit_keeps_the_app_and_drops_the_copy(self):
        source = self.staged + "x"
        self._write(source, b"novo")
        self.window._update_ready = {"version": "9.0.0", "path": source}
        with patch("src.qt.main_window.sys.executable", self.exe), \
                patch.object(self.window, "close", return_value=False), \
                patch("src.core.self_update.apply_update") as apply:
            self.window.restart_to_update()
        apply.assert_not_called()
        self.assertFalse(os.path.exists(self.staged))
        self.assertEqual(self._read(self.exe), b"antigo")

    def test_accepted_exit_swaps_and_quits(self):
        source = self.staged + "x"
        self._write(source, b"novo")
        self.window._update_ready = {"version": "9.0.0", "path": source}
        with patch("src.qt.main_window.sys.executable", self.exe), \
                patch.object(self.window, "close", return_value=True), \
                patch("src.core.self_update.apply_update") as apply, \
                patch("src.qt.main_window.QApplication.quit") as quit_app:
            self.window.restart_to_update()
        apply.assert_called_once_with(self.staged, self.exe)
        quit_app.assert_called_once()

    def test_setting_is_saved(self):
        from src.qt.dialogs.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.window.app_config, self.window)
        self.addCleanup(dialog.deleteLater)
        self.assertTrue(dialog._auto_download_updates.isChecked())
        dialog._auto_download_updates.setChecked(False)
        with patch("src.core.env_file.update_env_values"), patch("src.core.env_file.read_env_values", return_value={}):
            dialog._save()
        self.assertFalse(self.window.app_config.get("auto_download_updates"))


if __name__ == "__main__":
    unittest.main()
