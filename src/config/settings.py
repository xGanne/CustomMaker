import os

from dotenv import load_dotenv

from src.utils.resource_loader import resource_path

# Carrega variaveis de ambiente do arquivo .env
load_dotenv()

# Esquema de cores legado (mantido por compatibilidade)
COLORS = {
    "bg_dark": "#1e1e2e",
    "bg_medium": "#313244",
    "bg_light": "#45475a",
    "accent": "#89b4fa",
    "text": "#cdd6f4",
    "text_dim": "#bac2de",
    "success": "#a6e3a1",
    "warning": "#f9e2af",
    "error": "#f38ba8",
    "danger": "#f38ba8",
}

# Design tokens v1 (Dark Editorial Clean)
UI_TOKENS = {
    "surface_bg": "#141821",
    "surface_panel": "#1B202B",
    "surface_elevated": "#222938",
    "surface_muted": "#2A3244",
    "accent": "#2F8CFF",
    "accent_hover": "#1F6DCC",
    "text_primary": "#E9EEF8",
    "text_secondary": "#A8B3C7",
    "text_muted": "#7B879D",
    "success": "#1FA971",
    "warning": "#E7A83D",
    "error": "#D94B5E",
    "border_soft": "#334056",
    "border_strong": "#4A5A75",
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

# Mapeamento de nomes de borda para exibicao
BORDA_NAMES = {
    ".borda_red": "Red",
    ".borda_blue": "Blue",
    ".borda_green": "Green",
    ".borda_yellow": "Yellow",
    ".borda_purple": "Purple",
    ".borda_orange": "Orange",
    ".borda_white": "White",
    ".borda_black": "Black",
    ".borda_gray": "Gray",
    ".borda_cyan": "Cyan",
    ".borda_magenta": "Magenta",
    ".borda_brown": "Brown",
    ".borda_pink": "Pink",
    ".borda_lime": "Lime",
    ".borda_olive": "Olive",
    ".borda_maroon": "Maroon",
    ".borda_navy": "Navy",
    ".borda_teal": "Teal",
    ".borda_aqua": "Aqua",
    ".borda_silver": "Silver",
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

# Nome do arquivo de configuracao para persistencia
CONFIG_FILE = "custommaker_config.json"

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
CSS_FILE = resource_path("bordas.css")
FACE_CASCADE_FILE = resource_path("lbpcascade_animeface.xml")
