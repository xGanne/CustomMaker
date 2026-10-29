"""Configuração comum dos testes."""
import pytest


@pytest.fixture(autouse=True)
def _flush_deferred_qt_deletes():
    """Destrói ao fim de cada teste os objetos Qt marcados com deleteLater().

    Sem um loop de eventos rodando (como nos testes), os deleteLater() de
    janelas, abas e diálogos ficavam acumulados e o Qt os destruía de uma vez,
    mais tarde, no meio de outro teste — com threads e timers de testes
    antigos ainda ligados a eles (crash intermitente em test_session). Aqui a
    destruição acontece num ponto controlado, no teste que criou os objetos.
    """
    yield
    try:
        from src.qt.compat import QT_AVAILABLE
        if not QT_AVAILABLE:
            return
        from PySide6.QtCore import QCoreApplication, QEvent
        if QCoreApplication.instance() is None:
            return
        # ciclos de referência com objetos Qt deixados pelo teste são liberados
        # aqui, na GUI thread — e não pelo coletor rodando por acaso numa thread
        # de trabalho do teste seguinte (destruir QObject fora da thread dele
        # corrompe o heap)
        import gc
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.processEvents()
    except ImportError:
        pass
