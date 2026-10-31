import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest.mock import patch

from PIL import Image

from src.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, run_cli
from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.config_file = os.path.join(self.tmp, "config.json")
        self.presets_file = os.path.join(self.tmp, "presets.json")
        for patcher in (
            patch("src.core.app_config.CONFIG_FILE", self.config_file),
            patch("src.core.preset_manager.PRESETS_FILE", self.presets_file),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.folder = os.path.join(self.tmp, "imgs")
        os.makedirs(self.folder)
        for i in range(3):
            Image.new("RGB", (400 + 40 * i, 600), (60 * i, 90, 160)).save(os.path.join(self.folder, f"i{i}.png"))
        with open(os.path.join(self.folder, "notas.txt"), "w", encoding="utf-8") as f:
            f.write("não é imagem")  # ignorado pela extensão

    def run_cli(self, *args):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = run_cli(["--batch", self.folder, *args])
        return code, buffer.getvalue()

    def test_invalid_arguments_exit_2(self):
        for args in ((), ("--out", "a", "--zip", "b.zip"), ("--out", "a", "--anim", "Strobe (Pisca)"),
                     ("--out", "a", "--border", "Arco-íris"), ("--out", "a", "--preset", "Nao existe"),
                     ("--out", "a", "--workers", "50")):
            with self.subTest(args=args):
                code, output = self.run_cli(*args)
                self.assertEqual(code, EXIT_USAGE, output)
                self.assertIn("ERRO", output)

    def test_out_writes_one_custom_per_image(self):
        out = os.path.join(self.tmp, "saida")
        code, output = self.run_cli("--out", out)
        self.assertEqual(code, EXIT_OK, output)
        names = sorted(os.listdir(out))
        self.assertEqual(names, ["i0_custom.png", "i1_custom.png", "i2_custom.png"])
        for name in names:
            with Image.open(os.path.join(out, name)) as img:
                self.assertEqual(img.size, (BORDA_WIDTH, BORDA_HEIGHT))
        self.assertFalse(os.path.exists(self.config_file))  # nada gravado na config

    def test_zip_and_report(self):
        target, report = os.path.join(self.tmp, "x.zip"), os.path.join(self.tmp, "r.txt")
        code, _ = self.run_cli("--zip", target, "--anim", "Rainbow", "--report", report)
        self.assertEqual(code, EXIT_OK)
        with zipfile.ZipFile(target) as z:
            self.assertEqual(sorted(z.namelist()), ["i0_custom.gif", "i1_custom.gif", "i2_custom.gif"])
        with open(report, encoding="utf-8") as f:
            self.assertIn("Prontas: 3", f.read())

    def test_preset_border_and_style_options(self):
        with open(self.presets_file, "w", encoding="utf-8") as f:
            json.dump({"Rosa": {"border_name": "Cor Personalizada", "border_color": "#ff00aa",
                                "animation_type": "Nenhuma", "border_style": "dupla"}}, f)
        out = os.path.join(self.tmp, "p")
        code, output = self.run_cli("--out", out, "--preset", "Rosa")
        self.assertEqual(code, EXIT_OK, output)
        self.assertIn("estilo dupla", output)
        with Image.open(os.path.join(out, "i0_custom.png")) as img:
            self.assertEqual(img.convert("RGB").getpixel((1, 100)), (255, 0, 170))
        code, output = self.run_cli("--out", out, "--border", "#00ff00", "--style", "simples")
        with Image.open(os.path.join(out, "i0_custom.png")) as img:
            self.assertEqual(img.convert("RGB").getpixel((1, 100)), (0, 255, 0))

    def test_dry_run_writes_nothing(self):
        out = os.path.join(self.tmp, "nada")
        code, output = self.run_cli("--out", out, "--dry-run")
        self.assertEqual(code, EXIT_OK)
        self.assertFalse(os.path.exists(out))
        self.assertIn("i2.png", output)

    def test_empty_folder_fails(self):
        empty = os.path.join(self.tmp, "vazia")
        os.makedirs(empty)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = run_cli(["--batch", empty, "--out", os.path.join(self.tmp, "o")])
        self.assertEqual(code, EXIT_FAILED)

    def test_upload_prints_mudae_commands_within_discord_limit(self):
        class FakeUploader:
            api_token = "token"

            def reload_token(self):
                return True

            def upload_images(self, files, title, progress_callback=None, cancel_event=None):
                return [f"https://imgchest.com/p/{'x' * 60}{i}" for i in range(len(files) * 12)], []

        with patch("src.core.uploader.ImgChestUploader", FakeUploader):
            code, output = self.run_cli("--upload", "Rem (Re:Zero)")
        self.assertEqual(code, EXIT_OK, output)
        commands = output.split("--- comando do Mudae")[1:]
        self.assertGreater(len(commands), 1)  # 36 links não cabem numa mensagem
        for block in commands:
            command = block.split("---\n", 1)[1].strip()
            self.assertTrue(command.startswith("$ai Rem (Re:Zero) $"))
            self.assertLessEqual(len(command), 2000)

    def test_upload_without_token_fails_without_network(self):
        class NoToken:
            api_token = None

            def reload_token(self):
                return False

            def upload_images(self, *a, **k):
                raise AssertionError("não pode chamar a rede")

        with patch("src.core.uploader.ImgChestUploader", NoToken):
            code, output = self.run_cli("--upload", "X")
        self.assertEqual(code, EXIT_FAILED)
        self.assertIn("IMG_CHEST_API_TOKEN", output)

    def test_cli_does_not_import_qt(self):
        code = (
            "import sys; from src.cli import run_cli; "
            f"run_cli(['--batch', r'{self.folder}', '--out', 'x', '--dry-run']); "
            "print('QT' if 'PySide6' in sys.modules else 'SEM QT')"
        )
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, timeout=60, env=env,
                                encoding="utf-8", errors="replace")
        self.assertIn("SEM QT", result.stdout, result.stderr)


if __name__ == "__main__":
    unittest.main()
