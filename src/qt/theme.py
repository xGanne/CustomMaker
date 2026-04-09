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
QGroupBox {{
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_md"]}px;
    margin-top: 12px;
    padding: 14px 12px 12px 12px;
    background-color: {UI_TOKENS["surface_panel"]};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QListWidget {{
    background-color: {UI_TOKENS["surface_muted"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_sm"]}px;
    padding: 4px 10px;
    min-height: 18px;
}}
QPushButton {{
    background-color: {UI_TOKENS["accent"]};
    border: none;
    border-radius: {UI_TOKENS["radius_sm"]}px;
    color: {UI_TOKENS["text_primary"]};
    min-height: 38px;
    padding: 0 12px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {UI_TOKENS["accent_hover"]};
}}
QPushButton:disabled {{
    background-color: {UI_TOKENS["surface_muted"]};
    color: {UI_TOKENS["text_muted"]};
}}
QComboBox {{
    min-height: 34px;
    padding-right: 28px;
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background-color: {UI_TOKENS["surface_panel"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    padding: 4px;
}}
QLineEdit {{
    min-height: 34px;
}}
QListWidget {{
    padding: 8px;
}}
QTabWidget::pane {{
    border: 1px solid {UI_TOKENS["border_soft"]};
    border-radius: {UI_TOKENS["radius_md"]}px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {UI_TOKENS["surface_muted"]};
    border: 1px solid {UI_TOKENS["border_soft"]};
    min-height: 34px;
    padding: 0 16px;
    margin-right: 4px;
    border-top-left-radius: {UI_TOKENS["radius_sm"]}px;
    border-top-right-radius: {UI_TOKENS["radius_sm"]}px;
}}
QTabBar::tab:selected {{
    background-color: {UI_TOKENS["accent"]};
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QStatusBar {{
    background-color: {UI_TOKENS["surface_panel"]};
    border-top: 1px solid {UI_TOKENS["border_soft"]};
}}
"""
