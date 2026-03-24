from dataclasses import dataclass
from typing import Optional

from PIL import Image


@dataclass(frozen=True)
class AICapabilities:
    text_only: bool
    image_edit: bool


@dataclass
class AIResult:
    kind: str  # "image" | "text" | "error"
    image: Optional[Image.Image] = None
    text: Optional[str] = None
    error_message: Optional[str] = None


class AIProvider:
    def get_capabilities(self) -> AICapabilities:
        raise NotImplementedError

    def apply(self, image: Image.Image, prompt: str, options: dict, status_callback=None) -> AIResult:
        raise NotImplementedError
