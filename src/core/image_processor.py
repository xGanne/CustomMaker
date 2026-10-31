import logging
import os
import threading

import cv2
import numpy as np
from PIL import Image, ImageDraw

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH, BORDER_THICKNESS, FACE_CASCADE_FILE


logger = logging.getLogger(__name__)

# O CascadeClassifier do OpenCV não suporta detectMultiScale concorrente na
# mesma instância (assert em LBPEvaluator::setWindow); a detecção roda na GUI
# thread e em workers (carregamento, ajuste em lote, auto-seleção)
_FACE_DETECTION_LOCK = threading.Lock()


def uncovered_regions(image_rect, border_rect):
    """Faixas da borda que a imagem não cobre (sairiam transparentes no export).

    Retângulos (x, y, w, h); lista vazia quando a imagem cobre a borda inteira.
    """
    bx, by, bw, bh = border_rect
    ix, iy, iw, ih = image_rect
    left, top = max(bx, ix), max(by, iy)
    right, bottom = min(bx + bw, ix + iw), min(by + bh, iy + ih)
    if right <= left or bottom <= top:
        return [(bx, by, bw, bh)]  # nada da borda coberto
    regions = []
    if top > by:
        regions.append((bx, by, bw, top - by))
    if bottom < by + bh:
        regions.append((bx, bottom, bw, by + bh - bottom))
    if left > bx:
        regions.append((bx, top, left - bx, bottom - top))
    if right < bx + bw:
        regions.append((right, top, bx + bw - right, bottom - top))
    return regions


class ImageProcessor:
    @staticmethod
    def load_face_cascade():
        """Loads the face cascade classifier."""
        cascade_path = FACE_CASCADE_FILE
        if not os.path.exists(cascade_path):
            logger.warning("%s não encontrado.", cascade_path)
            return None

        try:
            face_cascade = cv2.CascadeClassifier(cascade_path)
            if face_cascade.empty():
                logger.error("Falha ao carregar CascadeClassifier de %s", cascade_path)
                return None
            return face_cascade
        except Exception as exc:
            logger.exception("Não foi possível carregar o classificador OpenCV: %s", exc)
            return None

    @staticmethod
    def resize_image(image, max_width, max_height):
        """Resizes the image maintaining aspect ratio to fit within max_width/height."""
        if image is None:
            return None
        if image.width == 0 or image.height == 0:
            return image
        width_ratio = max_width / image.width
        height_ratio = max_height / image.height
        best_ratio = min(width_ratio, height_ratio)
        new_width = int(image.width * best_ratio)
        new_height = int(image.height * best_ratio)
        new_width = max(1, new_width)
        new_height = max(1, new_height)
        return image.resize((new_width, new_height), Image.LANCZOS)

    @staticmethod
    def crop_image_to_borda(image_to_crop, image_pos_on_canvas, image_current_size, borda_pos):
        """Crops the image to fit the border area."""
        borda_canvas_x, borda_canvas_y = borda_pos
        img_x_canvas, img_y_canvas = image_pos_on_canvas
        img_w, img_h = image_current_size

        crop_rel_x1 = max(0, borda_canvas_x - img_x_canvas)
        crop_rel_y1 = max(0, borda_canvas_y - img_y_canvas)
        crop_rel_x2 = min(img_w, borda_canvas_x + BORDA_WIDTH - img_x_canvas)
        crop_rel_y2 = min(img_h, borda_canvas_y + BORDA_HEIGHT - img_y_canvas)

        if crop_rel_x1 >= crop_rel_x2 or crop_rel_y1 >= crop_rel_y2:
            return Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (0, 0, 0, 0))

        content_to_paste = image_to_crop.crop((crop_rel_x1, crop_rel_y1, crop_rel_x2, crop_rel_y2))
        final_custom_area = Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (0, 0, 0, 0))

        paste_x_on_final = max(0, img_x_canvas - borda_canvas_x)
        paste_y_on_final = max(0, img_y_canvas - borda_canvas_y)

        final_custom_area.paste(content_to_paste, (round(paste_x_on_final), round(paste_y_on_final)))
        return final_custom_area

    @staticmethod
    def render_image_to_borda(original_image, image_pos_on_canvas, image_current_size, borda_pos):
        """
        Renders the visible border area using the same logic as the legacy UI:
        resize first, crop after.

        The previous optimized path was faster but produced positional drift
        versus the editor preview, especially on non-uniform images.
        """
        if original_image is None:
            return Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (0, 0, 0, 0))
        img_w, img_h = image_current_size
        if img_w <= 0 or img_h <= 0:
            return Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (0, 0, 0, 0))
        resized = original_image.resize((int(img_w), int(img_h)), Image.LANCZOS)
        return ImageProcessor.crop_image_to_borda(
            resized,
            image_pos_on_canvas,
            (int(img_w), int(img_h)),
            borda_pos,
        )

    @staticmethod
    def add_borda_to_image(image_content_pil, border_hex_color):
        """Adds a visual border to the PIL image."""
        image_with_border = image_content_pil.copy()
        draw = ImageDraw.Draw(image_with_border)
        draw.rectangle(
            [0, 0, BORDA_WIDTH - 1, BORDA_HEIGHT - 1],
            outline=border_hex_color,
            width=BORDER_THICKNESS,
        )
        return image_with_border

    @staticmethod
    def detect_all_anime_faces(original_image, face_cascade):
        """
        Detects all anime faces in the image using the provided cascade.
        Returns a list of (x, y, w, h) tuples (possibly empty). Used both by
        the single-face fit logic and by the custom-suitability scorer, which
        cares about *how many* faces are present (group shot vs solo).
        """
        if not face_cascade or not original_image:
            return []

        try:
            # A detecção recebe arrays NumPy (não UMat), então o OpenCL não
            # acelera nada aqui — só cobrava ~2s de inicialização na primeira
            # detecção. A flag é por thread no OpenCV 4, por isso fica aqui.
            cv2.ocl.setUseOpenCL(False)
            open_cv_image_rgb = np.array(original_image.convert("RGB"))
            open_cv_image_bgr = cv2.cvtColor(open_cv_image_rgb, cv2.COLOR_RGB2BGR)
            gray_image = cv2.cvtColor(open_cv_image_bgr, cv2.COLOR_BGR2GRAY)
            gray_image = cv2.equalizeHist(gray_image)

            h, w = gray_image.shape
            min_dim = min(h, w)
            min_size_strict = max(60, int(min_dim * 0.15))

            with _FACE_DETECTION_LOCK:
                faces = face_cascade.detectMultiScale(
                    gray_image,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(min_size_strict, min_size_strict),
                )

                if faces is None or len(faces) == 0:
                    min_size_relaxed = max(40, int(min_dim * 0.05))
                    faces = face_cascade.detectMultiScale(
                        gray_image,
                        scaleFactor=1.05,
                        minNeighbors=3,
                        minSize=(min_size_relaxed, min_size_relaxed),
                    )

            if faces is None or len(faces) == 0:
                return []
            return list(faces)
        except Exception as exc:
            logger.warning("Erro de detecção OpenCV: %s", exc)
            return []

    @staticmethod
    def detect_faces_ranked(original_image, face_cascade, overlap=0.3):
        """Rostos do maior para o menor, sem detecções repetidas do mesmo rosto.

        O cascade às vezes devolve caixas sobrepostas para um mesmo rosto; uma
        caixa que cobre mais de `overlap` (IoU) de outra maior é descartada.
        """
        faces = ImageProcessor.detect_all_anime_faces(original_image, face_cascade)
        ranked = sorted((tuple(int(v) for v in f) for f in faces), key=lambda f: f[2] * f[3], reverse=True)
        kept = []
        for face in ranked:
            if all(ImageProcessor._iou(face, other) <= overlap for other in kept):
                kept.append(face)
        return kept

    @staticmethod
    def _iou(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
        iy = max(0, min(ay + ah, by + bh) - max(ay, by))
        inter = ix * iy
        union = aw * ah + bw * bh - inter
        return inter / union if union else 0.0

    @staticmethod
    def detect_anime_face(original_image, face_cascade):
        """
        Detects anime face in the image using the provided cascade.
        Returns (x, y, w, h) of the best (largest) face or None.
        """
        faces = ImageProcessor.detect_all_anime_faces(original_image, face_cascade)
        if not faces:
            return None
        return sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[0]

    @staticmethod
    def calculate_intelligent_frame_pos(original_image, face_rect, borda_pos):
        """
        Calculates the new image size and position to center the face.
        Returns (new_w, new_h, pos_x, pos_y).
        """
        fx, fy, fw, fh = face_rect
        if fh == 0 or fw == 0:
            return None

        target_face_height_ratio = 0.55
        target_face_top_margin_ratio = 0.12

        scale_factor = (target_face_height_ratio * BORDA_HEIGHT) / fh
        new_w = int(original_image.width * scale_factor)
        new_h = int(original_image.height * scale_factor)

        if new_w < 1 or new_h < 1:
            return None

        sfx, sfy, sfw = fx * scale_factor, fy * scale_factor, fw * scale_factor
        bx, by = borda_pos

        pos_x = int(bx + (BORDA_WIDTH / 2) - (sfx + sfw / 2))
        pos_y = int(by + (BORDA_HEIGHT * target_face_top_margin_ratio) - sfy)

        return new_w, new_h, pos_x, pos_y

    @staticmethod
    def suggest_border_color(image):
        """Cor de borda que combina com a imagem, em "#rrggbb".

        Pega o matiz dominante entre os pixels vivos (saturados e não escuros),
        ignorando fundos brancos/cinzas, e devolve uma versão viva e clara dele
        para destacar na borda. Imagem sem cor (P&B) recebe um cinza claro.
        """
        small = image.convert("RGB")
        small.thumbnail((96, 96))
        hsv = np.asarray(small.convert("HSV"), dtype=np.float32).reshape(-1, 3) / 255.0
        small.close()
        hue, sat, val = hsv[:, 0], hsv[:, 1], hsv[:, 2]
        vivid = (sat > 0.25) & (val > 0.25)
        if vivid.sum() < max(20, hsv.shape[0] * 0.02):
            return "#d9dde4"
        # 24 faixas de matiz, cada pixel pesando pela saturação (cores mais
        # vivas decidem mais); a faixa vencedora define o tom da borda
        bins = 24
        hist, edges = np.histogram(hue[vivid], bins=bins, range=(0.0, 1.0), weights=sat[vivid])
        hist = hist + 0.5 * (np.roll(hist, 1) + np.roll(hist, -1))  # matiz é circular
        best = int(np.argmax(hist))
        lo, hi = edges[best], edges[best + 1]
        in_bin = vivid & (hue >= lo) & (hue < hi)
        if not in_bin.any():
            in_bin = vivid
        h = float(np.median(hue[in_bin]))
        s = float(np.clip(np.median(sat[in_bin]) * 1.15, 0.45, 0.85))
        v = float(np.clip(np.median(val[in_bin]) * 1.1, 0.75, 0.95))
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))

    @staticmethod
    def calculate_default_fit(image, borda_pos, mode="auto_fit", face_cascade=None):
        """M11: enquadramento aplicado a imagens ainda não enquadradas.

        `mode` "intelligent" centraliza o rosto quando há cascade e um rosto é
        detectado; em qualquer outro caso cai no auto fit.
        Returns (new_w, new_h, pos_x, pos_y) or None.
        """
        if mode == "intelligent" and face_cascade is not None:
            face = ImageProcessor._detect_face_downscaled(image, face_cascade)
            if face is not None:
                fit = ImageProcessor.calculate_intelligent_frame_pos(image, face, borda_pos)
                if fit:
                    return fit
        return ImageProcessor.calculate_auto_fit_pos(image, borda_pos)

    DEFAULT_FIT_DETECTION_MAX_SIDE = 1000

    @staticmethod
    def _detect_face_downscaled(image, face_cascade):
        """Detecta o rosto numa cópia reduzida e devolve o retângulo na escala
        de `image` — a preview pode chegar a 2400px e a detecção nesse tamanho
        leva segundos, atrasando a primeira exibição da imagem."""
        max_side = ImageProcessor.DEFAULT_FIT_DETECTION_MAX_SIDE
        scale = max(image.width, image.height) / max_side
        if scale <= 1:
            return ImageProcessor.detect_anime_face(image, face_cascade)
        small = image.resize(
            (max(1, round(image.width / scale)), max(1, round(image.height / scale))),
            Image.BILINEAR,
        )
        try:
            face = ImageProcessor.detect_anime_face(small, face_cascade)
        finally:
            small.close()
        if face is None:
            return None
        return tuple(int(round(value * scale)) for value in face)

    @staticmethod
    def calculate_auto_fit_pos(original_image, borda_pos):
        """
        Calculates size and position to fill the border area.
        Returns (new_w, new_h, pos_x, pos_y).
        """
        orig_w, orig_h = original_image.size
        scale_w = BORDA_WIDTH / orig_w
        scale_h = BORDA_HEIGHT / orig_h
        scale_factor = max(scale_w, scale_h)

        new_w = int(orig_w * scale_factor)
        new_h = int(orig_h * scale_factor)

        if new_w < 1 or new_h < 1:
            return None

        bx, by = borda_pos
        pos_x = int(bx + (BORDA_WIDTH - new_w) // 2)
        pos_y = int(by + (BORDA_HEIGHT - new_h) // 2)

        return new_w, new_h, pos_x, pos_y
