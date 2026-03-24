import logging
import os
from typing import Optional

import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

from src.core.ai_provider import AICapabilities, AIProvider, AIResult


load_dotenv()
logger = logging.getLogger(__name__)


class GeminiTextOnlyProvider(AIProvider):
    def __init__(self, model_name: str = "models/gemini-1.5-flash"):
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY")
        self._enabled = bool(self.api_key)
        if self._enabled:
            genai.configure(api_key=self.api_key)
        else:
            logger.warning("GEMINI_API_KEY não encontrada. IA ficará indisponível.")

    def get_capabilities(self) -> AICapabilities:
        return AICapabilities(text_only=True, image_edit=False)

    def apply(self, image: Image.Image, prompt: str, options: dict, status_callback=None) -> AIResult:
        if not self._enabled:
            return AIResult(kind="error", error_message="GEMINI_API_KEY não configurada no .env.")

        if status_callback:
            status_callback("Enviando para Gemini...")

        try:
            base_prompt = (
                "You are an expert image stylist. Analyze the image and describe the character wearing "
                "a Flamengo soccer team uniform (red and black horizontal stripes jersey, black shorts, red socks), "
                "keeping the same pose and art style. Return only the visual description."
            )
            merged_prompt = f"{base_prompt} {prompt}".strip()
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content([merged_prompt, image])

            text = (getattr(response, "text", "") or "").strip()
            if not text:
                return AIResult(kind="error", error_message="Resposta vazia da IA.")

            # Safe mode: return text result explicitly; do not pretend we edited the image.
            return AIResult(kind="text", text=text)
        except Exception as exc:
            logger.exception("Falha na chamada Gemini: %s", exc)
            return AIResult(kind="error", error_message=f"Falha ao processar IA: {exc}")


class AIPipelineManager:
    def __init__(self, provider: Optional[AIProvider] = None):
        self.provider = provider or GeminiTextOnlyProvider()

    def get_capabilities(self) -> AICapabilities:
        return self.provider.get_capabilities()

    def load_pipeline(self, status_callback=None):
        if status_callback:
            caps = self.get_capabilities()
            if caps.image_edit:
                status_callback("IA pronta (edição de imagem disponível).")
            elif caps.text_only:
                status_callback("IA pronta em modo seguro (geração de descrição).")
            else:
                status_callback("IA indisponível.")

    def apply_uniform(
        self,
        image: Image.Image,
        prompt_suffix: str = "",
        strength: float = 0.75,
        status_callback=None,
    ) -> AIResult:
        options = {"strength": strength}
        return self.provider.apply(image=image, prompt=prompt_suffix, options=options, status_callback=status_callback)
