import logging
import threading
import weakref

from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot


logger = logging.getLogger(__name__)


if QT_AVAILABLE:
    class _TaskRunnable(QRunnable):
        def __init__(self, handle, fn):
            super().__init__()
            # O handle guarda uma referência Python a este runnable. Com
            # autoDelete (padrão), o QThreadPool apagava o objeto C++ ao fim do
            # run() e o coletor do Python o liberava de novo mais tarde, num
            # momento aleatório: access violation intermitente em qualquer
            # ponto do app/testes, mais frequente quanto mais tasks rodavam.
            self.setAutoDelete(False)
            self.handle = handle
            self.fn = fn

        @Slot()
        def run(self):
            try:
                result = self.fn(self.handle.cancel_event, self._emit_progress)
                if self.handle.cancel_event.is_set():
                    self._emit(self.handle.finished, "cancelled", None)
                else:
                    self._emit(self.handle.finished, "done", result)
            except Exception as exc:
                # M21: garante rastro no log mesmo se nenhum slot estiver
                # conectado ao sinal de erro
                logger.exception("Falha na task '%s': %s", self.handle.task_id, exc)
                self._emit(self.handle.finished, "error", exc)

        def _emit_progress(self, *args):
            self._emit(self.handle.progress, *args)

        def _emit(self, signal, *args):
            # a janela pode ter sido fechada (e o handle destruído) enquanto a
            # task terminava: não há mais quem receber o resultado
            try:
                signal.emit(*args)
            except RuntimeError:
                logger.debug("Task '%s' terminou após o fechamento da janela.", self.handle.task_id)


    class _Callbacks:
        """`done`/`error`/`cancelled` de uma task: mesma interface de um sinal
        (connect), mas chamados pelo runner, em ordem, no mesmo slot.

        Eram sinais Qt, cada slot com sua própria chamada enfileirada. O
        runner apagava o handle (deleteLater) no primeiro slot, e a chamada
        ainda pendente dos slots seguintes podia ser descartada junto: o
        carregamento terminava e a imagem nunca aparecia (~1 em 8 numa
        reprodução isolada; falhas que só apareciam no CI).
        """

        def __init__(self):
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

        def emit(self, *args):
            for callback in list(self._callbacks):
                try:
                    callback(*args)
                except Exception:
                    # como num slot Qt: registra e segue para os demais
                    logger.exception("Erro num callback de task")

    class QtTaskHandle(QObject):
        progress = Signal(int, int, str)
        # um único sinal entre threads; o runner repassa para os callbacks
        finished = Signal(str, object)

        def __init__(self, task_id, fn, pool, parent=None):
            super().__init__(parent)
            self.done = _Callbacks()
            self.error = _Callbacks()
            self.cancelled = _Callbacks()
            self.task_id = task_id
            self.fn = fn
            self.pool = pool
            self.cancel_event = threading.Event()
            self._running = False
            self._runnable = None

        def start(self):
            self._running = True
            self._runnable = _TaskRunnable(self, self.fn)
            self.pool.start(self._runnable)

        def cancel(self):
            self.cancel_event.set()

        def is_running(self):
            return self._running

        def mark_finished(self):
            self._running = False


    class QtTaskRunner(QObject):
        def __init__(self, parent=None, thread_pool=None):
            super().__init__(parent)
            self._pool = thread_pool or QThreadPool.globalInstance()
            self._tasks = {}

        def submit(self, task_id, fn):
            existing = self._tasks.get(task_id)
            if existing and existing.is_running():
                return None

            # Filho do runner (dono C++): handle e runnable se referenciam, e esse
            # ciclo só é liberado pelo coletor de ciclos do Python — que roda na
            # thread que estiver alocando, às vezes um worker. Sem dono C++, o
            # coletor destruía o QObject fora da GUI thread (corrupção de heap,
            # crash aleatório). Agora a destruição é sempre o deleteLater abaixo.
            handle = QtTaskHandle(task_id, fn, self._pool, parent=self)
            self._tasks[task_id] = handle
            # referência fraca: as funções abaixo ficam presas às conexões do
            # handle; com referência forte, destruir o handle podia liberar o
            # último ref do runner — que destruía o handle (seu filho) de novo
            runner_ref = weakref.ref(self)

            def finish(kind, payload):
                # fora da fila antes dos callbacks: eles podem consultar
                # has_task ou submeter de novo o mesmo id
                handle.mark_finished()
                runner = runner_ref()
                if runner is not None and runner._tasks.get(task_id) is handle:
                    runner._tasks.pop(task_id, None)
                try:
                    if kind == "done":
                        handle.done.emit(payload)
                    elif kind == "error":
                        handle.error.emit(payload)
                    else:
                        handle.cancelled.emit()
                finally:
                    # só depois de todos os callbacks terem rodado
                    handle.deleteLater()

            handle.finished.connect(finish)

            def start_later():
                runner = runner_ref()
                if runner is None or runner._tasks.get(task_id) is not handle:
                    return
                if handle.cancel_event.is_set():
                    finish("cancelled", None)
                    return
                handle.start()

            QTimer.singleShot(0, start_later)
            return handle

        def cancel(self, task_id):
            handle = self._tasks.get(task_id)
            if not handle:
                return False
            handle.cancel()
            return True

        def is_running(self, task_id):
            handle = self._tasks.get(task_id)
            return bool(handle and handle.is_running())

        def has_task(self, task_id):
            """Submetida e ainda não terminada (rodando ou prestes a começar)."""
            return task_id in self._tasks

        def running_task_ids(self):
            return [task_id for task_id, handle in self._tasks.items() if handle.is_running()]

        def cancel_all(self):
            """Sinaliza cancelamento a todas as tasks (ao fechar o app)."""
            for handle in list(self._tasks.values()):
                handle.cancel()
else:
    class QtTaskRunner:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
