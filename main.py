import multiprocessing
import sys


if __name__ == "__main__":
    # Obrigatório no exe do PyInstaller: sem isto, cada processo do pool de
    # exportação reexecuta o app (abrindo outra janela) e o lote quebra com
    # BrokenProcessPool. Fora do exe é um no-op.
    multiprocessing.freeze_support()
    if "--self-test" in sys.argv:
        # autoteste sem janela (usado pelo CI no exe): --self-test [relatorio.txt]
        from src.self_test import run_self_test
        index = sys.argv.index("--self-test")
        report = sys.argv[index + 1] if len(sys.argv) > index + 1 else None
        raise SystemExit(0 if run_self_test(report) else 1)
    from src.qt.app import main
    raise SystemExit(main())
