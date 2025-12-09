import os
import sys
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT, FACE_CASCADE_FILE

class ImageProcessor:
    @staticmethod
    def load_face_cascade():
        """Loads the face cascade classifier."""
        cascade_path = FACE_CASCADE_FILE
        if not os.path.exists(cascade_path):
            print(f"AVISO: {cascade_path} não encontrado.")
            return None
        
        try:
            face_cascade = cv2.CascadeClassifier(cascade_path)
            if face_cascade.empty():
                print(f"ERRO: Falha ao carregar CascadeClassifier de {cascade_path}")
                return None
            return face_cascade
        except Exception as e:
            print(f"ERRO CRÍTICO: Não foi possível carregar o classificador de faces OpenCV: {e}")
            return None

    @staticmethod
    def resize_image(image, max_width, max_height):
        """Resizes the image maintaining aspect ratio to fit within max_width/height."""
        if image is None: return None
        if image.width == 0 or image.height == 0: return image 
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
        # round added to avoid float errors if pos is float
        return final_custom_area

    @staticmethod
    def add_borda_to_image(image_content_pil, border_hex_color):
        """Adds a visual border to the PIL image."""
        image_with_border = image_content_pil.copy()
        draw = ImageDraw.Draw(image_with_border)
        draw.rectangle([0, 0, BORDA_WIDTH - 1, BORDA_HEIGHT - 1], outline=border_hex_color, width=2)
        return image_with_border

    @staticmethod
    def detect_anime_face(original_image, face_cascade):
        """
        Detects anime face in the image using the provided cascade.
        Returns (x, y, w, h) of the best face or None.
        """
        if not face_cascade or not original_image:
            return None
        
        try:
            # Convert PIL to OpenCV (RGB -> BGR)
            open_cv_image_rgb = np.array(original_image.convert('RGB'))
            open_cv_image_bgr = cv2.cvtColor(open_cv_image_rgb, cv2.COLOR_RGB2BGR)
            gray_image = cv2.cvtColor(open_cv_image_bgr, cv2.COLOR_BGR2GRAY)
            
            # 1. Enhance Contrast (Helps with stylized/faint lines)
            gray_image = cv2.equalizeHist(gray_image)
            
            h, w = gray_image.shape
            min_dim = min(h, w)
            
            # --- Pass 1: Strict Mode (Priority) ---
            # Look for LARGE, CLEAR faces (>15% of image). 
            # High threshold (minNeighbors=5) to avoid false positives (like jewels).
            min_size_strict = max(60, int(min_dim * 0.15))
            
            faces = face_cascade.detectMultiScale(
                gray_image, 
                scaleFactor=1.1, 
                minNeighbors=5, 
                minSize=(min_size_strict, min_size_strict)
            )
            
            # --- Pass 2: High Sensitivity Mode (Fallback) ---
            # If no big face found (maybe tilted, occluded, or small), look harder.
            # Smaller size (>5%) and lower threshold, but higher resolution scan (scaleFactor=1.05).
            if faces is None or len(faces) == 0:
                min_size_relaxed = max(40, int(min_dim * 0.05))
                faces = face_cascade.detectMultiScale(
                    gray_image, 
                    scaleFactor=1.05, 
                    minNeighbors=3, 
                    minSize=(min_size_relaxed, min_size_relaxed)
                )

            if len(faces) == 0:
                return None
                
            # Pick largest/best face (Width * Height)
            best_face = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)[0]
            return best_face
        except Exception as e:
            print(f"Erro de Detecção OpenCV: {e}")
            return None

    @staticmethod
    def calculate_intelligent_frame_pos(original_image, face_rect, borda_pos):
        """
        Calculates the new image size and position to center the face.
        Returns (new_w, new_h, pos_x, pos_y).
        """
        fx, fy, fw, fh = face_rect
        if fh == 0 or fw == 0: return None
        
        target_face_height_ratio = 0.55
        target_face_top_margin_ratio = 0.12
        
        scale_factor = (target_face_height_ratio * BORDA_HEIGHT) / fh
        new_w = int(original_image.width * scale_factor)
        new_h = int(original_image.height * scale_factor)
        
        if new_w < 1 or new_h < 1: return None
        
        sfx, sfy, sfw = fx * scale_factor, fy * scale_factor, fw * scale_factor
        bx, by = borda_pos
        
        pos_x = int(bx + (BORDA_WIDTH / 2) - (sfx + sfw / 2))
        pos_y = int(by + (BORDA_HEIGHT * target_face_top_margin_ratio) - sfy)
        
        return new_w, new_h, pos_x, pos_y

    @staticmethod
    def calculate_auto_fit_pos(original_image, borda_pos):
        """
        Calculates size and position to fill the border area.
        Returns (new_w, new_h, pos_x, pos_y).
        """
        orig_w, orig_h = original_image.size
        # Calculate scale to cover the border area (max of ratios)
        scale_w = BORDA_WIDTH / orig_w
        scale_h = BORDA_HEIGHT / orig_h
        scale_factor = max(scale_w, scale_h)
        
        new_w = int(orig_w * scale_factor)
        new_h = int(orig_h * scale_factor)
        
        if new_w < 1 or new_h < 1: return None
        
        bx, by = borda_pos
        # Center the image relative to border
        pos_x = int(bx + (BORDA_WIDTH - new_w) // 2)
        pos_y = int(by + (BORDA_HEIGHT - new_h) // 2)
        
        return new_w, new_h, pos_x, pos_y
