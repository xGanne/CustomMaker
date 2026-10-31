"""Modo linha de comando: gera as customs de uma pasta sem abrir a janela.

    python main.py --batch PASTA --zip saida.zip
    python main.py --batch PASTA --out SAIDA --preset "Anime" --framing intelligent
    python main.py --batch PASTA --upload "Rem (Re:Zero)" --anim Rainbow
    CustomMaker.exe --batch PASTA --out SAIDA --report relatorio.txt

Códigos de saída: 0 tudo ok · 1 parte falhou · 2 argumentos inválidos ·
3 nada pôde ser feito (pasta vazia, sem token para upload...) · 130 cancelado.

Somente leitura em relação ao app: não grava config, sessão nem histórico.
Não importa Qt.
"""
import argparse
import os
import re
import sys
import threading

EXIT_OK, EXIT_PARTIAL, EXIT_USAGE, EXIT_FAILED, EXIT_CANCELLED = 0, 1, 2, 3, 130


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # código 2 com mensagem clara, sem SystemExit no meio
        raise _Usage(message)


def _build_parser():
    from src.config.settings import ANIMATION_OPTIONS
    from src.core.border_styles import BORDER_STYLES

    parser = _Parser(prog="CustomMaker --batch", description="Gera as customs de uma pasta sem abrir a janela.")
    parser.add_argument("--batch", required=True, metavar="PASTA", help="pasta com as imagens (sem subpastas)")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", metavar="PASTA", help="grava as customs nesta pasta")
    destination.add_argument("--zip", metavar="ARQUIVO", help="grava as customs num ZIP")
    destination.add_argument("--upload", metavar="TITULO", help="envia ao ImgChest e imprime os comandos do Mudae")
    parser.add_argument("--preset", metavar="NOME", help="aplica um preset salvo no app")
    parser.add_argument("--framing", choices=("auto_fit", "intelligent"), help="enquadramento das imagens")
    parser.add_argument("--border", metavar="NOME|#RRGGBB", help="cor da borda: nome da lista do app ou hex")
    parser.add_argument("--style", choices=list(BORDER_STYLES), help="estilo da borda (sem animação)")
    parser.add_argument("--anim", choices=ANIMATION_OPTIONS, metavar="TIPO",
                        help="animação: " + ", ".join(ANIMATION_OPTIONS))
    parser.add_argument("--allow-strobe", action="store_true",
                        help="confirma o Strobe (pisca; pode afetar pessoas com fotossensibilidade)")
    parser.add_argument("--workers", type=int, metavar="N", help="processos em paralelo (1-8)")
    parser.add_argument("--report", metavar="ARQUIVO", help="grava o relatório neste arquivo (no exe é a única saída garantida)")
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que seria feito")
    return parser


class _Output:
    """Imprime e guarda as linhas para o relatório."""

    def __init__(self):
        self.lines = []

    def __call__(self, text=""):
        self.lines.append(text)
        try:
            print(text, flush=True)
        except Exception:
            pass  # exe sem console: o relatório guarda tudo

    def save(self, path):
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")


def _apply_options(args, editor_state, out):
    """Preset e opções sobre o estado. Devolve um código de erro ou None."""
    from src.config.settings import BORDA_HEX
    from src.core.preset_manager import PresetManager, apply_preset_to_state

    if args.preset:
        manager = PresetManager()
        data = manager.get_preset(args.preset)
        if data is None:
            names = ", ".join(manager.list_presets()) or "(nenhum preset salvo)"
            out(f"ERRO: preset '{args.preset}' não existe. Presets: {names}")
            return EXIT_USAGE
        rest = apply_preset_to_state(data, editor_state, BORDA_HEX, adjust_paths=list(editor_state.image_list))
        if rest.get("default_framing"):
            editor_state.default_framing = rest["default_framing"]
    if args.framing:
        editor_state.default_framing = args.framing
    if args.border:
        if re.fullmatch(r"#[0-9a-fA-F]{6}", args.border):
            editor_state.selected_borda = "Cor Personalizada"
            editor_state.custom_borda_hex = args.border
        elif args.border in BORDA_HEX:
            editor_state.selected_borda = args.border
        else:
            out(f"ERRO: borda '{args.border}' desconhecida. Use #RRGGBB ou: {', '.join(sorted(BORDA_HEX))}")
            return EXIT_USAGE
    if args.style:
        editor_state.border_style = args.style
    if args.anim:
        editor_state.animation_type = args.anim
    if editor_state.animation_type == "Strobe (Pisca)" and not args.allow_strobe:
        out("ERRO: o Strobe pisca e pode afetar pessoas com fotossensibilidade. Use --allow-strobe para confirmar.")
        return EXIT_USAGE
    return None


def attach_parent_console():
    """No exe (sem console), mostra a saída no terminal que o chamou, se houver.

    O exe é um app gráfico: o prompt pode voltar antes do fim — em scripts, use
    `start /wait CustomMaker.exe --batch ...` e o --report.
    """
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):  # -1: console do processo pai
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
    except Exception:
        pass  # sem terminal (duplo clique, agendador): fica só o --report


def run_cli(argv):
    attach_parent_console()
    out = _Output()
    try:
        args = _build_parser().parse_args(argv)
    except _Usage as exc:
        out(f"ERRO: {exc}")
        out("Uso: CustomMaker --batch PASTA (--out PASTA | --zip ARQUIVO | --upload TITULO) [opções]; --help para todas")
        return EXIT_USAGE
    except SystemExit as exc:  # --help
        return int(exc.code or 0)

    try:
        return _run(args, out)
    finally:
        try:
            out.save(args.report)
        except OSError as exc:
            print(f"ERRO: não foi possível gravar o relatório {args.report}: {exc}", file=sys.stderr)


def _run(args, out):
    from src.config.settings import BORDA_HEX
    from src.controllers.batch_controller import BatchController
    from src.core.app_config import AppConfig
    from src.core.editor_state import EditorState
    from src.core.image_files import list_folder_images

    if not os.path.isdir(args.batch):
        out(f"ERRO: a pasta {args.batch} não existe.")
        return EXIT_FAILED
    paths = list_folder_images(args.batch)
    if not paths:
        out(f"ERRO: nenhuma imagem em {args.batch}.")
        return EXIT_FAILED
    if args.workers is not None and not 1 <= args.workers <= 8:
        out("ERRO: --workers deve ficar entre 1 e 8.")
        return EXIT_USAGE

    app_config = AppConfig()  # só leitura: o CLI nunca grava a config
    editor_state = EditorState(image_list=list(paths), borda_pos=(0, 0))
    editor_state.default_framing = app_config.get("default_framing", "auto_fit")
    code = _apply_options(args, editor_state, out)
    if code is not None:
        return code

    destination = args.out or args.zip or f"ImgChest: {args.upload}"
    out(f"{len(paths)} imagem(ns) de {args.batch} → {destination}")
    out(f"borda {editor_state.selected_borda} ({editor_state.custom_borda_hex if editor_state.selected_borda == 'Cor Personalizada' else BORDA_HEX.get(editor_state.selected_borda)}),"
        f" estilo {editor_state.border_style}, animação {editor_state.animation_type},"
        f" enquadramento {editor_state.default_framing}")
    if args.dry_run:
        for path in paths:
            out(f"  {os.path.basename(path)}")
        out("--dry-run: nada foi gravado.")
        return EXIT_OK

    uploader = None
    if args.upload:
        from src.core.env_file import ENV_FILE
        from src.core.uploader import ImgChestUploader
        uploader = ImgChestUploader()
        if not uploader.api_token and not uploader.reload_token():
            out(f"ERRO: token do ImgChest não configurado. Defina IMG_CHEST_API_TOKEN em {ENV_FILE}.")
            return EXIT_FAILED

    config = {"max_workers": args.workers} if args.workers else {"max_workers": app_config.get("max_workers")}
    controller = BatchController(
        editor_state=editor_state, app_config=config, borda_hex=BORDA_HEX, borda_pos=(0, 0), uploader=uploader
    )
    cancel_event = threading.Event()

    def progress(done, total, message):
        if message and message.startswith("Enviando"):
            out(message)
        elif total:
            out(f"[{done}/{total}]")

    try:
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            result = controller.save_all_images(args.out, progress_callback=progress, cancel_event=cancel_event)
        elif args.zip:
            parent = os.path.dirname(os.path.abspath(args.zip))
            os.makedirs(parent, exist_ok=True)
            result = controller.save_zip(args.zip, progress_callback=progress, cancel_event=cancel_event)
        else:
            result = controller.upload_to_imgchest(args.upload, progress_callback=progress, cancel_event=cancel_event)
    except KeyboardInterrupt:
        cancel_event.set()
        out("Cancelado (Ctrl+C). O que já foi gravado continua no destino.")
        return EXIT_CANCELLED
    except OSError as exc:
        out(f"ERRO: {exc}")
        return EXIT_FAILED
    finally:
        controller.shutdown()

    return _summarize(args, result, out)


def _summarize(args, result, out):
    from src.core.file_sizes import format_bytes, size_summary
    from src.core.mudae import mudae_commands

    skipped = result.get("skipped") or []
    for name in skipped:
        out(f"PULADA {name}: sem enquadramento possível")
    for name, error in result.get("failed") or []:
        out(f"ERRO {name}: {error}")
    if args.upload:
        errors = result.get("errors") or []
        for error in errors:
            out(f"ERRO {error}")
        links = result.get("links") or []
        out(f"Enviadas: {result.get('uploaded', 0)} · links: {len(links)}")
        for index, command in enumerate(mudae_commands(args.upload, links), start=1):
            out(f"--- comando do Mudae {index} ---")
            out(command)
        failed = len(errors) + len(skipped)
        ok = bool(links)
    else:
        failed = int(result.get("errors") or 0) + len(skipped)
        total, largest = size_summary(result.get("sizes") or {})
        done = result.get("processed", 0) - int(result.get("errors") or 0)
        line = f"Prontas: {done} · com erro: {result.get('errors', 0)} · puladas: {len(skipped)}"
        if largest:
            line += f" · {format_bytes(total)} no total"
        out(line)
        out(f"Destino: {args.out or args.zip}")
        ok = done > 0
    if not ok:
        return EXIT_FAILED
    return EXIT_PARTIAL if failed else EXIT_OK
