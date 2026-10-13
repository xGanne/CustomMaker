"""Sinal emitido por threads de worker que sobrevive ao widget de destino.

Emitir um sinal *do widget* a partir de uma thread de ThreadPoolExecutor é
perigoso: se o widget for destruído com a thread ainda trabalhando (fechar a
galeria expandida no meio do carregamento das miniaturas, fechar a janela),
a emissão acontece num objeto C++ já liberado e corrompe o heap (crash
0xc0000374 / access violation, às vezes bem depois).

A ponte não tem pai e fica viva enquanto alguma thread guardar referência a
ela. O widget conecta um método próprio ao sinal; quando o widget é destruído,
o Qt desfaz a conexão e o resultado que chegar depois é descartado.
"""
from src.qt.compat import QT_AVAILABLE

if QT_AVAILABLE:
    from src.qt.compat import QObject, Signal

    class WorkerSignal(QObject):
        # payload: tupla com os argumentos do resultado
        ready = Signal(object)

        def __init__(self):
            super().__init__()  # sem pai, de propósito
