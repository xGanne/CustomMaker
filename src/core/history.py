"""Passos do histórico de desfazer/refazer de uma imagem."""
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

from PIL import Image


@dataclass
class Snapshot:
    """Estado de enquadramento (e pixels, se editados) antes de uma ação.

    `image` só é guardada quando há edição de pixels (rotação, IA): gestos de
    enquadramento não mudam os pixels. None = arquivo original. `label` é o
    nome da ação que veio depois deste estado ("Auto fit", "Mover"...).
    """

    image: Optional[Image.Image]
    pos: Tuple[int, int]
    size: Tuple[int, int]
    pixel_edited: bool
    label: str = ""
    timestamp: float = field(default_factory=time.monotonic)

    def shifted(self, dx, dy):
        """Cópia com a posição deslocada (a borda mudou de lugar no canvas)."""
        x, y = self.pos
        return Snapshot(self.image, (x + dx, y + dy), self.size, self.pixel_edited, self.label, self.timestamp)
