"""Configuração comum dos testes."""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

# Qt sem tela também na máquina local (o CI já usa): as janelas dos testes não
# aparecem nem roubam o foco de outros programas (jogo em tela cheia, navegador).
# Precisa vir antes de qualquer QApplication ser criado.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _export_pool_in_threads(request):
    """Exportação em threads, no próprio processo do pytest.

    O app usa um pool de processos (até 4); cada processo carrega numpy,
    OpenCV e PIL de novo, e a suíte passava de 680 MB de RAM com 7 processos
    Python. Para testar o que o lote produz, threads bastam. Testes do próprio
    pool (spawn, freeze_support do exe) usam `@pytest.mark.real_pool`.
    """
    if request.node.get_closest_marker("real_pool"):
        yield
        return
    from src.controllers.batch_controller import BatchController
    original = BatchController.executor_factory
    BatchController.executor_factory = ThreadPoolExecutor
    try:
        yield
    finally:
        BatchController.executor_factory = original


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
