import os
from dotenv import load_dotenv
from src.utils.resource_loader import resource_path

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Definição do esquema de cores moderno
COLORS = {
    "bg_dark": "#1e1e2e",         # Fundo escuro
    "bg_medium": "#313244",       # Fundo médio para frames
    "bg_light": "#45475a",        # Fundo claro para elementos interativos
    "accent": "#89b4fa",          # Cor de destaque
    "text": "#cdd6f4",            # Texto normal
    "text_dim": "#bac2de",        # Texto menos importante
    "success": "#a6e3a1",         # Verde para sucesso
    "warning": "#f9e2af",         # Amarelo para avisos
    "error": "#f38ba8"            # Vermelho para erros
}

# Mapeamento de nomes de borda para exibição
BORDA_NAMES = {
    '.borda_red': 'Red', '.borda_blue': 'Blue', '.borda_green': 'Green', '.borda_yellow': 'Yellow',
    '.borda_purple': 'Purple', '.borda_orange': 'Orange', '.borda_white': 'White', '.borda_black': 'Black',
    '.borda_gray': 'Gray', '.borda_cyan': 'Cyan', '.borda_magenta': 'Magenta', '.borda_brown': 'Brown',
    '.borda_pink': 'Pink', '.borda_lime': 'Lime', '.borda_olive': 'Olive', '.borda_maroon': 'Maroon',
    '.borda_navy': 'Navy', '.borda_teal': 'Teal', '.borda_aqua': 'Aqua', '.borda_silver': 'Silver'
}

# Códigos hexadecimais das cores de borda
BORDA_HEX = {
    'Red': '#f38ba8', 'Blue': '#89b4fa', 'Green': '#a6e3a1', 'Yellow': '#f9e2af',
    'Purple': '#cba6f7', 'Orange': '#fab387', 'White': '#cdd6f4', 'Black': '#11111b',
    'Gray': '#6c7086', 'Cyan': '#74c7ec', 'Magenta': '#f5c2e7', 'Brown': '#b4637a',
    'Pink': '#f5c2e7', 'Lime': '#a6e3a1', 'Olive': '#a6c288', 'Maroon': '#bf5f82',
    'Navy': '#1e66f5', 'Teal': '#94e2d5', 'Aqua': '#89dceb', 'Silver': '#a6adc8'
}

# Obter o token da API do ImgChest
IMG_CHEST_API_TOKEN = os.getenv('IMG_CHEST_API_TOKEN')

# Nome do arquivo de configuração para persistência
CONFIG_FILE = "custommaker_config.json"

# Configurações de layout
BORDA_WIDTH = 225
BORDA_HEIGHT = 350

# Configurações de upload
UPLOAD_BATCH_SIZE = 10

# Tipos de arquivos de imagem suportados
SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')

# Path to local assets
CSS_FILE = resource_path("bordas.css")
FACE_CASCADE_FILE = resource_path("lbpcascade_animeface.xml")
