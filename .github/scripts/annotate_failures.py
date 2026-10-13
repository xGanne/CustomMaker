"""Transforma as falhas do relatório JUnit do pytest em anotações do GitHub.

As anotações aparecem no resumo da execução (e na API pública), sem precisar
abrir o log completo do job.
"""
import sys
import xml.etree.ElementTree as ET


def _escape(text):
    # anotações têm uma linha só: quebras viram %0A
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def main(report_path, output_path=None):
    try:
        root = ET.parse(report_path).getroot()
    except (OSError, ET.ParseError) as exc:
        # sem relatório = o processo do pytest morreu no meio; o fim da saída
        # mostra o último teste iniciado e o traceback do faulthandler
        tail = ""
        if output_path:
            try:
                with open(output_path, encoding="utf-8", errors="replace") as f:
                    tail = "".join(f.readlines()[-60:])
            except OSError:
                pass
        print(f"::error title=pytest terminou sem relatorio ({exc.__class__.__name__})::{_escape(tail[-3500:])}")
        return
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is None:
                continue
            name = f"{case.get('classname')}.{case.get('name')}"
            detail = (node.get("message") or "") + "\n" + (node.text or "")
            print(f"::error title={kind} em {name}::{_escape(detail.strip()[-3000:])}")


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else "test-report.xml",
        sys.argv[2] if len(sys.argv) > 2 else None,
    )
