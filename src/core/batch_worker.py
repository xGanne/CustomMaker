
import os
from PIL import Image
from src.core.image_processor import ImageProcessor
from src.core.animation_processor import AnimationProcessor
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT

def process_image_task(task_data):
    """
    task_data is a dictionary containing:
    - path: str
    - state: dict {'pos', 'size'}
    - borda_pos: tuple
    - anim_type: str
    - border_color: str (hex)
    - output_format: 'webp' or 'png'
    """
    path = task_data['path']
    state = task_data['state']
    borda_pos = task_data['borda_pos']
    anim_type = task_data['anim_type']
    border_color = task_data['border_color']
    
    output_path = task_data.get('output_path')
    
    try:
        orig = Image.open(path).convert("RGBA")
        resized = orig.resize(state['size'], Image.LANCZOS)
        cropped = ImageProcessor.crop_image_to_borda(resized, state['pos'], state['size'], borda_pos)
        
        frames = []
        duration = 50
        
        if anim_type != "Nenhuma":
            # Animated
            if anim_type == "Rainbow":
                frames, duration = AnimationProcessor.generate_rainbow_frames(cropped, total_frames=40, border_width=10)
            elif anim_type == "Neon Pulsante":
                frames, duration = AnimationProcessor.generate_neon_frames(cropped, border_color, total_frames=40, border_width=10)
            elif anim_type == "Strobe (Pisca)":
                frames, duration = AnimationProcessor.generate_strobe_frames(cropped, total_frames=10, border_width=10)
            else:
                 frames, duration = AnimationProcessor.generate_rainbow_frames(cropped, total_frames=40, border_width=10)
            
            # Enforce dimensions
            final_frames = []
            for f in frames:
                if f.size != (BORDA_WIDTH, BORDA_HEIGHT):
                    f = f.resize((BORDA_WIDTH, BORDA_HEIGHT), Image.LANCZOS)
                final_frames.append(f)
            
            orig.close()
            
            if output_path:
                final_frames[0].save(output_path, save_all=True, append_images=final_frames[1:], loop=0, duration=duration, optimize=True, quality=90)
                return {'status': 'success', 'path': path, 'saved_to': output_path}
            else:
                return {'status': 'success', 'frames': final_frames, 'duration': duration, 'path': path, 'type': 'anim'}
            
        else:
            # Static
            final = ImageProcessor.add_borda_to_image(cropped, border_color)
            orig.close()
            
            if output_path:
                final.save(output_path)
                return {'status': 'success', 'path': path, 'saved_to': output_path}
            else:
                return {'status': 'success', 'image': final, 'path': path, 'type': 'static'}
            
    except Exception as e:
        return {'status': 'error', 'path': path, 'error': str(e)}
