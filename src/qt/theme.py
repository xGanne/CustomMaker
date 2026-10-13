import logging
import os

from src.config.settings import DEFAULT_THEME_VARIANT, UI_THEMES
from src.utils.resource_loader import app_data_path


logger = logging.getLogger(__name__)


# M7: tema ativo da sessão — escolhido em app.py a partir do config, antes de
# qualquer widget ser criado (os widgets leem as cores na construção)
_active_variant = DEFAULT_THEME_VARIANT


def set_active_theme(variant):
    global _active_variant
    _active_variant = variant if variant in UI_THEMES else DEFAULT_THEME_VARIANT
    return _active_variant


def active_theme():
    return _active_variant


def tokens():
    """Tokens de cor/medida do tema ativo."""
    return UI_THEMES[_active_variant]


def _svg_icon_url(name, svg):
    """Grava (uma vez) um ícone SVG do tema em .ui/ e devolve a URL para o QSS."""
    try:
        target_dir = app_data_path(".ui")
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"{name}.svg")
        existing = None
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file_obj:
                existing = file_obj.read()
        if existing != svg:
            with open(path, "w", encoding="utf-8") as file_obj:
                file_obj.write(svg)
        return path.replace("\\", "/")
    except OSError as exc:
        logger.debug("Não foi possível gerar o ícone '%s': %s", name, exc)
        return ""


def _chevron_icon_url(direction, color, variant, name_suffix=""):
    """Chevron de combos/spinboxes como SVG.

    O truque CSS de "triângulo por bordas" não funciona no Qt — ele desenha um
    retângulo. Um SVG real é o caminho previsível.
    """
    path_d = "M1 1.5 L5 5.5 L9 1.5" if direction == "down" else "M1 5.5 L5 1.5 L9 5.5"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="7" viewBox="0 0 10 7">'
        f'<path d="{path_d}" fill="none" stroke="{color}" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )
    return _svg_icon_url(f"chevron-{direction}{name_suffix}-{variant}", svg)


def _check_icon_url(color, variant):
    """Marca de seleção desenhada dentro do indicador de QCheckBox marcado."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
        f'<path d="M2 5.2 L4.2 7.4 L8.2 2.8" fill="none" stroke="{color}" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )
    return _svg_icon_url(f"check-{variant}", svg)


def build_stylesheet(variant=None):
    """Stylesheet global do app para o tema `variant` (padrão: o ativo)."""
    variant = variant if variant in UI_THEMES else _active_variant
    T = UI_THEMES[variant]
    chevron_down = _chevron_icon_url("down", T["text_secondary"], variant)
    chevron_up = _chevron_icon_url("up", T["text_secondary"], variant)
    check_mark = _check_icon_url(T["on_accent"], variant)
    chevron_on_accent = _chevron_icon_url("down", T["on_accent"], variant, "-on-accent")
    return f"""
QWidget {{
    background-color: {T["surface_bg"]};
    color: {T["text_primary"]};
    font-size: 13px;
    selection-background-color: {T["accent"]};
    selection-color: {T["on_accent"]};
}}
QMainWindow, QDialog {{
    background-color: {T["surface_bg"]};
}}
/* Labels e checkboxes não devem pintar fundo próprio: dentro de um group box
   o fundo global (mais escuro) aparecia como uma faixa retangular. */
QLabel, QCheckBox, QRadioButton {{
    background: transparent;
}}

/* ── Checkboxes ───────────────────────────────────────────── */
/* Sem estilo próprio o indicador desmarcado ficava invisível sobre o fundo */
QCheckBox {{
    spacing: 6px;
    color: {T["text_secondary"]};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {T["border_strong"]};
    border-radius: 4px;
    background-color: {T["surface_muted"]};
}}
QCheckBox::indicator:hover {{
    border-color: {T["accent"]};
}}
QCheckBox::indicator:checked {{
    background-color: {T["accent"]};
    border-color: {T["accent"]};
    image: url({check_mark});
}}
QCheckBox:checked {{
    color: {T["text_primary"]};
}}

/* ── Group boxes ──────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {T["border_soft"]};
    border-radius: {T["radius_md"]}px;
    margin-top: 10px;
    padding: 10px 10px 8px 10px;
    background-color: {T["surface_panel"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.8px;
    color: {T["text_muted"]};
    text-transform: uppercase;
}}

/* ── Inputs ───────────────────────────────────────────────── */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
    background-color: {T["surface_muted"]};
    border: 1px solid {T["border_soft"]};
    border-radius: {T["radius_sm"]}px;
    padding: 3px 8px;
    min-height: 16px;
}}
/* Listas ficam fora da regra acima de propósito: um `min-height` em QSS
   sobrescreve setMinimumHeight() no código e achatava a grade de resultados. */
QListWidget {{
    background-color: {T["surface_muted"]};
    border: 1px solid {T["border_soft"]};
    border-radius: {T["radius_sm"]}px;
}}
QComboBox {{
    min-height: 28px;
    padding-right: 24px;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}}
QComboBox::down-arrow {{
    image: url({chevron_down});
    width: 10px;
    height: 7px;
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {T["surface_panel"]};
    border: 1px solid {T["border_soft"]};
    padding: 4px;
}}
QLineEdit {{
    min-height: 28px;
}}
QListWidget {{
    padding: 6px;
}}

/* ── Buttons ──────────────────────────────────────────────── */
QPushButton {{
    background-color: {T["accent"]};
    border: none;
    border-radius: {T["radius_sm"]}px;
    color: {T["on_accent"]};
    min-height: 30px;
    padding: 0 10px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {T["accent_hover"]};
}}
/* seta de botões com menu (ex.: "Gerar customs"): a padrão sumia no azul */
QPushButton::menu-indicator {{
    image: url({chevron_on_accent});
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 10px;
    width: 10px;
    height: 7px;
}}
QPushButton:disabled {{
    background-color: {T["surface_muted"]};
    color: {T["text_muted"]};
}}
QPushButton[class="secondary"] {{
    background-color: transparent;
    border: 1px solid {T["border_soft"]};
    color: {T["text_secondary"]};
    font-weight: 400;
}}
QPushButton[class="secondary"]:hover {{
    background-color: {T["surface_muted"]};
    color: {T["text_primary"]};
    border-color: {T["border_strong"]};
}}
QPushButton[class="secondary"]:disabled {{
    background-color: transparent;
    color: {T["text_muted"]};
}}
QPushButton[class="tag-chip"] {{
    background-color: transparent;
    border: 1px solid {T["border_soft"]};
    color: {T["text_muted"]};
    border-radius: 10px;
    font-size: 11px;
    font-weight: 400;
    min-height: 22px;
    max-height: 22px;
    padding: 0 8px;
}}
QPushButton[class="tag-chip"]:hover {{
    background-color: {T["surface_muted"]};
    border-color: {T["border_strong"]};
    color: {T["text_primary"]};
}}
/* Setas de paginação: quadradas e discretas, sem competir com as ações */
QPushButton[class="pager"] {{
    background-color: transparent;
    border: 1px solid {T["border_soft"]};
    color: {T["text_secondary"]};
    font-weight: 400;
    font-size: 14px;
    min-height: 26px;
    max-height: 26px;
    padding: 0;
}}
QPushButton[class="pager"]:hover:enabled {{
    background-color: {T["surface_muted"]};
    border-color: {T["border_strong"]};
    color: {T["text_primary"]};
}}
QPushButton[class="pager"]:disabled {{
    background-color: transparent;
    border-color: {T["surface_muted"]};
    color: {T["surface_muted"]};
}}

/* ── Toolbar ──────────────────────────────────────────────── */
QToolBar {{
    background-color: {T["surface_panel"]};
    border-right: 1px solid {T["border_soft"]};
    spacing: 2px;
    padding: 6px 4px;
}}
QToolBar::separator {{
    background-color: {T["border_soft"]};
    width: 1px;
    margin: 4px 8px;
}}
QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: {T["radius_sm"]}px;
    color: {T["text_secondary"]};
    min-width: 38px;
    min-height: 38px;
    padding: 4px;
}}
QToolButton:hover {{
    background-color: {T["surface_muted"]};
    color: {T["text_primary"]};
}}
QToolButton:checked {{
    background-color: {T["accent"]};
    color: {T["on_accent"]};
}}
QToolButton:pressed {{
    background-color: {T["accent_hover"]};
    color: {T["on_accent"]};
}}

/* ── Options bar (acima do canvas) ───────────────────────── */
#OptionsBar {{
    background-color: {T["surface_panel"]};
    border-bottom: 1px solid {T["border_soft"]};
    padding: 4px 8px;
}}
#OptionsBar QLabel {{
    color: {T["text_muted"]};
    font-size: 11px;
}}
#OptionsBar QComboBox {{
    min-height: 26px;
    font-size: 12px;
}}
#OptionsBar QLineEdit {{
    min-height: 26px;
    font-size: 12px;
    max-width: 80px;
}}
#OptionsBar QPushButton {{
    min-height: 26px;
    font-size: 12px;
    padding: 0 8px;
}}

/* ── Campo de página da busca online (M16) ───────────────── */
#PageJumpField {{
    background-color: transparent;
    font-size: 11px;
    color: {T["text_secondary"]};
    min-height: 24px;
    max-height: 26px;
    padding: 0 4px;
}}
#PageJumpField:disabled {{
    color: {T["text_muted"]};
    border-color: {T["surface_muted"]};
}}
#PageJumpField::up-button, #PageJumpField::down-button {{
    width: 0px;
    border: none;
    image: none;
}}
#PageJumpField::up-arrow, #PageJumpField::down-arrow {{
    width: 0px;
    height: 0px;
    image: none;
}}

/* ── Indicador de zoom do canvas (M8) ────────────────────── */
#CanvasZoomLabel {{
    background-color: {T["surface_panel"]};
    border: 1px solid {T["border_soft"]};
    border-radius: {T["radius_sm"]}px;
    color: {T["text_secondary"]};
    font-size: 11px;
    padding: 2px 8px;
}}

/* ── Indicador de carregamento do canvas (M4) ────────────── */
#CanvasLoadingLabel {{
    background-color: {T["surface_elevated"]};
    border: 1px solid {T["border_strong"]};
    border-radius: {T["radius_md"]}px;
    color: {T["text_primary"]};
    font-size: 12px;
    padding: 6px 14px;
}}

/* ── Tabs ─────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {T["border_soft"]};
    border-radius: {T["radius_md"]}px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {T["surface_muted"]};
    border: 1px solid {T["border_soft"]};
    min-height: 30px;
    padding: 0 14px;
    margin-right: 4px;
    border-top-left-radius: {T["radius_sm"]}px;
    border-top-right-radius: {T["radius_sm"]}px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background-color: {T["accent"]};
    color: {T["on_accent"]};
}}

/* ── Misc ─────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QStatusBar {{
    background-color: {T["surface_panel"]};
    border-top: 1px solid {T["border_soft"]};
    font-size: 11px;
    color: {T["text_muted"]};
}}
QSplitter::handle {{
    background-color: {T["border_soft"]};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* ── Foco de teclado ──────────────────────────────────────── */
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {{
    border: 1px solid {T["accent"]};
}}

/* ── Spin boxes (diálogo de configurações) ───────────────── */
QSpinBox {{
    background-color: {T["surface_muted"]};
    border: 1px solid {T["border_soft"]};
    border-radius: {T["radius_sm"]}px;
    padding: 3px 8px;
    min-height: 26px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {T["surface_elevated"]};
    border: none;
    width: 18px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {T["border_soft"]};
}}
QSpinBox::up-arrow {{
    image: url({chevron_up});
    width: 9px;
    height: 6px;
}}
QSpinBox::down-arrow {{
    image: url({chevron_down});
    width: 9px;
    height: 6px;
}}

/* ── Slider (aba IA) ──────────────────────────────────────── */
QSlider::groove:horizontal {{
    background-color: {T["surface_muted"]};
    height: 4px;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background-color: {T["accent"]};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background-color: {T["text_primary"]};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background-color: {T["accent"]};
}}

/* ── Barra de progresso ───────────────────────────────────── */
QProgressBar {{
    background-color: {T["surface_muted"]};
    border: none;
    border-radius: {T["radius_sm"]}px;
    height: 8px;
    text-align: center;
    color: {T["text_secondary"]};
}}
QProgressBar::chunk {{
    background-color: {T["accent"]};
    border-radius: {T["radius_sm"]}px;
}}

/* ── Seleção de itens (grade Danbooru e listas) ───────────── */
QListWidget::item {{
    border: 1px solid transparent;
    border-radius: {T["radius_sm"]}px;
    padding: 2px;
    color: {T["text_secondary"]};
}}
QListWidget::item:hover {{
    background-color: {T["surface_elevated"]};
}}
QListWidget::item:selected {{
    background-color: {T["surface_elevated"]};
    border: 1px solid {T["accent"]};
    color: {T["text_primary"]};
}}

/* ── Scrollbars ───────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {T["surface_muted"]};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {T["border_strong"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {T["surface_muted"]};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {T["border_strong"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
    border: none;
    background: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}

/* ── Tooltips ─────────────────────────────────────────────── */
QToolTip {{
    background-color: {T["surface_elevated"]};
    border: 1px solid {T["border_soft"]};
    border-radius: {T["radius_sm"]}px;
    color: {T["text_primary"]};
    padding: 5px 8px;
    font-size: 11px;
}}

/* ── Diálogos e menus ─────────────────────────────────────── */
QMessageBox QPushButton, QDialogButtonBox QPushButton {{
    min-width: 88px;
}}
QMenu {{
    background-color: {T["surface_panel"]};
    border: 1px solid {T["border_soft"]};
    border-radius: {T["radius_sm"]}px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px 6px 12px;
    border-radius: {T["radius_sm"]}px;
    color: {T["text_secondary"]};
}}
QMenu::item:selected {{
    background-color: {T["accent"]};
    color: {T["on_accent"]};
}}
QMenu::separator {{
    height: 1px;
    background-color: {T["border_soft"]};
    margin: 4px 8px;
}}
"""
