"""Autoteste sem interface: `CustomMaker.exe --self-test relatorio.txt`.

Verifica o que só quebra no executável empacotado — pool de processos da
exportação (freeze_support), assets embutidos (cascade de rosto), tradução do
Qt e gravação da sessão. Sai com código 0 se tudo passou e 1 caso contrário.
"""
import os
import sys
import tempfile
import traceback


def _check(report, name, fn):
    try:
        detail = fn()
        report.append(f"[OK]    {name}" + (f" — {detail}" if detail else ""))
        return True
    except Exception as exc:  # o autoteste reporta tudo, não para no primeiro erro
        report.append(f"[FALHA] {name} — {exc.__class__.__name__}: {exc}")
        report.append("        " + traceback.format_exc().strip().replace("\n", "\n        "))
        return False


def run_self_test(report_path=None):
    report = [f"CustomMaker autoteste — frozen={getattr(sys, 'frozen', False)}"]
    tmp = tempfile.mkdtemp(prefix="custommaker_selftest_")

    def batch_export():
        from PIL import Image
        from src.config.settings import BORDA_HEIGHT, BORDA_HEX, BORDA_WIDTH
        from src.controllers.batch_controller import BatchController
        from src.core.editor_state import EditorState

        paths = []
        for i in range(4):
            path = os.path.join(tmp, f"src{i}.png")
            Image.new("RGBA", (400 + 50 * i, 600), (50 * i, 90, 160, 255)).save(path)
            paths.append(path)
        state = EditorState(image_list=paths)
        controller = BatchController(editor_state=state, borda_hex=BORDA_HEX)
        try:
            results = []
            for animation in ("Nenhuma", "Rainbow"):
                state.animation_type = animation
                out = os.path.join(tmp, f"out_{animation}")
                os.makedirs(out)
                result = controller.save_all_images(out)
                files = sorted(os.listdir(out))
                if result["errors"] or len(files) != len(paths):
                    raise RuntimeError(f"{animation}: {result['errors']} erro(s), {len(files)} arquivo(s)")
                for name in files:
                    with Image.open(os.path.join(out, name)) as img:
                        if img.size != (BORDA_WIDTH, BORDA_HEIGHT):
                            raise RuntimeError(f"{name} saiu {img.size}")
                results.append(f"{animation}: {len(files)}")
            return "lote com pool de processos: " + ", ".join(results)
        finally:
            controller.shutdown()

    def face_cascade():
        from src.core.image_processor import ImageProcessor
        cascade = ImageProcessor.load_face_cascade()
        if cascade is None or cascade.empty():
            raise RuntimeError("lbpcascade_animeface.xml não carregou (asset não embutido?)")
        return "cascade carregado"

    def qt_translations():
        from src.qt.compat import QApplication
        from src.qt.app import install_qt_translations
        app = QApplication.instance() or QApplication(["self-test"])
        if not install_qt_translations(app):
            raise RuntimeError("qtbase_pt_BR.qm não encontrado (tradução não empacotada)")
        from src.qt.compat import QMessageBox
        box = QMessageBox()
        box.setStandardButtons(QMessageBox.Yes)
        return f"botão Yes = {box.button(QMessageBox.Yes).text()!r}"

    def session_store():
        from src.core.editor_state import EditorState
        from src.core.session_store import SessionStore, apply_session, snapshot_session
        image = os.path.join(tmp, "src0.png")
        store = SessionStore(os.path.join(tmp, "session.json"), os.path.join(tmp, "edits"))
        state = EditorState(image_list=[image])
        state.set_image_state(image, (10, 20), (225, 350))
        store.save(snapshot_session(state, []))
        restored = EditorState()
        apply_session(store.load(), restored)
        if restored.image_states.get(image, {}).get("size") != (225, 350):
            raise RuntimeError("sessão não voltou igual")
        return "sessão gravada e restaurada"

    checks = [
        ("Exportação em lote", batch_export),
        ("Detecção de rosto", face_cascade),
        ("Tradução do Qt", qt_translations),
        ("Sessão", session_store),
    ]
    ok = all([_check(report, name, fn) for name, fn in checks])
    report.append("RESULTADO: " + ("PASSOU" if ok else "FALHOU"))
    text = "\n".join(report) + "\n"
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(text)
    try:
        sys.stdout.write(text)
    except Exception:
        pass  # exe sem console: o relatório vai só para o arquivo
    return ok
