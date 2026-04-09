from src.qt.compat import QT_AVAILABLE

if QT_AVAILABLE:
    from src.qt.tabs.ai_tab import AiTab
    from src.qt.tabs.editor_tab import EditorTab
    from src.qt.tabs.online_tab import OnlineTab

    __all__ = ["AiTab", "EditorTab", "OnlineTab"]
else:
    __all__ = []
