"""Transforma as falhas do relatório JUnit do pytest em anotações do GitHub.

As anotações aparecem no resumo da execução (e na API pública), sem precisar
abrir o log completo do job.
"""
import sys
import xml.etree.ElementTree as ET


def main(report_path):
    try:
        root = ET.parse(report_path).getroot()
    except (OSError, ET.ParseError) as exc:
        print(f"::warning::Relatório de testes indisponível: {exc}")
        return
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is None:
                continue
            name = f"{case.get('classname')}.{case.get('name')}"
            detail = (node.get("message") or "") + "\n" + (node.text or "")
            # anotações têm uma linha só: quebras viram %0A
            detail = detail.strip()[-3000:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
            print(f"::error title={kind} em {name}::{detail}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "test-report.xml")
