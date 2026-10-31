"""Roda só os testes ligados ao que mudou no código.

    python scripts/test_changed.py              # mudanças ainda não commitadas
    python scripts/test_changed.py --since main # + o que mudou desde um ref (ex.: antes de um push)
    python scripts/test_changed.py --list       # só mostra quais testes rodaria
    python scripts/test_changed.py --all        # suíte inteira (o CI já faz isso a cada push)
    python scripts/test_changed.py -- -k zip    # repassa argumentos ao pytest

Um teste é escolhido quando:
  - o próprio arquivo de teste mudou;
  - ele cita o módulo alterado (import, patch("src.x.y..."), from src.x import y);
  - o nome dele combina com o do módulo (src/qt/dialogs/review_dialog.py → test_review.py).
Mudanças em tests/conftest.py ou tests/_qt_helpers.py afetam todos os testes: use --all.
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
# palavras genéricas demais para ligar um módulo a um teste pelo nome
STOPWORDS = {"qt", "src", "core", "dialog", "dialogs", "mixin", "mixins", "tab", "tabs", "widget", "widgets",
             "utils", "config", "controller", "controllers", "main", "window", "init", "image", "images"}
SHARED_TEST_FILES = {"tests/conftest.py", "tests/_qt_helpers.py"}


def _git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(since=None):
    files = set(_git("diff", "--name-only", "HEAD"))
    files |= set(_git("ls-files", "--others", "--exclude-standard"))
    if since:
        files |= set(_git("diff", "--name-only", f"{since}...HEAD"))
    return sorted(f.replace("\\", "/") for f in files if f.endswith(".py"))


def _tokens(name):
    return {t for t in re.split(r"[_\W]+", name.lower()) if t and t not in STOPWORDS}


def select_tests(files):
    """{arquivo de teste: motivo} para os arquivos alterados."""
    test_sources = {}
    for name in sorted(os.listdir(TESTS)):
        if name.startswith("test_") and name.endswith(".py"):
            with open(os.path.join(TESTS, name), encoding="utf-8") as f:
                test_sources[f"tests/{name}"] = f.read()

    selected = {}
    for path in files:
        if path in test_sources:
            selected.setdefault(path, "o teste mudou")
            continue
        if not path.startswith("src/"):
            continue
        dotted = path[:-3].replace("/", ".")
        if dotted.endswith(".__init__"):
            dotted = dotted[: -len(".__init__")]
        package, _, module = dotted.rpartition(".")
        mention = re.compile(
            rf"{re.escape(dotted)}\b|from\s+{re.escape(package)}\s+import\s+[^\n]*\b{re.escape(module)}\b"
        )
        module_tokens = _tokens(module)
        for test_path, source in test_sources.items():
            if mention.search(source):
                selected.setdefault(test_path, f"cita {dotted}")
            elif module_tokens & _tokens(os.path.basename(test_path)[5:-3]):
                selected.setdefault(test_path, f"nome parecido com {module}")
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", help="inclui o que mudou desde este ref (ex.: main, origin/main, HEAD~3)")
    parser.add_argument("--list", action="store_true", help="só lista os testes escolhidos")
    parser.add_argument("--all", action="store_true", help="roda a suíte inteira")
    parser.add_argument("pytest_args", nargs="*", help="argumentos extras para o pytest (depois de --)")
    args = parser.parse_args(argv)

    if args.all:
        targets = ["tests"]
    else:
        files = changed_files(args.since)
        if not files:
            print("Nada mudou (nem desde o ref pedido). Use --since <ref> ou --all.")
            return 0
        print("Arquivos alterados:\n  " + "\n  ".join(files))
        shared = SHARED_TEST_FILES.intersection(files)
        if shared:
            print(f"\nAviso: {', '.join(sorted(shared))} afeta todos os testes; considere --all.")
        selected = select_tests(files)
        if not selected:
            print("\nNenhum teste ligado a essas mudanças.")
            return 0
        print("\nTestes escolhidos:")
        for test_path, reason in sorted(selected.items()):
            print(f"  {test_path}  ({reason})")
        targets = sorted(selected)

    if args.list:
        return 0
    command = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *targets, *args.pytest_args]
    print("\n" + " ".join(command[2:]), flush=True)  # antes da saída do pytest, mesmo redirecionada
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
