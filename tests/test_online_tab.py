import importlib
import os
import threading
import time
import unittest


online_module = importlib.import_module("src.qt.tabs.online_tab")
QT_AVAILABLE = getattr(online_module, "QT_AVAILABLE", False)


class FakeConfig:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        pass


class FakeMainWindow:
    def __init__(self, task_runner):
        self.app_config = FakeConfig()
        self.task_runner = task_runner
        self.statuses = []
        self.warnings = []

    def show_status(self, message, timeout_ms=5000):
        self.statuses.append(message)

    def show_warning(self, title, message):
        self.warnings.append((title, message))

    def show_info(self, title, message):
        pass


def _posts(count, start=1):
    return [{"id": start + i, "rating": "g"} for i in range(count)]


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestOnlineTabSearch(unittest.TestCase):
    """M16: cancelar busca, pular para página N e retorno após salto vazio."""

    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.app = compat.QApplication.instance() or compat.QApplication([])
        cls.TaskRunner = importlib.import_module("src.qt.task_runner").QtTaskRunner

    def setUp(self):
        self.main = FakeMainWindow(self.TaskRunner())
        self.main.app_config.set("danbooru_page_size", 20)  # os cenários usam páginas de 20
        self.tab = online_module.OnlineTab(self.main)
        self.requests = []
        self.limits = []
        self.pages = {}  # page -> posts
        self.gate = None
        self.tab.client.search_posts = self._fake_search

    def tearDown(self):
        if self.gate is not None:
            self.gate.set()
        self.tab.close()
        self.tab.deleteLater()
        self.app.processEvents()

    def _fake_search(self, tags, limit=20, page=1):
        self.requests.append(page)
        self.limits.append(limit)
        if self.gate is not None:
            self.gate.wait(5)
        return list(self.pages.get(page, []))

    def _wait_until(self, condition, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.processEvents()
            if condition():
                return True
            time.sleep(0.01)
        return False

    def _search_and_wait(self, **kwargs):
        if "page" in kwargs or "use_active_tags" in kwargs:
            self.tab.search(**kwargs)
        else:
            self.tab.search_edit.setText("hatsune_miku")
            self.tab.search()
        self.assertTrue(self._wait_until(lambda: not self.tab._is_searching()))
        self.app.processEvents()

    def test_search_button_turns_into_cancel_while_searching(self):
        self.pages[1] = _posts(20)
        self.gate = threading.Event()
        self.tab.search_edit.setText("hatsune_miku")
        self.tab.search()
        self.assertEqual(self.tab.search_button.text(), "Cancelar")
        self.assertTrue(self.tab.search_button.isEnabled())
        self.gate.set()
        self.assertTrue(self._wait_until(lambda: not self.tab._is_searching()))
        self.assertEqual(self.tab.search_button.text(), "Buscar")

    def test_cancel_restores_previous_page_and_discards_late_result(self):
        self.pages[1] = _posts(20)
        self.pages[2] = _posts(20, start=100)
        self._search_and_wait()
        self.assertEqual(self.tab.current_page, 1)

        self.gate = threading.Event()
        self.tab.change_page(1)
        self.assertEqual(self.tab.current_page, 2)
        self.tab._on_search_button_clicked()  # Cancelar
        self.assertEqual(self.tab.current_page, 1)
        self.assertEqual(self.tab.search_button.text(), "Buscar")
        self.assertIn("Busca cancelada.", self.main.statuses)

        # a resposta atrasada da página 2 não pode substituir a página 1
        self.gate.set()
        self._wait_until(lambda: False, timeout=0.3)
        self.assertEqual(self.tab.current_page, 1)
        self.assertEqual([p["id"] for p in self.tab.posts][:1], [1])
        self.assertEqual(self.tab.results_grid.count(), 20)

    def test_typing_a_page_number_jumps_to_it(self):
        self.pages[1] = _posts(20)
        self.pages[7] = _posts(20, start=700)
        self._search_and_wait()
        self.tab.page_label.setValue(7)
        self.tab._jump_to_typed_page()
        self.assertTrue(self._wait_until(lambda: not self.tab._is_searching()))
        self.assertEqual(self.tab.current_page, 7)
        self.assertEqual(self.tab.posts[0]["id"], 700)
        self.assertEqual(self.requests, [1, 7])

    def test_empty_jumped_page_returns_directly_to_previous_page(self):
        self.pages[1] = _posts(20)
        self._search_and_wait()
        self.requests.clear()

        self.tab.page_label.setValue(500)
        self.tab._jump_to_typed_page()
        self.assertTrue(self._wait_until(lambda: len(self.requests) == 2 and not self.tab._is_searching()))
        # 500 vazia -> volta direto para a página de onde saiu, sem recuar uma a uma
        self.assertEqual(self.requests, [500, 1])
        self.assertEqual(self.tab.current_page, 1)
        self.assertEqual(len(self.tab.posts), 20)

    def test_search_keeps_typed_tags_in_the_field(self):
        self.pages[1] = _posts(3)
        self._search_and_wait()
        self.assertEqual(self.tab.search_edit.text(), "hatsune_miku")
        self.assertEqual(self.main.app_config.get("danbooru_search_history"), ["hatsune_miku"])

    def test_query_respects_two_tag_limit(self):
        """Ordenação padrão e blacklist não ocupam vagas do limite de tags."""
        self.tab.search_edit.setText("hatsune_miku solo")
        self.tab.blacklist_edit.setText("gore blood")
        self.tab.rating_combo.setCurrentText("Geral")
        self.assertEqual(self.tab._build_tags(), "hatsune_miku solo rating:g")
        self.tab.sort_combo.setCurrentText("Melhor avaliados")
        self.assertEqual(self.tab._build_tags(), "hatsune_miku solo rating:g order:score")

    def test_portrait_filter_adds_ratio_metatag_and_is_remembered(self):
        self.tab.search_edit.setText("hatsune_miku solo")
        self.tab.portrait_check.setChecked(True)
        self.assertEqual(self.tab._build_tags(), f"hatsune_miku solo {online_module.PORTRAIT_RATIO_TAG}")
        self.assertTrue(self.main.app_config.get("danbooru_portrait_only"))
        self.tab.portrait_check.setChecked(False)
        self.assertEqual(self.tab._build_tags(), "hatsune_miku solo")

    def test_blacklist_is_filtered_from_results(self):
        posts = _posts(20)
        posts[0]["tag_string"] = "hatsune_miku gore"
        posts[1]["tag_string"] = "hatsune_miku blood"
        self.pages[1] = posts
        self.tab.blacklist_edit.setText("gore blood")
        self._search_and_wait()
        self.assertEqual(len(self.tab.posts), 18)
        self.assertNotIn(1, [p["id"] for p in self.tab.posts])
        self.assertIn("2 oculto(s)", self.tab.summary_label.text())
        # a página veio cheia do servidor: ainda há próxima página
        self.assertTrue(self.tab._has_next_page)

    def test_page_fully_hidden_by_blacklist_is_not_end_of_results(self):
        self.pages[1] = _posts(20)
        self.pages[2] = [dict(p, tag_string="gore") for p in _posts(20, start=100)]
        self.tab.blacklist_edit.setText("gore")
        self._search_and_wait()
        self.requests.clear()
        self.tab.change_page(1)
        self.assertTrue(self._wait_until(lambda: not self.tab._is_searching()))
        # não volta para a página 1 (F22): a página 2 existe, só está toda oculta
        self.assertEqual(self.requests, [2])
        self.assertEqual(self.tab.current_page, 2)
        self.assertIn("Todos ocultos", self.tab.summary_label.text())

    def test_page_size_change_applies_to_next_new_search_only(self):
        self.pages[1] = _posts(20)
        self.pages[2] = _posts(20, start=100)
        self._search_and_wait()
        self.main.app_config.set("danbooru_page_size", 60)
        self.tab.change_page(1)  # paginação da busca ativa mantém o tamanho
        self.assertTrue(self._wait_until(lambda: not self.tab._is_searching()))
        self._search_and_wait()  # busca nova adota o tamanho configurado
        self.assertEqual(self.limits, [20, 20, 60])

    def test_empty_next_page_still_steps_back_one(self):
        """F22 continua valendo para o avanço normal com →."""
        self.pages[1] = _posts(20)
        self._search_and_wait()
        self.requests.clear()
        self.tab.change_page(1)
        self.assertTrue(self._wait_until(lambda: len(self.requests) == 2 and not self.tab._is_searching()))
        self.assertEqual(self.requests, [2, 1])
        self.assertEqual(self.tab.current_page, 1)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestImportDownloadsLargeVersion(unittest.TestCase):
    """Importar baixa a versão large (quando basta); "Baixar" mantém o original."""

    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.app = compat.QApplication.instance() or compat.QApplication([])
        cls.TaskRunner = importlib.import_module("src.qt.task_runner").QtTaskRunner

    def setUp(self):
        import tempfile
        from types import SimpleNamespace
        self.tmp = tempfile.mkdtemp()
        self.main = FakeMainWindow(self.TaskRunner())
        self.main.editor_state = SimpleNamespace(image_list=[])
        self.main.ui_preferences = SimpleNamespace(last_folder=self.tmp)
        self.main.added = []
        self.main.add_images = lambda paths, **_kw: self.main.added.extend(paths)

        def run_task(_task_id, _title, task_fn, on_done, **_kw):
            on_done(task_fn(threading.Event(), None))

        self.main.run_task = run_task
        self.tab = online_module.OnlineTab(self.main)
        self.urls = []
        self.tab.client.download_image = lambda url: self.urls.append(url) or b"data"
        self.post = {
            "id": 42, "image_width": 3497, "image_height": 5000, "file_ext": "png",
            "file_url": "https://cdn/original/42.png", "large_file_url": "https://cdn/sample/42.jpg",
        }

    def tearDown(self):
        import shutil
        self.tab.close()
        self.tab.deleteLater()
        self.app.processEvents()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_single_import_uses_large_and_jpg_name(self):
        self.tab._import_single_post(self.post)
        self.assertEqual(self.urls, ["https://cdn/sample/42.jpg"])
        self.assertEqual([os.path.basename(p) for p in self.main.added], ["42.jpg"])

    def test_batch_import_uses_large_but_download_keeps_original(self):
        self.tab.selection_state.selected_posts_details[42] = self.post
        self.tab._download_posts(self.tmp, import_after=True)
        self.tab._download_posts(self.tmp, import_after=False)
        self.assertEqual(self.urls, ["https://cdn/sample/42.jpg", "https://cdn/original/42.png"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "42.png")))


class TestImportFolderName(unittest.TestCase):
    def test_sanitizes_query_for_windows(self):
        name = online_module.import_folder_name('hatsune_miku  solo rating:g "x"/y?')
        self.assertEqual(name, "hatsune_miku solo ratingg xy")

    def test_empty_or_dots_falls_back(self):
        self.assertEqual(online_module.import_folder_name(""), "importados")
        self.assertEqual(online_module.import_folder_name(" ... "), "importados")
        self.assertEqual(len(online_module.import_folder_name("a" * 200)), 60)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestImportWithoutOpenFolder(unittest.TestCase):
    """Sem pasta aberta, importar usa Imagens/CustomMaker/<busca>."""

    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.app = compat.QApplication.instance() or compat.QApplication([])
        cls.TaskRunner = importlib.import_module("src.qt.task_runner").QtTaskRunner

    def test_managed_folder_is_used_and_created(self):
        import shutil
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        main = FakeMainWindow(self.TaskRunner())
        main.editor_state = SimpleNamespace(image_list=[])
        main.ui_preferences = SimpleNamespace(last_folder=None)
        tab = online_module.OnlineTab(main)
        self.addCleanup(tab.deleteLater)
        self.addCleanup(tab.close)
        tab._active_query_label = "hatsune_miku solo"
        with patch.object(online_module.QStandardPaths, "writableLocation", return_value=tmp):
            folder = tab._resolve_import_directory()
        self.assertEqual(folder, os.path.join(tmp, "CustomMaker", "hatsune_miku solo"))
        self.assertTrue(os.path.isdir(folder))


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestGenerateCustoms(unittest.TestCase):
    """Fluxo em um clique: baixar → enquadrar → exportar/enviar."""

    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.app = compat.QApplication.instance() or compat.QApplication([])
        cls.TaskRunner = importlib.import_module("src.qt.task_runner").QtTaskRunner

    def setUp(self):
        import shutil
        import tempfile
        from types import SimpleNamespace
        from src.qt.mixins.export_mixin import ExportMixin
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        main = FakeMainWindow(self.TaskRunner())
        from src.core.editor_state import EditorState
        main.editor_state = EditorState()
        main.ui_preferences = SimpleNamespace(last_folder=self.tmp)
        main.added, main.infos, main.links = [], [], []
        main.add_images = lambda paths, **_kw: main.added.extend(paths)
        main.show_info = lambda _t, msg: main.infos.append(msg)
        main.mudae_command = ExportMixin.mudae_command
        main._show_links_dialog = lambda title, links: main.links.append((title, links))
        main.choose_directory = lambda _title: os.path.join(self.tmp, "out")
        main.uploader = SimpleNamespace(api_token="token", reload_token=lambda: "token")
        main.batch_calls = []

        class FakeBatch:
            def save_all_images(_self, out_dir, paths=None, **_kw):
                main.batch_calls.append(("folder", out_dir, list(paths)))
                return {"processed": len(paths), "errors": 0, "cancelled": False,
                        "generated_states": {paths[0]: {"pos": (1, 2), "size": (3, 4)}}}

            def upload_to_imgchest(_self, title, paths=None, **_kw):
                main.batch_calls.append(("imgchest", title, list(paths)))
                return {"links": [f"https://imgchest/{i}" for i in range(len(paths))], "errors": [],
                        "cancelled": False, "generated_states": {}}

        main.batch_controller = FakeBatch()

        def run_task(_task_id, _title, task_fn, on_done, **_kw):
            on_done(task_fn(threading.Event(), None))

        main.run_task = run_task
        self.main = main
        self.tab = online_module.OnlineTab(main)
        self.addCleanup(self.tab.deleteLater)
        self.addCleanup(self.tab.close)
        self.tab.client.download_image = lambda url: b"data"
        for post_id in (7, 8):
            self.tab.selection_state.selected_posts_details[post_id] = {
                "id": post_id, "file_ext": "jpg", "file_url": f"https://cdn/{post_id}.jpg",
            }

    def test_folder_destination_exports_only_downloaded_files(self):
        self.tab.generate_customs("folder")
        expected = [os.path.join(self.tmp, "7.jpg"), os.path.join(self.tmp, "8.jpg")]
        self.assertEqual(self.main.batch_calls, [("folder", os.path.join(self.tmp, "out"), expected)])
        self.assertEqual(self.main.added, expected)
        # o editor adota o enquadramento usado no export
        self.assertEqual(self.main.editor_state.image_states[expected[0]], {"pos": (1, 2), "size": (3, 4)})
        # enquadramento automático: não conta como ajuste nem como "não exportado"
        self.assertEqual(self.main.editor_state.user_adjusted, set())
        self.assertEqual(self.main.editor_state.image_dirty, set())
        self.assertIn("2 custom(s) salva(s)", self.main.infos[-1])

    def test_imgchest_destination_copies_mudae_command(self):
        from unittest.mock import patch
        from src.qt.compat import QGuiApplication
        self.tab._active_query_label = "miku"
        with patch("src.qt.compat.QInputDialog.getText", return_value=("Miku", True)):
            self.tab.generate_customs("imgchest")
        self.assertEqual(self.main.batch_calls[0][:2], ("imgchest", "Miku"))
        self.assertEqual(self.main.links, [("Miku", ["https://imgchest/0", "https://imgchest/1"])])
        self.assertEqual(
            QGuiApplication.clipboard().text(),
            "$ai Miku $\nhttps://imgchest/0 $\nhttps://imgchest/1",
        )

    def test_no_selection_warns_without_downloading(self):
        self.tab.selection_state.clear()
        self.tab.generate_customs("folder")
        self.assertEqual(self.main.batch_calls, [])
        self.assertTrue(self.main.warnings)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 not installed")
class TestAutocompleteCache(unittest.TestCase):
    """M16: sugestões por prefixo ficam em cache durante a sessão."""

    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.compat = compat
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def _wait(self, condition, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.processEvents()
            if condition():
                return True
            time.sleep(0.01)
        return False

    def test_repeated_prefix_does_not_hit_network(self):
        autocomplete_module = importlib.import_module("src.qt.widgets.danbooru_autocomplete")

        class CountingClient:
            def __init__(self):
                self.calls = []

            def fetch_tags(self, query):
                self.calls.append(query)
                return [{"name": f"{query}_tag", "post_count": 10}]

        client = CountingClient()
        window = self.compat.QWidget()
        entry = self.compat.QLineEdit(window)
        autocomplete = autocomplete_module.DanbooruAutocomplete(entry, client)
        try:
            entry.setText("miku")
            entry.setCursorPosition(4)
            autocomplete._fetch_suggestions()
            self.assertTrue(self._wait(lambda: autocomplete.popup.count() > 0))
            autocomplete.popup.clear()

            autocomplete._fetch_suggestions()  # mesmo prefixo
            self.assertEqual(autocomplete.popup.count(), 1)
            self.assertEqual(client.calls, ["miku"])
        finally:
            autocomplete.close()
            window.deleteLater()

    def test_empty_results_are_not_cached(self):
        autocomplete_module = importlib.import_module("src.qt.widgets.danbooru_autocomplete")

        class EmptyClient:
            def __init__(self):
                self.calls = 0

            def fetch_tags(self, query):
                self.calls += 1
                return []  # também é o retorno em erro de rede

        client = EmptyClient()
        window = self.compat.QWidget()
        entry = self.compat.QLineEdit(window)
        autocomplete = autocomplete_module.DanbooruAutocomplete(entry, client)
        try:
            entry.setText("zz")
            entry.setCursorPosition(2)
            autocomplete._fetch_suggestions()
            self.assertTrue(self._wait(lambda: client.calls == 1))
            self._wait(lambda: False, timeout=0.1)
            autocomplete._fetch_suggestions()
            self.assertTrue(self._wait(lambda: client.calls == 2))
        finally:
            autocomplete.close()
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()
