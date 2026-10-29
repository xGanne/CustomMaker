"""Registro único de comandos do app: paleta (Ctrl+K) e atalhos usam a mesma lista.

Sem Qt neste módulo — a busca é pura e testável isoladamente.
"""
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, List, Tuple


@dataclass
class Command:
    id: str
    title: str
    handler: Callable[[], None]
    category: str = ""
    shortcut: str = ""          # exibido na paleta; ver register_shortcut
    keywords: Tuple[str, ...] = ()
    enabled: Callable[[], bool] = field(default=lambda: True)
    register_shortcut: bool = False  # vira QAction da janela (senão só exibição)


def normalize(text):
    """Minúsculas e sem acentos: "Animação" casa com "animacao"."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _is_subsequence(needle, haystack):
    it = iter(haystack)
    return all(char in it for char in needle)


def _token_score(token, command):
    title = normalize(command.title)
    words = title.replace(":", " ").split()
    extra = normalize(" ".join((command.category,) + tuple(command.keywords)))
    if title.startswith(token):
        return 100
    if any(word.startswith(token) for word in words):
        return 80
    if token in title:
        return 60
    if any(word.startswith(token) for word in extra.split()):
        return 50
    if token in extra:
        return 40
    if len(token) >= 3 and _is_subsequence(token, title.replace(" ", "")):
        return 20  # erro de digitação leve: "rnbow" → "Rainbow"
    return 0


class CommandRegistry:
    def __init__(self):
        self._commands = []
        self._providers = []

    def register(self, command):
        self._commands.append(command)
        return command

    def add_provider(self, provider):
        """`provider()` devolve comandos recalculados a cada busca (presets, bordas...)."""
        self._providers.append(provider)

    def all(self) -> List[Command]:
        commands = list(self._commands)
        for provider in self._providers:
            commands.extend(provider())
        return commands

    def get(self, command_id):
        return next((c for c in self.all() if c.id == command_id), None)

    def search(self, query, recent_ids=()):
        commands = self.all()
        recent_rank = {cid: i for i, cid in enumerate(recent_ids)}
        tokens = normalize(query).split()
        if not tokens:
            recent = sorted((c for c in commands if c.id in recent_rank), key=lambda c: recent_rank[c.id])
            rest = sorted((c for c in commands if c.id not in recent_rank), key=lambda c: (c.category, c.title))
            return recent + rest
        scored = []
        for command in commands:
            scores = [_token_score(token, command) for token in tokens]
            if all(scores):
                scored.append((-sum(scores), recent_rank.get(command.id, len(recent_rank)), command.title, command))
        scored.sort(key=lambda item: item[:3])
        return [item[3] for item in scored]
