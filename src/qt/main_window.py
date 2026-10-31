"""
QtMainWindow — janela principal do CustomMaker Pro.

Responsabilidades deste arquivo:
  • Inicialização de todos os componentes (estado, controladores, UI)
  • Construção do layout: toolbar lateral, barra de opções, canvas, painéis
  • Registro de atalhos de teclado e eventos de drag-and-drop
  • Handlers da barra de opções (borda, cor, animação)
  • Utilitários de UI: dialogs, status bar, task runner com progress
  • Eventos do canvas e gerenciamento da lista de imagens

A lógica de domínio está nos mixins em src/qt/mixins/:
  • ImageLoaderMixin  — carregamento, cache e undo
  • AdjustmentsMixin  — fit, rotação, presets
  • AnimationMixin    — loop de prévia de borda animada
  • ExportMixin       — salvar/zip/upload em lote
"""
import os
from collections import OrderedDict

from PIL import Image, ImageGrab

from src.config.settings import BORDA_HEX, SUPPORTED_EXTENSIONS
from src.controllers.batch_controller import BatchController
from src.core.editor_state import EditorState, UiPreferences
from src.core.image_processor import ImageProcessor
from src.core.preset_manager import PresetManager
from src.core.uploader import ImgChestUploader
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.theme import tokens
from src.qt.dialogs.progress_dialog import ProgressDialog
from src.qt.mixins.adjustments_mixin import AdjustmentsMixin
from src.qt.mixins.animation_mixin import AnimationMixin
from src.qt.mixins.export_mixin import ExportMixin
from src.qt.mixins.image_loader_mixin import ImageLoaderMixin
from src.qt.mixins.session_mixin import SessionMixin
from src.qt.tabs.ai_tab import AiTab
from src.qt.tabs.editor_tab import EditorTab
from src.qt.tabs.online_tab import OnlineTab
from src.qt.task_runner import QtTaskRunner
from src.qt.widgets.image_canvas import ImageCanvas
from src.qt.widgets.image_list_panel import ImageListPanel
from src.utils.resource_loader import resource_path

if QT_AVAILABLE:
    from src.qt.compat import (
        QAction,
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QIcon,
        QKeySequence,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSplitter,
        QTabWidget,
        QTimer,
        QToolBar,
        QToolButton,
        QVBoxLayout,
        QHBoxLayout,
        QWidget,
        Qt,
    )


if QT_AVAILABLE:
    class QtMainWindow(
        QMainWindow,
        ExportMixin,
        AdjustmentsMixin,
        AnimationMixin,
        ImageLoaderMixin,
        SessionMixin,
    ):
        def __init__(self, app_config, session_store=None):
            super().__init__()
            self.app_config = app_config
            self.ui_preferences = UiPreferences.from_app_config(app_config)
            self.editor_state = EditorState(
                selected_borda=self.ui_preferences.last_global_borda,
                default_framing=app_config.get("default_framing", "auto_fit"),
            )
            self.preset_manager = PresetManager()
            self.uploader = ImgChestUploader()
            self.face_cascade = ImageProcessor.load_face_cascade()
            self.task_runner = QtTaskRunner(self)
            self.edited_images = {}
            self.batch_controller = BatchController(
                editor_state=self.editor_state,
                app_config=self.app_config,
                uploader=self.uploader,
                borda_hex=BORDA_HEX,
                edited_source_images=self.edited_images,
            )

            # Image loading state
            self.current_original_image = None
            self.current_path = None
            self._image_load_seq = 0
            self._active_image_load_task_id = None

            # Preview cache (LRU em memória)
            self._preview_cache = OrderedDict()
            self._preview_cache_current_bytes = 0
            cache_mb = max(32, min(1024, int(self.ui_preferences.image_cache_max_mb or 256)))
            self._preview_cache_limit_bytes = cache_mb * 1024 * 1024

            # Undo/redo stacks (keyed by file path)
            self._undo_stacks = {}
            self._redo_stacks = {}

            # Animation preview state
            self._active_preview_task_id = None
            self._preview_seq = 0
            self._preview_frames = []
            self._preview_duration = 50
            self._preview_index = 0
            self._preview_timer = QTimer(self)
            self._preview_timer.timeout.connect(self._advance_preview_frame)

            # Color picker state
            self._color_picker_enabled = False

            self.setWindowTitle("Custom Maker Pro (Qt)")
            self.resize(1440, 920)
            self._apply_icon()
            self.setAcceptDrops(True)
            self._build_ui()
            self._register_shortcuts()
            # sessão salva automaticamente; o app passa o store, testes não
            self._init_session(session_store)
            if self.face_cascade is None:
                # M17: sem o cascade, "Ajuste Inteligente" silenciosamente vira
                # auto fit — avisar uma vez em vez de esconder a degradação
                self._mark_face_detection_unavailable()
                self.show_status(
                    "Detecção de rosto indisponível (lbpcascade_animeface.xml não carregado) — "
                    "o Ajuste Inteligente usará auto fit.",
                    timeout_ms=10000,
                )
            else:
                self.show_status("UI Qt pronta.")

        FACE_DETECTION_UNAVAILABLE_TIP = (
            "Indisponível: lbpcascade_animeface.xml não foi encontrado, "
            "então não há detecção de rosto. Use o Auto Fit."
        )

        def _mark_face_detection_unavailable(self):
            """M17: desabilita e explica os botões que dependem da detecção de rosto."""
            for button in (self._toolbar_smart_fit_btn, self.editor_tab.smart_fit_all_btn):
                button.setEnabled(False)
                button.setToolTip(self.FACE_DETECTION_UNAVAILABLE_TIP)

        # ── Ícone da janela ────────────────────────────────────────────────

        def _apply_icon(self):
            for candidate in ("icon.ico", "icon.png"):
                icon_path = resource_path(candidate)
                if os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
                    break

        # ── Construção do layout ───────────────────────────────────────────

        def _build_ui(self):
            self._build_toolbar()

            central = QWidget(self)
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(8, 8, 8, 8)
            root_layout.setSpacing(0)

            splitter = QSplitter(Qt.Horizontal, self)
            root_layout.addWidget(splitter)

            # Esquerda: barra de opções + canvas
            left_widget = QWidget(self)
            left_layout = QVBoxLayout(left_widget)
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(0)

            self._build_options_bar(left_widget, left_layout)

            self.image_canvas = ImageCanvas(self)
            self.image_canvas.state_changed.connect(self.on_canvas_state_changed)
            self.image_canvas.border_pos_changed.connect(self.on_border_pos_changed)
            # a borda do canvas já existe: sincronizar desde já, para que
            # enquadramentos calculados antes de abrir uma imagem (ex.: "Gerar
            # customs") usem a mesma referência que o editor
            self.editor_state.borda_pos = self.image_canvas.border_pos
            self.image_canvas.interaction_started.connect(self.save_state_for_undo)  # label = gesto
            self.image_canvas.color_picked.connect(self.on_canvas_color_picked)
            self.image_canvas.color_pick_cancelled.connect(self.cancel_color_picker)
            left_layout.addWidget(self.image_canvas)

            self._image_counter_label = QLabel("")
            self._image_counter_label.setAlignment(Qt.AlignCenter)
            self._image_counter_label.setStyleSheet(
                f"color: {tokens()['text_muted']}; font-size: 11px; padding: 2px 0; background: transparent;"
            )
            left_layout.addWidget(self._image_counter_label)
            splitter.addWidget(left_widget)

            # Direita: tabs + lista de imagens (splitter vertical)
            right_widget = QWidget(self)
            right_outer = QVBoxLayout(right_widget)
            right_outer.setContentsMargins(0, 0, 0, 0)
            right_outer.setSpacing(0)
            right_widget.setMinimumWidth(380)

            right_splitter = QSplitter(Qt.Vertical, right_widget)
            self.tabs = QTabWidget(self)
            self.tabs.setDocumentMode(True)
            self.editor_tab = EditorTab(self, self.tabs)
            self.online_tab = OnlineTab(self, self.tabs)
            self.ai_tab = AiTab(self, self.tabs)
            # Cada aba rola em vez de impor sua altura mínima ao painel: numa
            # tela de 1080p a aba Online não cabia inteira, o Qt espremia os
            # widgets uns sobre os outros e a lista de imagens ia para o rodapé.
            for page, title in ((self.editor_tab, "Edição"), (self.online_tab, "Online"), (self.ai_tab, "IA")):
                self.tabs.addTab(self._scrollable_tab(page), title)

            self.image_list_panel = ImageListPanel(self)
            self.image_list_panel.selection_changed.connect(self.load_image)
            self.image_list_panel.remove_requested.connect(self.remove_images_at)
            self.image_list_panel.toggle_individual_requested.connect(self.toggle_individual_border)
            self.image_list_panel.order_changed.connect(self._on_image_list_reordered)

            right_splitter.addWidget(self.tabs)
            right_splitter.addWidget(self.image_list_panel)
            right_splitter.setChildrenCollapsible(False)
            # As abas precisam de mais altura que a lista: a grade de resultados
            # da aba Online só mostra uma linha inteira de cards a partir daqui.
            right_splitter.setStretchFactor(0, 3)
            right_splitter.setStretchFactor(1, 2)
            right_splitter.setSizes([560, 320])
            right_outer.addWidget(right_splitter)
            splitter.addWidget(right_widget)
            splitter.setSizes([980, 460])

        def _scrollable_tab(self, page):
            from src.qt.compat import QScrollArea

            area = QScrollArea(self.tabs)
            area.setWidgetResizable(True)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setWidget(page)
            return area

        def _build_toolbar(self):
            from src.qt.icons import make_icon
            from src.qt.compat import QSize

            toolbar = QToolBar("Ferramentas", self)
            toolbar.setMovable(False)
            toolbar.setFloatable(False)
            toolbar.setOrientation(Qt.Vertical)
            toolbar.setIconSize(QSize(22, 22))
            self.addToolBar(Qt.LeftToolBarArea, toolbar)

            def _tool_btn(icon_name, tip, handler, shortcut="", checkable=False):
                btn = QToolButton()
                icon = make_icon(icon_name)
                if icon:
                    btn.setIcon(icon)
                btn.setToolTip(f"{tip}  {shortcut}".strip())
                btn.setCheckable(checkable)
                btn.clicked.connect(handler)
                return btn

            self._folder_btn = _tool_btn("folder-open", "Selecionar Pasta  (clique direito: recentes)", self.load_folder, "Ctrl+O")
            self._folder_btn.setContextMenuPolicy(Qt.CustomContextMenu)
            self._folder_btn.customContextMenuRequested.connect(self._show_recent_folders_menu)
            toolbar.addWidget(self._folder_btn)
            toolbar.addWidget(_tool_btn("clipboard", "Colar Imagem", self.paste_image, "Ctrl+V"))
            # clique desfaz; a setinha abre o histórico da imagem (salto direto)
            self._undo_btn = _tool_btn(
                "arrow-uturn-left", "Desfazer  (setinha: histórico · Ctrl+Alt+Z: alternar com o anterior)",
                self.undo_current_image, "Ctrl+Z",
            )
            history_menu = QMenu(self._undo_btn)
            history_menu.aboutToShow.connect(lambda: self._populate_history_menu(history_menu))
            self._undo_btn.setMenu(history_menu)
            self._undo_btn.setPopupMode(QToolButton.MenuButtonPopup)
            toolbar.addWidget(self._undo_btn)
            toolbar.addSeparator()
            toolbar.addWidget(_tool_btn("arrows-pointing-out", "Auto Fit", self.apply_auto_fit, "Alt+B"))
            self._toolbar_smart_fit_btn = _tool_btn(
                "face-smile", "Ajuste Inteligente — repita para alternar entre rostos", self.apply_intelligent_fit, "Alt+F"
            )
            toolbar.addWidget(self._toolbar_smart_fit_btn)
            toolbar.addWidget(_tool_btn("magnifying-glass", "Zoom 100%", self.zoom_to_actual_size, "Ctrl+0"))
            toolbar.addSeparator()
            self._toolbar_pick_btn = _tool_btn(
                "eye-dropper", "Pick Color — clique: todas · Shift+clique: só esta · Ctrl: média 3×3 · Esc: sair",
                self._toggle_color_picker_btn, checkable=True
            )
            toolbar.addWidget(self._toolbar_pick_btn)
            toolbar.addSeparator()
            toolbar.addWidget(_tool_btn("rotate-left", "Rotacionar Esquerda", lambda: self.rotate_current_image("left"), "Ctrl+Q"))
            toolbar.addWidget(_tool_btn("rotate-right", "Rotacionar Direita", lambda: self.rotate_current_image("right"), "Ctrl+E"))
            toolbar.addSeparator()
            toolbar.addWidget(_tool_btn("cog", "Configurações", self._open_settings))

        def _build_options_bar(self, parent_widget, parent_layout):
            bar = QWidget(parent_widget)
            bar.setObjectName("OptionsBar")
            bar.setFixedHeight(44)
            bar_layout = QHBoxLayout(bar)
            bar_layout.setContentsMargins(8, 4, 8, 4)
            bar_layout.setSpacing(6)

            border_label = QLabel("Borda:")
            border_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            bar_layout.addWidget(border_label)
            self.options_border_combo = QComboBox()
            self.options_border_combo.addItems(sorted(BORDA_HEX.keys()) + ["Cor Personalizada"])
            self.options_border_combo.setFixedWidth(150)
            self.options_border_combo.setToolTip("Cor da borda do custom")
            self.options_border_combo.currentTextChanged.connect(self._on_options_border_changed)
            bar_layout.addWidget(self.options_border_combo)

            self.options_color_swatch = QPushButton()
            self.options_color_swatch.setFixedSize(30, 30)
            self.options_color_swatch.setCursor(Qt.PointingHandCursor)
            self.options_color_swatch.setToolTip("Conta-gotas: escolher cor a partir da imagem")
            self.options_color_swatch.clicked.connect(self._on_options_color_swatch_clicked)
            bar_layout.addWidget(self.options_color_swatch)

            self.options_color_edit = QLineEdit()
            self.options_color_edit.setPlaceholderText("#FFFFFF")
            self.options_color_edit.setFixedWidth(88)
            self.options_color_edit.setAlignment(Qt.AlignCenter)
            self.options_color_edit.setToolTip("Cor personalizada em hexadecimal")
            self.options_color_edit.textChanged.connect(self._on_options_custom_color_changed)
            bar_layout.addWidget(self.options_color_edit)

            # cor automática: borda que combina com cada custom
            self.auto_border_button = QPushButton("Auto")
            self.auto_border_button.setProperty("class", "secondary")
            self.auto_border_button.setToolTip(
                "Cor automática: escolhe uma borda que combina com o que aparece em cada custom"
            )
            auto_menu = QMenu(self.auto_border_button)
            auto_menu.addAction("Nesta imagem", lambda: self.apply_auto_border(all_images=False))
            auto_menu.addAction("Em todas as imagens", lambda: self.apply_auto_border(all_images=True))
            self.auto_border_button.setMenu(auto_menu)
            self.auto_border_button.setProperty("hasMenu", "true")
            bar_layout.addWidget(self.auto_border_button)

            bar_layout.addSpacing(8)
            anim_label = QLabel("Animação:")
            anim_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            bar_layout.addWidget(anim_label)
            self.options_anim_combo = QComboBox()
            from src.qt.tabs.editor_tab import ANIMATION_OPTIONS
            self.options_anim_combo.addItems(ANIMATION_OPTIONS)
            self.options_anim_combo.setFixedWidth(150)
            self.options_anim_combo.setToolTip("Animação aplicada à borda na exportação")
            self.options_anim_combo.currentTextChanged.connect(self._on_options_anim_changed)
            bar_layout.addWidget(self.options_anim_combo)

            bar_layout.addStretch(1)
            apply_all_btn = QPushButton("Aplicar a Todas")
            apply_all_btn.setProperty("class", "secondary")
            apply_all_btn.setToolTip("Aplica borda e animação atuais a todas as imagens da lista")
            apply_all_btn.clicked.connect(self.apply_style_to_all)
            bar_layout.addWidget(apply_all_btn)

            parent_layout.addWidget(bar)
            self._update_options_color_swatch()

        # ── Handlers da barra de opções ────────────────────────────────────

        def _on_options_border_changed(self, value):
            self.editor_state.selected_borda = value
            self.ui_preferences.last_global_borda = value
            self.options_color_edit.setEnabled(value == "Cor Personalizada")
            self.options_color_swatch.setEnabled(True)
            self._update_options_color_swatch()
            if hasattr(self, "editor_tab"):
                self.editor_tab.sync_from_options_bar()
            self.refresh_current_canvas()

        def _on_options_custom_color_changed(self, value):
            if value.startswith("#") and len(value) == 7:
                self.editor_state.custom_borda_hex = value
                self._update_options_color_swatch()
                self.refresh_current_canvas()

        def _on_options_anim_changed(self, value):
            if value == "Strobe (Pisca)":
                self._warn_strobe_once()
            self.editor_state.animation_type = value
            if hasattr(self, "editor_tab"):
                self.editor_tab.sync_from_options_bar()
            self.refresh_current_canvas()
            self.show_status(f"Animação: {value}")

        def _warn_strobe_once(self):
            """M10: aviso de fotossensibilidade exibido só na primeira seleção."""
            if self.app_config.get("strobe_warning_acknowledged"):
                return
            QMessageBox.warning(
                self,
                "Aviso de fotossensibilidade",
                "A animação Strobe alterna cores saturadas rapidamente e pode "
                "desencadear crises em pessoas com epilepsia fotossensível.\n\n"
                "A frequência foi limitada a menos de 3 flashes por segundo, mas "
                "avise quem for ver o custom.",
            )
            self.app_config.set("strobe_warning_acknowledged", True)
            self.app_config.save()

        def _on_options_color_swatch_clicked(self):
            self.toggle_color_picker()
            if hasattr(self, "_toolbar_pick_btn"):
                self._toolbar_pick_btn.setChecked(self._color_picker_enabled)

        def _update_options_color_swatch(self):
            if not hasattr(self, "options_color_swatch"):
                return
            color = self.editor_state.custom_borda_hex or "#FFFFFF"
            self.options_color_swatch.setStyleSheet(
                f"background-color: {color}; border: 1px solid {tokens()['border_soft']}; border-radius: 4px;"
            )

        def refresh_options_bar(self):
            """Sincroniza a barra de opções com editor_state (chamado por EditorTab)."""
            if not hasattr(self, "options_border_combo"):
                return
            state = self.editor_state
            self.options_border_combo.blockSignals(True)
            self.options_anim_combo.blockSignals(True)
            self.options_color_edit.blockSignals(True)

            idx = self.options_border_combo.findText(state.selected_borda)
            if idx >= 0:
                self.options_border_combo.setCurrentIndex(idx)
            self.options_anim_combo.setCurrentText(state.animation_type)
            self.options_color_edit.setText(state.custom_borda_hex or "")
            self.options_color_edit.setEnabled(state.selected_borda == "Cor Personalizada")
            self._update_options_color_swatch()

            self.options_border_combo.blockSignals(False)
            self.options_anim_combo.blockSignals(False)
            self.options_color_edit.blockSignals(False)

        # ── Atalhos de teclado ─────────────────────────────────────────────

        def _register_shortcuts(self):
            # Os atalhos saem do registro de comandos: o atalho exibido na
            # paleta é sempre o que funciona. Ctrl+Z / Ctrl+V / ←/→ / B ficam em
            # keyPressEvent para não roubar as teclas de campos de texto (F3).
            self.commands = self._build_command_registry()
            for command in self.commands.all():
                if not command.register_shortcut:
                    continue
                action = QAction(self)
                action.setShortcut(QKeySequence(command.shortcut))
                # o handler valida sozinho (ex.: "Nenhuma imagem carregada")
                action.triggered.connect(lambda _checked=False, c=command: c.handler())
                self.addAction(action)
            for sequence in ("Ctrl+K", "Ctrl+Shift+P"):
                action = QAction(self)
                action.setShortcut(QKeySequence(sequence))
                action.triggered.connect(self.open_command_palette)
                self.addAction(action)
            if not self.app_config.get("command_palette_hint_shown"):
                # com a janela como contexto: o timer morre junto se ela fechar antes
                QTimer.singleShot(2500, self, self._show_command_palette_hint)

        def _show_command_palette_hint(self):
            if not self._window_alive():
                return
            self.show_status("Novo: Ctrl+K abre a paleta de comandos — digite o que quer fazer.", timeout_ms=12000)
            self.app_config.set("command_palette_hint_shown", True)
            self.app_config.save()

        # ── Paleta de comandos (Ctrl+K) ────────────────────────────────────

        def _build_command_registry(self):
            from src.qt.commands import Command, CommandRegistry
            from src.qt.tabs.editor_tab import ANIMATION_OPTIONS

            has_images = lambda: bool(self.editor_state.image_list)
            has_current = lambda: bool(self.current_path)
            idle = lambda: has_images() and not self._running_user_operations()
            reg = CommandRegistry()
            static = [
                ("file.open", "Abrir pasta", self.load_folder, "Arquivo", "Ctrl+O", ("carregar", "imagens"), None, True),
                ("file.paste", "Colar imagem", self.paste_image, "Arquivo", "Ctrl+V", ("clipboard",), None, False),
                ("edit.undo", "Desfazer", self.undo_current_image, "Editar", "Ctrl+Z", (), has_current, False),
                ("edit.redo", "Refazer", self.redo_current_image, "Editar", "Ctrl+Y", (), has_current, False),
                ("edit.toggle_last", "Alternar com o passo anterior", self.toggle_last_state, "Editar", "Ctrl+Alt+Z", ("comparar", "antes", "historico"), has_current, True),
                ("edit.history", "Histórico desta imagem", self._show_history_menu, "Editar", "", ("desfazer", "passos"), has_current, False),
                ("edit.clear_history", "Limpar histórico desta imagem", self.clear_history, "Editar", "", ("desfazer", "memoria"), has_current, False),
                ("frame.auto", "Auto fit", self.apply_auto_fit, "Enquadramento", "Alt+B", ("ajustar", "borda"), has_current, True),
                ("frame.smart", "Ajuste inteligente (rosto)", self.apply_intelligent_fit, "Enquadramento", "Alt+F", ("face",), has_current, True),
                ("frame.auto_all", "Auto fit em todas", lambda: self.apply_adjustment_to_all("auto_fit"), "Enquadramento", "", ("lote",), idle, False),
                ("frame.smart_all", "Ajuste inteligente em todas", lambda: self.apply_adjustment_to_all("intelligent_fit"), "Enquadramento", "", ("lote", "rosto"), idle, False),
                ("frame.copy_all", "Copiar enquadramento para todas", self.copy_framing_to_all, "Enquadramento", "", ("lote",), has_current, False),
                ("view.zoom100", "Zoom 100%", self.zoom_to_actual_size, "Visualizar", "Ctrl+0", ("tamanho real",), has_current, True),
                ("image.rotate_left", "Rotacionar à esquerda", lambda: self.rotate_current_image("left"), "Imagem", "Ctrl+Q", ("girar",), has_current, True),
                ("image.rotate_right", "Rotacionar à direita", lambda: self.rotate_current_image("right"), "Imagem", "Ctrl+E", ("girar",), has_current, True),
                ("border.pick", "Pick Color (conta-gotas)", self._toggle_color_picker_btn, "Borda", "", ("cor", "pegar"), has_current, False),
                ("border.auto", "Cor de borda automática nesta imagem", lambda: self.apply_auto_border(all_images=False), "Borda", "", ("cor",), has_current, False),
                ("border.auto_all", "Cor de borda automática em todas", lambda: self.apply_auto_border(all_images=True), "Borda", "", ("cor", "lote"), idle, False),
                ("border.apply_all", "Aplicar borda e animação a todas", self.apply_style_to_all, "Borda", "", ("estilo",), has_images, False),
                ("export.all", "Salvar todas", self.save_all_images, "Exportar", "Ctrl+S", ("exportar", "pasta"), idle, True),
                ("export.current", "Salvar imagem atual", self.save_current_image, "Exportar", "Ctrl+Shift+S", ("exportar",), has_current, True),
                ("export.zip", "Exportar ZIP", self.save_zip, "Exportar", "", ("compactar", "salvar"), idle, False),
                ("export.imgchest", "Enviar para ImgChest", self.upload_to_imgchest, "Exportar", "", ("upload", "mudae"), idle, False),
                ("review.open", "Revisar customs", lambda: self.open_review(), "Exportar", "", ("grade", "previa"), has_images, False),
                ("review.sizes", "Calcular tamanhos das customs", lambda: self.open_review(measure=True), "Exportar", "", ("peso", "mb"), has_images, False),
                ("app.settings", "Configurações", self._open_settings, "App", "", ("preferencias", "opcoes"), None, False),
                ("tab.editor", "Ir para a aba Edição", lambda: self.tabs.setCurrentIndex(0), "Navegar", "", (), None, False),
                ("tab.online", "Ir para a aba Online (Danbooru)", self._focus_online_search, "Navegar", "", ("buscar", "danbooru"), None, False),
                ("tab.ai", "Ir para a aba IA", lambda: self.tabs.setCurrentIndex(2), "Navegar", "", (), None, False),
            ]
            for cid, title, handler, category, shortcut, keywords, enabled, register in static:
                reg.register(Command(
                    cid, title, handler, category, shortcut, keywords,
                    enabled or (lambda: True), register_shortcut=register,
                ))

            def dynamic():
                commands = []
                for name in sorted(BORDA_HEX) + ["Cor Personalizada"]:
                    commands.append(Command(
                        f"border.set.{name}", f"Borda: {name}",
                        lambda n=name: self.options_border_combo.setCurrentText(n), "Borda", keywords=("cor",),
                    ))
                for anim in ANIMATION_OPTIONS:
                    # pelo combo: passa pelo aviso de fotossensibilidade do Strobe
                    commands.append(Command(
                        f"anim.set.{anim}", f"Animação: {anim}",
                        lambda a=anim: self.options_anim_combo.setCurrentText(a), "Animação", keywords=("gif",),
                    ))
                for preset in self.preset_manager.list_presets():
                    commands.append(Command(
                        f"preset.{preset}", f"Preset: {preset}",
                        lambda p=preset: self._apply_preset_by_name(p), "Preset",
                    ))
                for mode, label in (("auto_fit", "Auto fit"), ("intelligent", "Inteligente (rosto)")):
                    commands.append(Command(
                        f"framing.default.{mode}", f"Enquadramento padrão: {label}",
                        lambda m=mode: self.set_default_framing(m), "Enquadramento",
                    ))
                return commands

            reg.add_provider(dynamic)
            return reg

        def _apply_preset_by_name(self, name):
            data = self.preset_manager.get_preset(name)
            if not data:
                self.show_status(f"O preset '{name}' não existe mais.")
                return
            self.apply_preset(data)

        def _focus_online_search(self):
            self.tabs.setCurrentIndex(1)
            self.online_tab.search_combo.setFocus()

        def open_command_palette(self):
            from src.qt.dialogs.command_palette import CommandPalette
            recent = [cid for cid in (self.app_config.get("command_palette_recent") or []) if isinstance(cid, str)]
            palette = CommandPalette(self, self.commands, recent_ids=recent, on_run=self._run_command)
            self._command_palette = palette
            palette.show_centered()
            return palette

        def _run_command(self, command):
            recent = [cid for cid in (self.app_config.get("command_palette_recent") or []) if cid != command.id]
            self.app_config.set("command_palette_recent", [command.id] + recent[:7])
            self.app_config.save()
            command.handler()

        # ── Navegação entre imagens ────────────────────────────────────────

        def navigate_images(self, delta):
            image_list = self.editor_state.image_list or []
            if not image_list:
                return
            try:
                idx = image_list.index(self.current_path)
            except ValueError:
                idx = 0
            new_idx = max(0, min(len(image_list) - 1, idx + delta))
            if new_idx != idx:
                self.image_list_panel.set_current_index(new_idx)
                self.load_image(new_idx)

        def _update_image_counter(self):
            image_list = self.editor_state.image_list or []
            total = len(image_list)
            if total == 0:
                self._image_counter_label.setText("")
                return
            try:
                idx = image_list.index(self.current_path) + 1
            except ValueError:
                idx = 0
            filename = os.path.basename(self.current_path) if self.current_path else ""
            self._image_counter_label.setText(f"{filename}  ·  {idx} / {total}")

        def zoom_to_actual_size(self):
            # M8: o indicador permanente no canto do canvas substitui a
            # mensagem efêmera de zoom na status bar
            self.image_canvas.zoom_to_actual_size()

        # ── Utilitários de UI ──────────────────────────────────────────────

        def show_status(self, message, timeout_ms=5000):
            self.statusBar().showMessage(message, timeout_ms)

        def show_info(self, title, message):
            QMessageBox.information(self, title, message)

        def show_warning(self, title, message):
            QMessageBox.warning(self, title, message)

        def show_error(self, title, message):
            QMessageBox.critical(self, title, message)

        def choose_directory(self, title):
            start_dir = self.ui_preferences.last_folder or ""
            return QFileDialog.getExistingDirectory(self, title, start_dir)

        def choose_save_file(self, title, filter_text, suggested_name=None):
            start_dir = self.ui_preferences.last_folder or ""
            if suggested_name:
                start_dir = os.path.join(start_dir, suggested_name) if start_dir else suggested_name
            file_path, _ = QFileDialog.getSaveFileName(self, title, start_dir, filter_text)
            return file_path

        def run_task(self, task_id, title, task_fn, on_done, on_error=None, maximum=1):
            dialog = ProgressDialog(
                self,
                title=title,
                maximum=maximum,
                on_cancel=lambda: self.task_runner.cancel(task_id),
            )
            handle = self.task_runner.submit(task_id, task_fn)
            if handle is None:
                self.show_warning("Tarefa", "Já existe uma operação em andamento com esse identificador.")
                return None

            def close_dialog(*_args):
                dialog.mark_done()
                dialog.close()

            handle.progress.connect(lambda current, total, text: dialog.update_progress(current, total, text))
            handle.done.connect(lambda result: (close_dialog(), on_done(result)))
            if on_error:
                handle.error.connect(lambda exc: (close_dialog(), on_error(exc)))
            else:
                handle.error.connect(lambda exc: (close_dialog(), self.show_error("Erro", str(exc))))
            handle.cancelled.connect(lambda: (close_dialog(), self.show_status("Operação cancelada.")))
            dialog.show()
            return handle

        # ── Eventos do canvas ──────────────────────────────────────────────

        def refresh_current_canvas(self):
            if not self.current_path:
                return
            border_color = self.editor_state.resolve_border_hex(BORDA_HEX, self.current_path)
            self.image_canvas.set_border_color(border_color)
            self._update_preview_animation()

        def on_canvas_state_changed(self, pos, size):
            if not self.current_path:
                return
            # o canvas reemite o estado ao exibir uma imagem e ao reposicionar a
            # borda: só um enquadramento realmente diferente conta como ajuste
            # (senão abrir/navegar já disparava o aviso de "não exportado")
            current = self.editor_state.image_states.get(self.current_path)
            if current and tuple(current["pos"]) == tuple(pos) and tuple(current["size"]) == tuple(size):
                return
            self.editor_state.set_image_state(self.current_path, pos, size)

        def on_border_pos_changed(self, pos):
            # O enquadramento é guardado em coordenadas absolutas da cena. Quando
            # a borda se recentraliza (janela redimensionada/maximizada, divisor
            # arrastado), o canvas só move a imagem visível — as demais tinham
            # que acompanhar, senão o corte delas ficava deslocado na exportação.
            old_x, old_y = self.editor_state.borda_pos
            dx, dy = pos[0] - old_x, pos[1] - old_y
            if dx or dy:
                for state in self.editor_state.image_states.values():
                    x, y = state["pos"]
                    state["pos"] = (x + dx, y + dy)
                # o histórico de desfazer/refazer também guarda posições absolutas
                for stacks in (self._undo_stacks, self._redo_stacks):
                    for stack in stacks.values():
                        stack[:] = [snapshot.shifted(dx, dy) for snapshot in stack]
            self.editor_state.borda_pos = pos

        # ── Color picker ───────────────────────────────────────────────────

        def toggle_color_picker(self):
            self._color_picker_enabled = not self._color_picker_enabled
            self.image_canvas.set_color_pick_enabled(self._color_picker_enabled)
            if self._color_picker_enabled:
                self.show_status("Modo Pick Color ativo. Clique sobre a imagem.")
            else:
                self.show_status("Modo Pick Color desativado.")

        def _toggle_color_picker_btn(self):
            self.toggle_color_picker()
            if hasattr(self, "_toolbar_pick_btn"):
                self._toolbar_pick_btn.setChecked(self._color_picker_enabled)

        def _stop_color_picker(self):
            self._color_picker_enabled = False
            self.image_canvas.set_color_pick_enabled(False)
            if hasattr(self, "_toolbar_pick_btn"):
                self._toolbar_pick_btn.setChecked(False)

        def cancel_color_picker(self):
            """Esc no modo Pick Color."""
            if self._color_picker_enabled:
                self._stop_color_picker()
                self.show_status("Modo Pick Color desativado.")

        def on_canvas_color_picked(self, color, only_current=False):
            self._stop_color_picker()
            QApplication.clipboard().setText(color)
            if only_current and self.current_path:
                # Shift+clique: borda individual só desta imagem (como a cor automática)
                path = self.current_path
                self.editor_state.individual_bordas[path] = "Cor Personalizada"
                self.editor_state.custom_borda_hex_individual[path] = color
                self.editor_state.image_dirty.add(path)
                self.refresh_current_canvas()
                if hasattr(self, "refresh_list_indicators"):
                    self.refresh_list_indicators()
                self.show_status(f"Pick Color: {color} aplicada só nesta imagem e copiada.", timeout_ms=6000)
                return
            self.editor_state.selected_borda = "Cor Personalizada"
            self.editor_state.custom_borda_hex = color
            self.ui_preferences.last_global_borda = "Cor Personalizada"
            self.editor_tab.refresh_from_state()
            self.refresh_options_bar()
            self.refresh_current_canvas()
            # M1: confirmação não crítica vai para a status bar, sem modal
            self.show_status(f"Pick Color: {color} aplicada e copiada para a área de transferência.", timeout_ms=6000)

        # ── Gerenciamento da lista de imagens ──────────────────────────────

        def remove_images_at(self, indices):
            """M9: remove uma ou várias imagens da lista (os arquivos ficam no disco)."""
            image_list = self.editor_state.image_list
            paths = [image_list[i] for i in sorted(set(indices)) if 0 <= i < len(image_list)]
            if not paths:
                return
            if len(paths) > 1:
                answer = QMessageBox.question(
                    self,
                    "Remover imagens",
                    f"Remover {len(paths)} imagens da lista?\n"
                    "Os arquivos não são apagados, mas os ajustes delas serão perdidos.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
            current_removed = self.current_path in paths
            for path in paths:
                self._forget_image(path)
            self.image_list_panel.set_paths(self.editor_state.image_list)
            self.refresh_list_indicators()
            if not self.editor_state.image_list:
                self.current_path = None
                self._close_current_original()
                self.image_canvas.set_loading(False)
                self.image_canvas.clear_image()
                self.stop_preview_animation()
                self.show_status("Lista de imagens vazia.")
                return
            if current_removed:
                self.load_image(self.editor_state.current_image_index or 0)
            else:
                self.image_list_panel.set_current_index(self.editor_state.current_image_index)
                self._update_image_counter()
            if len(paths) > 1:
                self.show_status(f"{len(paths)} imagens removidas da lista.")

        def _forget_image(self, path):
            """Remove a imagem do estado e libera tudo que estava em memória para ela."""
            self.editor_state.remove_image(path)
            cached_preview = self._preview_cache.pop(path, None)
            if cached_preview is not None:
                self._preview_cache_current_bytes = max(
                    0,
                    self._preview_cache_current_bytes - self._estimate_image_bytes(cached_preview),
                )
                try:
                    cached_preview.close()
                except Exception:
                    pass
            edited = self.edited_images.pop(path, None)
            if edited is not None:
                try:
                    edited.close()
                except Exception:
                    pass
            self._dispose_images([snapshot.image for snapshot in self._undo_stacks.pop(path, [])])
            self._drop_redo_stack(path)
            self.__dict__.get("_last_history_op", {}).pop(path, None)
            self.__dict__.get("_face_cycle", {}).pop(path, None)

        def toggle_individual_border(self, index):
            if index < 0 or index >= len(self.editor_state.image_list):
                return
            path = self.editor_state.image_list[index]
            if path in self.editor_state.individual_bordas:
                self.editor_state.individual_bordas.pop(path, None)
            else:
                self.editor_state.individual_bordas[path] = self.editor_state.selected_borda
            if path == self.current_path:
                self.refresh_current_canvas()
            self.refresh_list_indicators()
            self.show_status("Configuração individual de borda atualizada.")

        def _on_image_list_reordered(self, new_paths):
            self.editor_state.image_list = list(new_paths)
            self._update_image_counter()

        # ── Histórico (setinha do Desfazer) ────────────────────────────────

        @staticmethod
        def _relative_time(timestamp):
            seconds = max(0, _time.monotonic() - timestamp)
            if seconds < 60:
                return "agora"
            if seconds < 3600:
                return f"há {int(seconds // 60)} min"
            return f"há {int(seconds // 3600)} h"

        def _populate_history_menu(self, menu):
            """Passos da imagem atual: refazíveis no topo, o atual em negrito e os
            anteriores abaixo (mais recente primeiro); clicar salta direto."""
            menu.clear()
            path = self.current_path
            if path:
                self._drop_noop_undo_steps(path)  # o menu não lista passos que não mudaram nada
            undo = list(self._undo_stacks.get(path, [])) if path else []
            redo = list(self._redo_stacks.get(path, [])) if path else []
            if not undo and not redo:
                menu.addAction("Sem histórico").setEnabled(False)
                return

            def add(text, steps, font_style=None):
                action = menu.addAction(text)
                if font_style:
                    font = action.font()
                    font.setBold(font_style == "bold")
                    font.setItalic(font_style == "italic")
                    action.setFont(font)
                if steps:
                    action.triggered.connect(lambda _checked=False, s=steps: self.jump_history(s))
                else:
                    action.setEnabled(False)
                return action

            # refazíveis: o mais distante no topo, o próximo logo acima do atual
            for index, snapshot in enumerate(redo):
                add(f"↷ {snapshot.label or 'Passo'}", len(redo) - index, "italic")
            # atual: o estado depois da última ação desfazível
            current_label = undo[-1].label if undo else "Início (como abriu)"
            add(f"● {current_label or 'Passo'}", 0, "bold")
            # anteriores: voltar j passos leva ao estado depois da ação undo[k-j]
            for back in range(1, len(undo)):
                snapshot = undo[len(undo) - 1 - back]
                add(f"{snapshot.label or 'Passo'} · {self._relative_time(snapshot.timestamp)}", -back)
            if undo:
                add("Início (como abriu)", -len(undo))
            menu.addSeparator()
            menu.addAction("Limpar histórico desta imagem", self.clear_history)

        def _show_history_menu(self):
            """Abre o histórico pela paleta: o mesmo menu da setinha do Desfazer."""
            if hasattr(self, "_undo_btn"):
                self._undo_btn.showMenu()

        def open_review(self, paths=None, summary=None, measure=False):
            """Revisão em grade das customs (todas da lista, ou só `paths`);
            `measure` já calcula o tamanho de cada uma ao abrir."""
            from src.qt.dialogs.review_dialog import ReviewDialog
            if not self.editor_state.image_list:
                self.show_warning("Revisar", "Nenhuma imagem na lista.")
                return None
            dialog = ReviewDialog(self, paths, summary=summary, measure=measure)
            dialog.show()
            self._review_dialog = dialog
            return dialog

        def _open_settings(self):
            from src.qt.dialogs.settings_dialog import SettingsDialog
            dialog = SettingsDialog(self.app_config, parent=self)
            if dialog.exec():
                # F12: refletir imediatamente o que dá para aplicar a quente
                self.online_tab.refresh_from_config()
                self.ai_tab.refresh_from_config()
                if dialog.theme_changed:
                    self.show_info("Tema", "O novo tema será aplicado na próxima vez que o programa abrir.")
                self.show_status(
                    "Configurações salvas. Tema e performance têm efeito após reiniciar."
                )

        def _show_recent_folders_menu(self, pos):
            recent = self.app_config.get("recent_folders") or []
            if not recent:
                self.show_status("Nenhuma pasta recente.")
                return
            menu = QMenu(self)
            for folder in recent:
                action = menu.addAction(folder)
                action.triggered.connect(lambda _checked, f=folder: self.load_folder(f))
            menu.exec(self._folder_btn.mapToGlobal(pos))

        def refresh_list_indicators(self):
            # só ajuste do usuário conta como "ajustada"; enquadramento padrão
            # calculado automaticamente não pinta a lista
            self.image_list_panel.update_indicators(
                set(self.edited_images.keys()),
                self.editor_state.user_adjusted,
            )
            # M9: badge com a cor das imagens que têm borda individual
            state = self.editor_state
            self.image_list_panel.update_border_badges({
                path: (name, state.resolve_border_hex(BORDA_HEX, path))
                for path, name in state.individual_bordas.items()
            })

        # ── Colar da área de transferência ────────────────────────────────

        def paste_image(self):
            import tempfile
            import time as _time
            import uuid

            try:
                clipboard_content = ImageGrab.grabclipboard()
            except Exception as exc:
                self.show_error("Colar imagem", f"Falha ao acessar a área de transferência: {exc}")
                return
            if not isinstance(clipboard_content, Image.Image):
                self.show_warning("Colar imagem", "Nenhuma imagem encontrada na área de transferência.")
                return
            temp_dir = os.path.join(tempfile.gettempdir(), "CustomMakerPaste")
            os.makedirs(temp_dir, exist_ok=True)
            # F11: nome único por sessão/colagem — nunca sobrescreve um arquivo
            # que ainda esteja na lista de outra colagem
            filename = f"pasted_{_time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.png"
            path = os.path.join(temp_dir, filename)
            try:
                clipboard_content.save(path)
            except OSError as exc:
                self.show_error("Colar imagem", f"Falha ao salvar a imagem colada: {exc}")
                return
            self.add_images([path], replace=False, select_last=True)
            self.show_status("Imagem colada da área de transferência.")

        # ── Eventos de teclado e drag-drop ────────────────────────────────

        def keyPressEvent(self, event):
            # Estas teclas chegam aqui apenas quando o widget focado não as
            # consumiu (ex.: QLineEdit trata Ctrl+V/Ctrl+Z/setas sozinho), então
            # não roubam a edição de texto (F3).
            # F17: a crase é dead key no teclado ABNT — B (de "before") também funciona
            if event.key() == Qt.Key_Escape and self._color_picker_enabled:
                self.cancel_color_picker()
            elif event.key() in (Qt.Key_QuoteLeft, Qt.Key_B) and event.modifiers() == Qt.NoModifier and not event.isAutoRepeat():
                self.image_canvas.show_original_preview()
                self.show_status("Antes (original) — solte a tecla para voltar.", timeout_ms=10000)
            elif event.matches(QKeySequence.Paste):
                self.paste_image()
            elif event.matches(QKeySequence.Undo):
                self.undo_current_image()
            elif event.matches(QKeySequence.Redo):
                self.redo_current_image()
            elif event.key() == Qt.Key_Left and event.modifiers() == Qt.NoModifier:
                self.navigate_images(-1)
            elif event.key() == Qt.Key_Right and event.modifiers() == Qt.NoModifier:
                self.navigate_images(1)
            else:
                super().keyPressEvent(event)

        def keyReleaseEvent(self, event):
            if event.key() in (Qt.Key_QuoteLeft, Qt.Key_B) and not event.isAutoRepeat():
                self.image_canvas.restore_edit_preview()
                self.show_status("Depois (editado).", timeout_ms=2000)
            else:
                super().keyReleaseEvent(event)

        def dragEnterEvent(self, event):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dropEvent(self, event):
            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            folders = [p for p in paths if os.path.isdir(p)]
            files = [p for p in paths if os.path.isfile(p)]
            if folders:
                folder = folders[0]
                folder_paths = [
                    os.path.join(folder, name)
                    for name in sorted(os.listdir(folder))
                    if os.path.isfile(os.path.join(folder, name)) and name.lower().endswith(SUPPORTED_EXTENSIONS)
                ]
                self.add_images(folder_paths, replace=True)
            elif files:
                self.add_images(files, replace=False, select_last=True)
            event.acceptProposedAction()

        # ── Limpeza ao fechar ──────────────────────────────────────────────

        def _confirm_exit_with_unexported(self, dirty_count):
            """M2: pergunta antes de sair; "não perguntar novamente" desliga o aviso."""
            if not self.app_config.get("confirm_exit_with_unexported", True):
                return True
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Sair")
            box.setText(
                f"Você tem {dirty_count} imagem(ns) com ajustes não exportados.\n"
                "Sair mesmo assim?"
            )
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            dont_ask = QCheckBox("Não perguntar novamente")
            box.setCheckBox(dont_ask)
            confirmed = box.exec() == QMessageBox.Yes
            # só desliga o aviso quando o usuário de fato confirmou a saída
            if confirmed and dont_ask.isChecked():
                self.app_config.set("confirm_exit_with_unexported", False)
            return confirmed

        # operações que o usuário espera ver concluídas (resultado, links...)
        _USER_OPERATION_PREFIXES = (
            "qt_save", "qt_upload", "qt_generate", "qt_online_download", "qt_import",
            "qt_adjust_all", "qt_auto_select", "qt_ai_apply",
        )

        def _running_user_operations(self):
            return [
                task_id for task_id in self.task_runner.running_task_ids()
                if task_id.startswith(self._USER_OPERATION_PREFIXES)
            ]

        def closeEvent(self, event):
            self._closing = False
            # sair no meio de um upload/exportação: a janela sumia, mas o processo
            # seguia vivo até a operação acabar, e o resultado (links, comando
            # Mudae) se perdia
            if self._running_user_operations():
                answer = QMessageBox.question(
                    self,
                    "Sair",
                    "Há uma operação em andamento (exportação, upload ou download).\n"
                    "Cancelar e sair?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    event.ignore()
                    return
            # M2: avisa antes de sair se há ajustes/edições ainda não exportados
            dirty_count = len(self.editor_state.image_dirty)
            if dirty_count > 0 and not self._confirm_exit_with_unexported(dirty_count):
                event.ignore()
                return
            # a partir daqui a janela está fechando: tasks em segundo plano que
            # terminarem depois não mexem mais na interface (_window_alive)
            self._closing = True
            # salva a sessão (lista, enquadramentos, edições) antes de liberar tudo
            if getattr(self, "_session_timer", None) is not None:
                self._session_timer.stop()
            self._autosave_session(force=True)
            self.ui_preferences.last_global_borda = self.editor_state.selected_borda
            if self.editor_state.image_list:
                self.ui_preferences.last_folder = os.path.dirname(self.editor_state.image_list[0])
            self.ui_preferences.save_to_app_config(self.app_config)
            self.app_config.save()
            self.stop_preview_animation()
            # tasks em andamento param no próximo ponto de checagem, em vez de
            # manter o processo vivo depois que a janela fecha
            self.task_runner.cancel_all()
            self.batch_controller.shutdown()
            self.online_tab.close()
            self._close_current_original()
            self._clear_preview_cache()
            for image in self.edited_images.values():
                try:
                    image.close()
                except Exception:
                    pass
            self.edited_images.clear()
            for stacks in (self._undo_stacks, self._redo_stacks):
                for stack in stacks.values():
                    self._dispose_images([snapshot.image for snapshot in stack])
                stacks.clear()
            super().closeEvent(event)

else:
    class QtMainWindow:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
