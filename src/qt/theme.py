from src.config.settings import UI_TOKENS


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
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QListWidget {{
    background-color: {UI_TOKENS["surface_muted"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
    padding: 3px 8px;
    min-height: 16px;
}}
QComboBox {{
    min-height: 28px;
    padding-right: 24px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
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
"""
