import logging
import os
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

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
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content([prompt.strip(), image])

            text = (getattr(response, "text", "") or "").strip()
            if not text:
                return AIResult(kind="error", error_message="Resposta vazia da IA.")

            # Safe mode: return text result explicitly; do not pretend we edited the image.
            return AIResult(kind="text", text=text)
        except Exception as exc:
            exc_type = type(exc).__name__
            exc_str = str(exc).lower()
            if "resourceexhausted" in exc_type or "quota" in exc_str or "429" in exc_str:
                msg = "Quota da API Gemini excedida. Aguarde alguns minutos e tente novamente."
            elif "permissiondenied" in exc_type or "403" in exc_str or "permission" in exc_str:
                msg = "Acesso negado pela API Gemini. Verifique se a GEMINI_API_KEY é válida e tem permissão."
            elif "invalidargument" in exc_type or "400" in exc_str:
                msg = "Requisição inválida para o Gemini. A imagem pode ser grande demais ou o prompt inválido."
            else:
                msg = f"Falha ao processar IA: {exc}"
            logger.exception("Falha na chamada Gemini (%s): %s", exc_type, exc)
            return AIResult(kind="error", error_message=msg)


class AIPipelineManager:
    DEFAULT_BASE_PROMPT = (
        "Analyze the image and describe the requested visual edit while preserving the original pose, "
        "composition, character identity, and art style. Return only the visual description."
    )

    def __init__(self, provider: Optional[AIProvider] = None, base_prompt: Optional[str] = None):
        self.provider = provider or GeminiTextOnlyProvider()
        self.base_prompt = (base_prompt or self.DEFAULT_BASE_PROMPT).strip()

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
        merged_prompt = f"{self.base_prompt} {prompt_suffix}".strip()
        return self.provider.apply(image=image, prompt=merged_prompt, options=options, status_callback=status_callback)
