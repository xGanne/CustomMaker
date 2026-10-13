import importlib
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.core.danbooru import DanbooruClient
from src.core.env_file import read_env_values, update_env_values


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, content=b""):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.headers = headers or {"Content-Type": "image/png"}
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.exceptions.HTTPError(f"http {self.status_code}", response=self)

    def json(self):
        return self._payload


class TestEnvFile(unittest.TestCase):
    """Segredos ficam no .env, atualizados sem apagar o que já existe."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, ".env")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("# meus segredos\nIMG_CHEST_API_TOKEN=abc123\nGEMINI_API_KEY=xyz\n")

    def test_update_preserves_other_lines_and_comments(self):
        update_env_values({"DANBOORU_LOGIN": "miku_fan", "DANBOORU_API_KEY": "k3y"}, path=self.path)
        values = read_env_values(self.path)
        self.assertEqual(values["IMG_CHEST_API_TOKEN"], "abc123")
        self.assertEqual(values["GEMINI_API_KEY"], "xyz")
        self.assertEqual(values["DANBOORU_LOGIN"], "miku_fan")
        with open(self.path, encoding="utf-8") as f:
            self.assertIn("# meus segredos", f.read())

    def test_update_replaces_and_empty_value_removes(self):
        update_env_values({"DANBOORU_LOGIN": "a", "DANBOORU_API_KEY": "b"}, path=self.path)
        update_env_values({"DANBOORU_LOGIN": "outro", "DANBOORU_API_KEY": ""}, path=self.path)
        values = read_env_values(self.path)
        self.assertEqual(values["DANBOORU_LOGIN"], "outro")
        self.assertNotIn("DANBOORU_API_KEY", values)

    def test_values_with_special_characters_round_trip(self):
        update_env_values({"DANBOORU_API_KEY": 'a b"c#d'}, path=self.path)
        self.assertEqual(read_env_values(self.path)["DANBOORU_API_KEY"], 'a b"c#d')


class TestDanbooruAccount(unittest.TestCase):
    """Conta do Danbooru: autentica só as chamadas à API."""

    def _client(self, login="miku_fan", api_key="k3y"):
        client = DanbooruClient()
        client.load_credentials({"DANBOORU_LOGIN": login, "DANBOORU_API_KEY": api_key})
        self.addCleanup(client.close)
        return client

    def test_search_and_suggestions_send_credentials(self):
        client = self._client()
        with patch.object(client.session, "get", return_value=FakeResponse(payload=[])) as get:
            client.search_posts("hatsune_miku")
            client.fetch_tags("hats")
        for call in get.call_args_list:
            self.assertEqual(call.kwargs.get("auth"), ("miku_fan", "k3y"))

    def test_image_downloads_never_send_credentials(self):
        client = self._client()
        with patch.object(client.session, "get", return_value=FakeResponse(content=b"x")) as get:
            client.download_image("https://cdn.donmai.us/original/a.png")
        self.assertIsNone(get.call_args.kwargs.get("auth"))
        self.assertIsNone(client.session.auth)

    def test_incomplete_credentials_mean_anonymous(self):
        self.assertFalse(self._client(login="so_login", api_key="").is_authenticated)

    def test_profile_reports_limit_and_rejects_bad_credentials(self):
        client = self._client()
        profile = {"id": 1, "name": "miku_fan", "level_string": "Gold", "tag_query_limit": 6}
        with patch.object(client.session, "get", return_value=FakeResponse(payload=profile)):
            self.assertEqual(client.fetch_profile(), {"name": "miku_fan", "level": "Gold", "tag_query_limit": 6})
        with patch.object(client.session, "get", return_value=FakeResponse(status_code=401)):
            with self.assertRaises(PermissionError):
                client.fetch_profile()

    def test_tag_limit_message_suggests_login_only_when_anonymous(self):
        error = FakeResponse(status_code=422, payload={
            "success": False, "error": "PostQuery::TagLimitError",
            "message": "You cannot search for more than 2 tags at a time.",
        })
        anonymous = self._client(login="", api_key="")
        with patch.object(anonymous.session, "get", return_value=error):
            with self.assertRaises(RuntimeError) as ctx:
                anonymous.search_posts("a b order:score")
        self.assertIn("Configurações › Danbooru", str(ctx.exception))

        logged = self._client()
        with patch.object(logged.session, "get", return_value=error):
            with self.assertRaises(RuntimeError) as ctx:
                logged.search_posts("a b c d e f g")
        self.assertNotIn("Configurações › Danbooru", str(ctx.exception))


compat = importlib.import_module("src.qt.compat")


@unittest.skipUnless(compat.QT_AVAILABLE, "PySide6 not installed")
class TestSettingsSavesAccountToEnv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def test_account_goes_to_env_and_never_to_config(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        env_path = os.path.join(tmp, ".env")
        config_path = os.path.join(tmp, "config.json")
        with patch("src.core.env_file.ENV_FILE", env_path), patch("src.core.app_config.CONFIG_FILE", config_path):
            from src.core.app_config import AppConfig
            from src.qt.dialogs.settings_dialog import SettingsDialog
            config = AppConfig()
            dialog = SettingsDialog(config)
            dialog._danbooru_login.setText("miku_fan")
            dialog._danbooru_api_key.setText("segredo123")
            dialog._save()
            env = read_env_values(env_path)
            with open(config_path, encoding="utf-8") as f:
                saved_config = f.read()
        self.assertEqual(env["DANBOORU_LOGIN"], "miku_fan")
        self.assertEqual(env["DANBOORU_API_KEY"], "segredo123")
        self.assertNotIn("segredo123", saved_config)
        self.assertNotIn("segredo123", json.dumps(config.config_data))


if __name__ == "__main__":
    unittest.main()
