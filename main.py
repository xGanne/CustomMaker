import multiprocessing
import sys


if __name__ == "__main__":
    # Obrigatório no exe do PyInstaller: sem isto, cada processo do pool de
    # exportação reexecuta o app (abrindo outra janela) e o lote quebra com
    # BrokenProcessPool. Fora do exe é um no-op.
    multiprocessing.freeze_support()
    if "--update-smoke" in sys.argv and getattr(sys, "frozen", False):
        # usado pelo CI: troca este exe por outro e o reabre com --self-test
        # (--update-smoke novo.exe relatorio.txt)
        from src.core.self_update import apply_update, stage_update
        index = sys.argv.index("--update-smoke")
        staged = stage_update(sys.argv[index + 1], sys.executable)
        ok = apply_update(staged, sys.executable, args=["--self-test", sys.argv[index + 2]])
        raise SystemExit(0 if ok else 1)
    if getattr(sys, "frozen", False):
        # sobras da atualização anterior (.old, download já instalado)
        from src.core.self_update import cleanup_previous_in_background, hold_instance_lock
        from src.version import __version__
        hold_instance_lock()
        cleanup_previous_in_background(__version__)
    if "--batch" in sys.argv:
        # modo linha de comando (sem janela; não importa o Qt): ver src/cli.py
        from src.cli import run_cli
        raise SystemExit(run_cli(sys.argv[1:]))
    if "--self-test" in sys.argv:
        # autoteste sem janela (usado pelo CI no exe): --self-test [relatorio.txt]
        from src.self_test import run_self_test
        index = sys.argv.index("--self-test")
        report = sys.argv[index + 1] if len(sys.argv) > index + 1 else None
        raise SystemExit(0 if run_self_test(report) else 1)
    from src.qt.app import main
    raise SystemExit(main())
