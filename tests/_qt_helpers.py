"""Utilitários para testes com a janela principal real."""
import time
from unittest.mock import patch


def wait_for_image(app, window, timeout=10.0):
    """Espera a imagem atual estar no canvas, sem tarefas pendentes.

    "Fila vazia" sozinha não basta: um carregamento que termina sem exibir
    (erro, ou trocado por outro) também esvazia a fila — e o teste começava
    com o canvas vazio, só no CI. Devolve "" se pronto, senão um diagnóstico
    para a mensagem do assert.
    """
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if not window.task_runner._tasks and window.image_canvas._base_image is not None:
            return ""
        time.sleep(0.01)
    return (
        f"imagem não carregou: atual={window.current_path} "
        f"tarefas={list(window.task_runner._tasks)} "
        f"status={window.statusBar().currentMessage()!r}"
    )


def dispose_window(app, window, timeout=5.0):
    """Encerra uma QtMainWindow de teste por completo.

    Só `deleteLater()` deixava tasks em segundo plano vivas: depois que a pasta
    temporária do teste era apagada, um carregamento falhava e mexia na
    interface de uma janela já destruída, corrompendo o heap num teste
    seguinte (crash 0xc0000374 no CI). Aqui as tasks são canceladas e
    aguardadas, os pools de miniatura param e a janela é fechada e destruída.
    Registre esta limpeza DEPOIS da que apaga a pasta temporária (addCleanup
    roda em ordem inversa).
    """
    from src.qt.compat import QMessageBox

    try:
        window.editor_state.image_dirty.clear()
        window.app_config.set("confirm_exit_with_unexported", False)
        window.task_runner.cancel_all()
        end = time.monotonic() + timeout
        while window.task_runner.running_task_ids() and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)
        window.image_list_panel._executor.shutdown(wait=True)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            window.close()
        app.processEvents()
        window.deleteLater()
        app.processEvents()
    except RuntimeError:
        pass  # objeto C++ já destruído
