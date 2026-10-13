import multiprocessing

from src.qt.app import main


if __name__ == "__main__":
    # Obrigatório no exe do PyInstaller: sem isto, cada processo do pool de
    # exportação reexecuta o app (abrindo outra janela) e o lote quebra com
    # BrokenProcessPool. Fora do exe é um no-op.
    multiprocessing.freeze_support()
    raise SystemExit(main())
