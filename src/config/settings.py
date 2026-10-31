import os

from dotenv import load_dotenv

from src.utils.resource_loader import app_data_path, resource_path

# Carrega variaveis de ambiente do arquivo .env — primeiro o do diretório de
# dados do app (F19), depois o do cwd como fallback (compatibilidade)
load_dotenv(app_data_path(".env"))
load_dotenv()

_UI_METRICS = {
    "radius_sm": 8,
    "radius_md": 12,
    "radius_lg": 16,
    "space_1": 4,
    "space_2": 8,
    "space_3": 12,
    "space_4": 16,
    "space_5": 20,
    "space_6": 24,
}

# Design tokens por tema (M7). "on_accent" é o texto sobre botões/abas em
# destaque — fica branco nos dois temas, ao contrário de text_primary.
UI_THEMES = {
    "editorial_dark_v1": {
        "surface_bg": "#141821",
        "surface_panel": "#1B202B",
        "surface_elevated": "#222938",
        "surface_muted": "#2A3244",
        "canvas_bg": "#141821",
        "accent": "#2F8CFF",
        "accent_hover": "#1F6DCC",
        "on_accent": "#FFFFFF",
        "text_primary": "#E9EEF8",
        "text_secondary": "#A8B3C7",
        "text_muted": "#7C889E",  # 4.5:1 sobre surface_panel (era #7B879D, 4.499)
        "success": "#1FA971",
        "warning": "#E7A83D",
        "error": "#D94B5E",
        "border_soft": "#334056",
        "border_strong": "#4A5A75",
        **_UI_METRICS,
    },
    "editorial_light_v1": {
        "surface_bg": "#F3F5F9",
        "surface_panel": "#FFFFFF",
        "surface_elevated": "#EDF1F7",
        "surface_muted": "#E2E7EF",
        # canvas levemente mais escuro que os painéis: a borda branca e
        # imagens claras continuam visíveis
        "canvas_bg": "#D5DBE4",
        "accent": "#1F6FE0",
        "accent_hover": "#1959B5",
        "on_accent": "#FFFFFF",
        "text_primary": "#1A2130",
        "text_secondary": "#465166",
        "text_muted": "#626E83",
        "success": "#137A50",
        "warning": "#A56A12",
        "error": "#C2303F",
        "border_soft": "#CDD5E1",
        "border_strong": "#9AA7BB",
        **_UI_METRICS,
    },
}
DEFAULT_THEME_VARIANT = "editorial_dark_v1"
THEME_LABELS = {
    "editorial_dark_v1": "Escuro",
    "editorial_light_v1": "Claro",
}

# Codigos hexadecimais das cores de borda
BORDA_HEX = {
    "Red": "#f38ba8",
    "Blue": "#89b4fa",
    "Green": "#a6e3a1",
    "Yellow": "#f9e2af",
    "Purple": "#cba6f7",
    "Orange": "#fab387",
    "White": "#cdd6f4",
    "Black": "#11111b",
    "Gray": "#6c7086",
    "Cyan": "#74c7ec",
    "Magenta": "#f5c2e7",
    "Brown": "#b4637a",
    "Pink": "#f5c2e7",
    "Lime": "#a6e3a1",
    "Olive": "#a6c288",
    "Maroon": "#bf5f82",
    "Navy": "#1e66f5",
    "Teal": "#94e2d5",
    "Aqua": "#89dceb",
    "Silver": "#a6adc8",
}

# Obter o token da API do ImgChest
IMG_CHEST_API_TOKEN = os.getenv("IMG_CHEST_API_TOKEN")

# Arquivo de configuracao para persistencia — ancorado no diretório de dados
# do app (raiz do projeto em dev, %LOCALAPPDATA%/CustomMaker no exe) (F19)
CONFIG_FILE = app_data_path("custommaker_config.json")

# Defaults de performance (Otimização Geral V1)
DANBOORU_POOL_CONNECTIONS_DEFAULT = 16
DANBOORU_POOL_MAXSIZE_DEFAULT = 32
DANBOORU_RETRY_TOTAL_DEFAULT = 2
DANBOORU_RETRY_BACKOFF_DEFAULT = 0.35
DANBOORU_TIMEOUT_SEARCH_S_DEFAULT = 10
DANBOORU_TIMEOUT_TAGS_S_DEFAULT = 5
DANBOORU_TIMEOUT_DOWNLOAD_S_DEFAULT = 15
THUMBNAIL_BATCH_SIZE_DEFAULT = 4
THUMBNAIL_BATCH_INTERVAL_MS_DEFAULT = 40
THUMBNAIL_MEMORY_CACHE_MB_DEFAULT = 64
THUMBNAIL_DISK_CACHE_MB_DEFAULT = 512
IMAGE_CACHE_MAX_MB_DEFAULT = 256

# Configuracoes de layout
BORDA_WIDTH = 225
BORDA_HEIGHT = 350
BORDER_THICKNESS = 5

# Configuracoes de upload
UPLOAD_BATCH_SIZE = 10

# Tipos de arquivos de imagem suportados
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")

# Path to local assets
FACE_CASCADE_FILE = resource_path("lbpcascade_animeface.xml")

# animações de borda, na ordem dos seletores da interface
ANIMATION_OPTIONS = [
    "Nenhuma",
    "Rainbow",
    "Neon Pulsante",
    "Strobe (Pisca)",
    "Glitch",
    "Spin",
    "Flow",
]
