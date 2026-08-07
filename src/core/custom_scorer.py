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

_TARGET_RATIO = BORDA_WIDTH / BORDA_HEIGHT  # ~0.643 (retrato)


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


def metadata_score(post):
    """Pontuação baseada só nos campos já retornados pela busca — sem I/O.

    Maior é melhor. Não tem piso/teto definido; use para ordenar, não para
    comparar contra um limiar absoluto sem calibrar primeiro.
    """
    tags = set((post.get("tag_string") or "").split())
    score = 0.0
    for tag, weight in _TAG_BOOSTS.items():
        if tag in tags:
            score += weight
    for tag, weight in _TAG_PENALTIES.items():
        if tag in tags:
            score -= weight
    score += _aspect_ratio_score(post.get("image_width"), post.get("image_height"))
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
