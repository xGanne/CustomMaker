"""
custom_scorer — heurística de "isso daria um bom custom?" para resultados do Danbooru.

Dois níveis, pensados para serem baratos primeiro e caros depois:

  • metadata_score(post)   — só olha os campos que a busca já retorna
                              (tags, proporção, score/favoritos). Sem I/O.
  • visual_score(image, face_cascade) — roda o mesmo detector de rosto usado
                              no "Ajuste Inteligente" sobre a imagem baixada.
                              Só deve ser chamado para o shortlist do passo
                              anterior, já que exige download.

A pontuação é uma heurística, não um classificador treinado — o objetivo é
priorizar candidatos plausíveis para revisão humana, não decidir sozinha.

Conteúdo explícito: a classificação (`rating`) do Danbooru é feita por pessoas
e vem em todo post — é mais confiável para arte de anime que um modelo local.
Questionável/explícito nunca entra no Auto (`is_auto_eligible`); dentro do
permitido, tags sugestivas pesam contra (`DEFAULT_AVOID_TAGS`, editável).
"""
import math

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH
from src.core.image_processor import ImageProcessor


# Tags que indicam um enquadramento amigável para custom (retrato de um
# personagem só). Pesos moderados — nenhuma tag isolada deve dominar o score.
_TAG_BOOSTS = {
    "solo": 3.0,
    "solo_focus": 2.0,
    "1girl": 1.5,
    "1boy": 1.5,
    "1other": 1.0,
    "upper_body": 2.0,
    "portrait": 2.0,
    "close-up": 1.5,
    "close_up": 1.5,
    "looking_at_viewer": 0.5,
}

# Tags que indicam algo ruim para recorte em retrato: quadrinho paginado,
# grupo, rosto ausente/oculto, marca d'água.
_TAG_PENALTIES = {
    "comic": 5.0,
    "4koma": 5.0,
    "manga": 4.0,
    "multiple_girls": 3.0,
    "multiple_boys": 3.0,
    "multiple_others": 3.0,
    "monochrome": 1.5,
    "greyscale": 1.5,
    "text": 1.5,
    "speech_bubble": 1.5,
    "watermark": 1.0,
    "from_behind": 2.0,
    "faceless": 3.0,
    "full_body": 1.0,
}

# Qualidade da arte: o que costuma render (ou estragar) um custom.
_QUALITY_BOOSTS = {
    "official_art": 1.5,
    "absurdres": 0.8,
    "highres": 0.5,
}
_QUALITY_PENALTIES = {
    "ai-generated": 4.0,
    "photo_(medium)": 3.0,
    "cosplay": 3.0,
    "3d": 2.0,
    "lowres": 2.0,
    "sketch": 1.5,
    "jpeg_artifacts": 1.0,
}

# Classificação do Danbooru: g (geral), s (sensível), q (questionável), e (explícito)
AUTO_RATINGS = frozenset({"g", "s"})
_SENSITIVE_RATING_PENALTY = 1.5

# Tags sugestivas que aparecem mesmo em g/s: cada uma tira pontos (não exclui).
# Editável em Configurações › Danbooru (danbooru_auto_avoid_tags).
DEFAULT_AVOID_TAGS = (
    "cleavage large_breasts huge_breasts underwear panties bra lingerie swimsuit "
    "bikini see-through sideboob underboob ass pantyshot upskirt spread_legs "
    "towel bathing undressing partially_undressed topless nude censored"
)
_AVOID_TAG_PENALTY = 2.5

_TARGET_RATIO = BORDA_WIDTH / BORDA_HEIGHT  # ~0.643 (retrato)


def parse_avoid_tags(text):
    """'a b  c' -> {'a', 'b', 'c'} (minúsculas, sem vazios)."""
    return {tag.lower() for tag in (text or "").split() if tag}


def is_auto_eligible(post):
    """Pode ser pré-selecionado pelo Auto? Só Geral e Sensível — questionável e
    explícito (e post sem classificação) nunca, qualquer que seja o filtro da busca."""
    return (post.get("rating") or "").lower() in AUTO_RATINGS


def _resolution_score(width, height):
    """O recorte de 225x350 precisa de imagem grande: ampliar fica borrado."""
    if not width or not height:
        return 0.0
    if width < BORDA_WIDTH or height < BORDA_HEIGHT:
        return -2.0  # teria que ampliar
    if width < BORDA_WIDTH * 2 or height < BORDA_HEIGHT * 2:
        return -0.5  # pouca margem para enquadrar o rosto
    return 0.0


def _character_score(post):
    """Custom é de um personagem: post sem personagem identificado (ou com
    vários) costuma ser cenário, original ou grupo."""
    characters = (post.get("tag_string_character") or "").split()
    if "tag_string_character" not in post:
        return 0.0  # busca antiga, sem o campo: neutro
    if not characters:
        return -1.0
    if len(characters) > 1:
        return -1.0
    return 1.0


def _aspect_ratio_score(width, height):
    """Recompensa proporções próximas do quadro do custom (225x350)."""
    if not width or not height:
        return 0.0
    ratio = width / height
    diff = abs(ratio - _TARGET_RATIO)
    return max(0.0, 2.0 - diff * 3.0)


def _popularity_score(post):
    """Empurrão pequeno para arte bem avaliada — nunca deve dominar as tags."""
    fav_count = post.get("fav_count") or 0
    score_value = post.get("score") or 0
    try:
        return math.log1p(max(0, fav_count)) * 0.3 + math.log1p(max(0, score_value)) * 0.2
    except (TypeError, ValueError):
        return 0.0


def metadata_score(post, avoid_tags=None):
    """Pontuação baseada só nos campos já retornados pela busca — sem I/O.

    Maior é melhor. Não tem piso/teto definido; use para ordenar, não para
    comparar contra um limiar absoluto sem calibrar primeiro. `avoid_tags`:
    tags sugestivas que pesam contra (padrão: DEFAULT_AVOID_TAGS).
    """
    if avoid_tags is None:
        avoid_tags = parse_avoid_tags(DEFAULT_AVOID_TAGS)
    tags = set((post.get("tag_string") or "").split())
    score = 0.0
    for boosts, sign in ((_TAG_BOOSTS, 1), (_TAG_PENALTIES, -1), (_QUALITY_BOOSTS, 1), (_QUALITY_PENALTIES, -1)):
        for tag, weight in boosts.items():
            if tag in tags:
                score += sign * weight
    score -= _AVOID_TAG_PENALTY * len(tags & avoid_tags)
    if (post.get("rating") or "").lower() == "s":
        score -= _SENSITIVE_RATING_PENALTY
    score += _aspect_ratio_score(post.get("image_width"), post.get("image_height"))
    score += _resolution_score(post.get("image_width"), post.get("image_height"))
    score += _character_score(post)
    score += _popularity_score(post)
    return score


def visual_score(image, face_cascade):
    """Pontuação baseada na imagem baixada (detecção de rosto).

    image: PIL.Image já carregada (preview é suficiente).
    face_cascade: o mesmo classificador de ImageProcessor.load_face_cascade().
    """
    if face_cascade is None or image is None:
        return 0.0

    faces = ImageProcessor.detect_all_anime_faces(image, face_cascade)
    if not faces:
        return -2.0  # provavelmente paisagem/objeto/corpo sem rosto visível
    if len(faces) > 1:
        return -1.5  # múltiplos rostos — grupo, não solo

    _fx, _fy, fw, fh = faces[0]
    frame_area = max(1, image.width * image.height)
    face_area_ratio = (fw * fh) / frame_area

    if face_area_ratio < 0.02:
        return 0.0  # rosto detectado mas minúsculo — enquadramento distante
    if face_area_ratio > 0.5:
        return 1.0  # já é praticamente um close-up
    return 2.5  # proporção rosto/quadro favorável para retrato


def combined_score(post, visual_bonus=0.0):
    """metadata_score(post) + visual_bonus (0.0 se a etapa visual não rodou)."""
    return metadata_score(post) + visual_bonus


def rank_posts_by_metadata(posts):
    """Ordena posts (desc.) só pela pontuação de metadado. Não faz I/O."""
    return sorted(posts, key=metadata_score, reverse=True)
