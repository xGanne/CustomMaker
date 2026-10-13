import logging
import os

from src.config.settings import UI_TOKENS
from src.utils.resource_loader import app_data_path


logger = logging.getLogger(__name__)


def _chevron_icon_url(direction="down"):
    """Gera (uma vez) o chevron de combos/spinboxes como SVG e devolve a URL.

    O truque CSS de "triângulo por bordas" não funciona no Qt — ele desenha um
    retângulo. Um SVG real é o caminho previsível.
    """
    path_d = "M1 1.5 L5 5.5 L9 1.5" if direction == "down" else "M1 5.5 L5 1.5 L9 5.5"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="7" viewBox="0 0 10 7">'
        f'<path d="{path_d}" fill="none" stroke="{UI_TOKENS["text_secondary"]}" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )
    try:
        target_dir = app_data_path(".ui")
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"chevron-{direction}.svg")
        existing = None
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file_obj:
                existing = file_obj.read()
        if existing != svg:
            with open(path, "w", encoding="utf-8") as file_obj:
                file_obj.write(svg)
        return path.replace("\\", "/")
    except OSError as exc:
        logger.debug("Não foi possível gerar o chevron '%s': %s", direction, exc)
        return ""


_CHEVRON_URL = _chevron_icon_url("down")
_CHEVRON_UP_URL = _chevron_icon_url("up")


QT_STYLESHEET = f"""
QWidget {{
    background-color: {UI_TOKENS["surface_bg"]};
    color: {UI_TOKENS["text_primary"]};
    font-size: 13px;
    selection-background-color: {UI_TOKENS["accent"]};
    selection-color: {UI_TOKENS["text_primary"]};
}}
QMainWindow, QDialog {{
    background-color: {UI_TOKENS["surface_bg"]};
}}
/* Labels e checkboxes não devem pintar fundo próprio: dentro de um group box
   o fundo global (mais escuro) aparecia como uma faixa retangular. */
QLabel, QCheckBox, QRadioButton {{
    background: transparent;
}}

/* ── Group boxes ──────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_md"]}px;
    margin-top: 10px;
    padding: 10px 10px 8px 10px;
    background-color: {UI_TOKENS["surface_panel"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.8px;
    color: {UI_TOKENS["text_muted"]};
    text-transform: uppercase;
}}

/* ── Inputs ───────────────────────────────────────────────── */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
    background-color: {UI_TOKENS["surface_muted"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
    padding: 3px 8px;
    min-height: 16px;
}}
/* Listas ficam fora da regra acima de propósito: um `min-height` em QSS
   sobrescreve setMinimumHeight() no código e achatava a grade de resultados. */
QListWidget {{
    background-color: {UI_TOKENS["surface_muted"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
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
    image: url({_CHEVRON_URL});
    width: 10px;
    height: 7px;
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {UI_TOKENS["surface_panel"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
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
    background-color: {UI_TOKENS["accent"]};
    border: none;
    border-radius: {UI_TOKENS["radius_sm"]}px;
    color: {UI_TOKENS["text_primary"]};
    min-height: 30px;
    padding: 0 10px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {UI_TOKENS["accent_hover"]};
}}
QPushButton:disabled {{
    background-color: {UI_TOKENS["surface_muted"]};
    color: {UI_TOKENS["text_muted"]};
}}
QPushButton[class="secondary"] {{
    background-color: transparent;
    border: 1px solid {UI_TOKENS["border_soft"]};
    color: {UI_TOKENS["text_secondary"]};
    font-weight: 400;
}}
QPushButton[class="secondary"]:hover {{
    background-color: {UI_TOKENS["surface_muted"]};
    color: {UI_TOKENS["text_primary"]};
    border-color: {UI_TOKENS["border_strong"]};
}}
QPushButton[class="secondary"]:disabled {{
    background-color: transparent;
    color: {UI_TOKENS["text_muted"]};
}}
QPushButton[class="tag-chip"] {{
    background-color: transparent;
    border: 1px solid {UI_TOKENS["border_soft"]};
    color: {UI_TOKENS["text_muted"]};
    border-radius: 10px;
    font-size: 11px;
    font-weight: 400;
    min-height: 22px;
    max-height: 22px;
    padding: 0 8px;
}}
QPushButton[class="tag-chip"]:hover {{
    background-color: {UI_TOKENS["surface_muted"]};
    border-color: {UI_TOKENS["border_strong"]};
    color: {UI_TOKENS["text_primary"]};
}}
/* Setas de paginação: quadradas e discretas, sem competir com as ações */
QPushButton[class="pager"] {{
    background-color: transparent;
    border: 1px solid {UI_TOKENS["border_soft"]};
    color: {UI_TOKENS["text_secondary"]};
    font-weight: 400;
    font-size: 14px;
    min-height: 26px;
    max-height: 26px;
    padding: 0;
}}
QPushButton[class="pager"]:hover:enabled {{
    background-color: {UI_TOKENS["surface_muted"]};
    border-color: {UI_TOKENS["border_strong"]};
    color: {UI_TOKENS["text_primary"]};
}}
QPushButton[class="pager"]:disabled {{
    background-color: transparent;
    border-color: {UI_TOKENS["surface_muted"]};
    color: {UI_TOKENS["surface_muted"]};
}}

/* ── Toolbar ──────────────────────────────────────────────── */
QToolBar {{
    background-color: {UI_TOKENS["surface_panel"]};
    border-right: 1px solid {UI_TOKENS["border_soft"]};
    spacing: 2px;
    padding: 6px 4px;
}}
QToolBar::separator {{
    background-color: {UI_TOKENS["border_soft"]};
    width: 1px;
    margin: 4px 8px;
}}
QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: {UI_TOKENS["radius_sm"]}px;
    color: {UI_TOKENS["text_secondary"]};
    min-width: 38px;
    min-height: 38px;
    padding: 4px;
}}
QToolButton:hover {{
    background-color: {UI_TOKENS["surface_muted"]};
    color: {UI_TOKENS["text_primary"]};
}}
QToolButton:checked {{
    background-color: {UI_TOKENS["accent"]};
    color: white;
}}
QToolButton:pressed {{
    background-color: {UI_TOKENS["accent_hover"]};
    color: white;
}}

/* ── Options bar (acima do canvas) ───────────────────────── */
#OptionsBar {{
    background-color: {UI_TOKENS["surface_panel"]};
    border-bottom: 1px solid {UI_TOKENS["border_soft"]};
    padding: 4px 8px;
}}
#OptionsBar QLabel {{
    color: {UI_TOKENS["text_muted"]};
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

/* ── Indicador de zoom do canvas (M8) ────────────────────── */
#CanvasZoomLabel {{
    background-color: {UI_TOKENS["surface_panel"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
    color: {UI_TOKENS["text_secondary"]};
    font-size: 11px;
    padding: 2px 8px;
}}

/* ── Indicador de carregamento do canvas (M4) ────────────── */
#CanvasLoadingLabel {{
    background-color: {UI_TOKENS["surface_elevated"]};
    border: 1px solid {UI_TOKENS["border_strong"]};
    border-radius: {UI_TOKENS["radius_md"]}px;
    color: {UI_TOKENS["text_primary"]};
    font-size: 12px;
    padding: 6px 14px;
}}

/* ── Tabs ─────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_md"]}px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {UI_TOKENS["surface_muted"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    min-height: 30px;
    padding: 0 14px;
    margin-right: 4px;
    border-top-left-radius: {UI_TOKENS["radius_sm"]}px;
    border-top-right-radius: {UI_TOKENS["radius_sm"]}px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background-color: {UI_TOKENS["accent"]};
}}

/* ── Misc ─────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QStatusBar {{
    background-color: {UI_TOKENS["surface_panel"]};
    border-top: 1px solid {UI_TOKENS["border_soft"]};
    font-size: 11px;
    color: {UI_TOKENS["text_muted"]};
}}
QSplitter::handle {{
    background-color: {UI_TOKENS["border_soft"]};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* ── Foco de teclado ──────────────────────────────────────── */
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {{
    border: 1px solid {UI_TOKENS["accent"]};
}}

/* ── Spin boxes (diálogo de configurações) ───────────────── */
QSpinBox {{
    background-color: {UI_TOKENS["surface_muted"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
    padding: 3px 8px;
    min-height: 26px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {UI_TOKENS["surface_elevated"]};
    border: none;
    width: 18px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {UI_TOKENS["border_soft"]};
}}
QSpinBox::up-arrow {{
    image: url({_CHEVRON_UP_URL});
    width: 9px;
    height: 6px;
}}
QSpinBox::down-arrow {{
    image: url({_CHEVRON_URL});
    width: 9px;
    height: 6px;
}}

/* ── Slider (aba IA) ──────────────────────────────────────── */
QSlider::groove:horizontal {{
    background-color: {UI_TOKENS["surface_muted"]};
    height: 4px;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background-color: {UI_TOKENS["accent"]};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background-color: {UI_TOKENS["text_primary"]};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background-color: {UI_TOKENS["accent"]};
}}

/* ── Barra de progresso ───────────────────────────────────── */
QProgressBar {{
    background-color: {UI_TOKENS["surface_muted"]};
    border: none;
    border-radius: {UI_TOKENS["radius_sm"]}px;
    height: 8px;
    text-align: center;
    color: {UI_TOKENS["text_secondary"]};
}}
QProgressBar::chunk {{
    background-color: {UI_TOKENS["accent"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
}}

/* ── Seleção de itens (grade Danbooru e listas) ───────────── */
QListWidget::item {{
    border: 1px solid transparent;
    border-radius: {UI_TOKENS["radius_sm"]}px;
    padding: 2px;
    color: {UI_TOKENS["text_secondary"]};
}}
QListWidget::item:hover {{
    background-color: {UI_TOKENS["surface_elevated"]};
}}
QListWidget::item:selected {{
    background-color: {UI_TOKENS["surface_elevated"]};
    border: 1px solid {UI_TOKENS["accent"]};
    color: {UI_TOKENS["text_primary"]};
}}

/* ── Scrollbars ───────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {UI_TOKENS["surface_muted"]};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {UI_TOKENS["border_strong"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background-color: {UI_TOKENS["surface_muted"]};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {UI_TOKENS["border_strong"]};
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
    background-color: {UI_TOKENS["surface_elevated"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
    color: {UI_TOKENS["text_primary"]};
    padding: 5px 8px;
    font-size: 11px;
}}

/* ── Diálogos e menus ─────────────────────────────────────── */
QMessageBox QPushButton, QDialogButtonBox QPushButton {{
    min-width: 88px;
}}
QMenu {{
    background-color: {UI_TOKENS["surface_panel"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px 6px 12px;
    border-radius: {UI_TOKENS["radius_sm"]}px;
    color: {UI_TOKENS["text_secondary"]};
}}
QMenu::item:selected {{
    background-color: {UI_TOKENS["accent"]};
    color: {UI_TOKENS["text_primary"]};
}}
QMenu::separator {{
    height: 1px;
    background-color: {UI_TOKENS["border_soft"]};
    margin: 4px 8px;
}}
"""
