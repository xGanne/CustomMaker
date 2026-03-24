import unittest

from PIL import Image

from src.core.ai_provider import AICapabilities, AIProvider, AIResult


try:
    import google.generativeai  # noqa: F401
    HAS_GENAI = True
except Exception:
    HAS_GENAI = False


if HAS_GENAI:
    from src.core.ai_pipeline import AIPipelineManager


class FakeTextProvider(AIProvider):
    def __init__(self):
        self.last_args = None

    def get_capabilities(self):
        return AICapabilities(text_only=True, image_edit=False)

    def apply(self, image, prompt, options, status_callback=None):
        self.last_args = {"image": image, "prompt": prompt, "options": options}
        return AIResult(kind="text", text="descricao gerada")


@unittest.skipUnless(HAS_GENAI, "google-generativeai not installed")
class TestAIPipeline(unittest.TestCase):
    def test_pipeline_reports_safe_mode(self):
        provider = FakeTextProvider()
        manager = AIPipelineManager(provider=provider)
        messages = []

        manager.load_pipeline(status_callback=messages.append)

        self.assertTrue(messages)
        self.assertIn("modo seguro", messages[0].lower())

    def test_pipeline_forward_prompt_and_strength(self):
        provider = FakeTextProvider()
        manager = AIPipelineManager(provider=provider)

        result = manager.apply_uniform(
            image=Image.new("RGBA", (10, 10), "white"),
            prompt_suffix="cabelo azul",
            strength=0.33,
        )

        self.assertEqual(result.kind, "text")
        self.assertEqual(provider.last_args["prompt"], "cabelo azul")
        self.assertEqual(provider.last_args["options"]["strength"], 0.33)
