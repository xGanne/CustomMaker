"""
SVG icon renderer using Heroicons v2 outline (MIT License).
https://github.com/tailwindlabs/heroicons
All icons: 24×24 viewBox, stroke-width 1.5, round linecap/linejoin, no fill.
"""
from PySide6.QtSvg import QSvgRenderer

from src.qt.compat import QPainter, QPixmap, Qt

_ICONS: dict[str, str] = {
    "folder-open": (
        '<path stroke-linecap="round" stroke-linejoin="round"'
        ' d="M3.75 9.776c.112-.017.227-.026.344-.026h15.812c.117 0 .232.009.344.026'
        "m-16.5 0a2.25 2.25 0 0 0-1.883 2.542l.857 6a2.25 2.25 0 0 0 2.227 1.932H19.05"
        "a2.25 2.25 0 0 0 2.227-1.932l.857-6a2.25 2.25 0 0 0-1.883-2.542"
        "m-16.5 0V6A2.25 2.25 0 0 1 6 3.75h3.879a1.5 1.5 0 0 1 1.06.44l2.122 2.12"
        'a1.5 1.5 0 0 0 1.06.44H18A2.25 2.25 0 0 1 20.25 9v.776" />'
    ),
    "clipboard": (
        '<path stroke-linecap="round" stroke-linejoin="round"'
        ' d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108'
        "c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08"
        "m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75"
        " 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15"
        "c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08"
        "C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125"
        "v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125"
        'V9.375c0-.621-.504-1.125-1.125-1.125H8.25Z" />'
    ),
    "arrow-uturn-left": (
        '<path stroke-linecap="round" stroke-linejoin="round"'
        ' d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3" />'
    ),
    "arrows-pointing-out": (
        '<path stroke-linecap="round" stroke-linejoin="round"'
        " d=\"M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5"
        "m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9"
        'm5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />'
    ),
    "face-smile": (
        '<path stroke-linecap="round" stroke-linejoin="round"'
        ' d="M15.182 15.182a4.5 4.5 0 0 1-6.364 0M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z'
        "M9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75Z"
        "m-.375 0h.008v.015h-.008V9.75Zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75"
        '.168-.75.375-.75.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Z" />'
    ),
    "eye-dropper": (
        '<path stroke-linecap="round" stroke-linejoin="round"'
        ' d="m15.042 21.672-1.358-5.072m0 0-2.51 2.225.569-9.47 5.227 7.917-3.286-.672Z'
        "m-7.518-.267A8.25 8.25 0 1 1 20.25 10.5"
        'M8.288 14.212A5.25 5.25 0 1 1 17.25 10.5" />'
    ),
    "cog": (
        '<path stroke-linecap="round" stroke-linejoin="round"'
        ' d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87'
        ".108.058.205.12.301.187l1.2-.48a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827"
        "c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827"
        "c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.201-.48"
        "c-.096.065-.193.127-.3.186-.333.184-.582.496-.645.87l-.213 1.281"
        "c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281"
        "c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.301-.186l-1.201.48"
        "a1.125 1.125 0 0 1-1.37-.49l-1.296-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827"
        "c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827"
        "a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.2.48"
        "c.098-.065.194-.127.302-.186.332-.184.582-.496.644-.87l.214-1.28Z"
        ' M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />'
    ),
    "rotate-right": (
        '<path stroke-linecap="round" stroke-linejoin="round"'
        " d=\"M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992"
        "m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7"
        'M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />'
    ),
}


def make_icon(name: str, size: int = 22, color: str = "#A8B3C7"):
    """Render a Heroicons v2 outline icon as QIcon at the given size and color."""
    path_el = _ICONS.get(name)
    flip = False

    if path_el is None and name == "rotate-left":
        path_el = _ICONS["rotate-right"]
        flip = True

    if path_el is None:
        return None

    group_attrs = 'transform="scale(-1,1) translate(-24,0)"' if flip else ""
    svg_bytes = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
        f' fill="none" stroke="{color}" stroke-width="1.5"'
        f' stroke-linecap="round" stroke-linejoin="round"'
        f' width="{size}" height="{size}">'
        f"<g {group_attrs}>{path_el}</g>"
        f"</svg>"
    ).encode()

    renderer = QSvgRenderer(svg_bytes)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    from src.qt.compat import QIcon
    return QIcon(pixmap)
