import importlib
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from src.core.update_check import fetch_latest_release, is_newer, parse_version, update_to_offer

compat = importlib.import_module("src.qt.compat")


class TestVersions(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("1.2"), (1, 2, 0))
        self.assertIsNone(parse_version("nightly"))
        self.assertTrue(is_newer("v1.10.0", "1.9.9"))  # numérico, não texto
        self.assertFalse(is_newer("v1.1.0", "1.1.0"))
        self.assertFalse(is_newer("lixo", "1.0.0"))

    def test_offer_skips_old_and_dismissed_versions(self):
        release = {"version": "1.2.0", "url": "https://x"}
        self.assertEqual(update_to_offer(release, "1.1.0"), release)
        self.assertIsNone(update_to_offer(release, "1.2.0"))
        self.assertIsNone(update_to_offer(release, "1.1.0", dismissed="1.2.0"))
        self.assertEqual(update_to_offer(release, "1.1.0", dismissed="1.1.5"), release)
        self.assertIsNone(update_to_offer(None, "1.1.0"))


class TestFetch(unittest.TestCase):
    def _response(self, status=200, data=None):
        response = MagicMock(status_code=status)
        response.json.return_value = data or {}
        return response

    def test_reads_the_latest_release(self):
        data = {"tag_name": "v1.2.0", "html_url": "https://github.com/x/releases/v1.2.0"}
        with patch("requests.get", return_value=self._response(data=data)) as get:
            self.assertEqual(fetch_latest_release(), {"version": "1.2.0", "url": data["html_url"]})
        self.assertNotIn("auth", get.call_args.kwargs)  # requisição anônima

    def test_network_errors_and_prereleases_give_none(self):
        with patch("requests.get", side_effect=OSError("offline")):
            self.assertIsNone(fetch_latest_release())
        with patch("requests.get", return_value=self._response(status=404)):
            self.assertIsNone(fetch_latest_release())
        pre = {"tag_name": "v2.0.0", "html_url": "u", "prerelease": True}
        with patch("requests.get", return_value=self._response(data=pre)):
            self.assertIsNone(fetch_latest_release())


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestUpdateCheckInWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def setUp(self):
        from _qt_helpers import dispose_window
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", os.path.join(self.tmp, "config.json")),
            patch("src.core.preset_manager.PRESETS_FILE", os.path.join(self.tmp, "presets.json")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        from src.core.app_config import AppConfig
        from src.qt.main_window import QtMainWindow
        self.window = QtMainWindow(AppConfig())
        self.addCleanup(dispose_window, self.app, self.window)
        self.offers = []
        self.window._offer_update = self.offers.append

    def _check(self, release, manual=False):
        with patch("src.core.update_check.fetch_latest_release", return_value=release):
            self.window.check_for_updates(manual=manual)
            end = time.monotonic() + 5
            while self.window.task_runner._tasks and time.monotonic() < end:
                self.app.processEvents()
                time.sleep(0.01)
        self.app.processEvents()

    def test_offers_a_newer_release_unless_dismissed(self):
        self._check({"version": "99.0.0", "url": "https://x"})
        self.assertEqual([o["version"] for o in self.offers], ["99.0.0"])
        self.window.app_config.set("update_dismissed_version", "99.0.0")
        self._check({"version": "99.0.0", "url": "https://x"})
        self.assertEqual(len(self.offers), 1)  # dispensada: não oferece de novo
        self._check({"version": "99.0.0", "url": "https://x"}, manual=True)
        self.assertEqual(len(self.offers), 2)  # pedido manual sempre mostra

    def test_source_runs_never_check_on_their_own(self):
        with patch("src.qt.main_window.QTimer.singleShot") as single_shot:
            self.window._schedule_update_check()
        single_shot.assert_not_called()  # fora do exe: atualiza pelo git


if __name__ == "__main__":
    unittest.main()
