import os

from PIL import Image
from src.core.image_processor import ImageProcessor
from src.core.animation_processor import AnimationProcessor
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT, BORDER_THICKNESS

def process_image_task(task_data):
    """
    task_data is a dictionary containing:
    - path: str
    - state: dict {'pos', 'size'}
    - borda_pos: tuple
    - anim_type: str
    - border_color: str (hex)
    - output_format: 'gif' or 'png'
    """
    path = task_data['path']
    source_path = task_data.get('source_path') or path
    state = task_data['state']
    borda_pos = task_data['borda_pos']
    anim_type = task_data['anim_type']
    border_color = task_data['border_color']
    
    output_path = task_data.get('output_path')
    
    try:
        with Image.open(source_path) as source:
            orig = source.convert("RGBA")

        cropped = ImageProcessor.render_image_to_borda(orig, state['pos'], state['size'], borda_pos)
        frames = []
        duration = 50

        if anim_type != "Nenhuma":
            if anim_type == "Rainbow":
                frames, duration = AnimationProcessor.generate_rainbow_frames(cropped, total_frames=40, border_width=BORDER_THICKNESS)
            elif anim_type == "Neon Pulsante":
                frames, duration = AnimationProcessor.generate_neon_frames(cropped, border_color, total_frames=40, border_width=BORDER_THICKNESS)
            elif anim_type == "Strobe (Pisca)":
                frames, duration = AnimationProcessor.generate_strobe_frames(cropped, total_frames=10, border_width=BORDER_THICKNESS)
            elif anim_type == "Glitch":
                frames, duration = AnimationProcessor.generate_glitch_frames(cropped, total_frames=20, border_width=BORDER_THICKNESS)
            elif anim_type == "Spin":
                frames, duration = AnimationProcessor.generate_spin_frames(cropped, border_color, total_frames=30, border_width=BORDER_THICKNESS)
            elif anim_type == "Flow":
                frames, duration = AnimationProcessor.generate_flow_frames(cropped, border_color, total_frames=30, border_width=BORDER_THICKNESS)
            else:
                frames, duration = AnimationProcessor.generate_rainbow_frames(cropped, total_frames=40, border_width=BORDER_THICKNESS)

            final_frames = []
            for f in frames:
                if f.size != (BORDA_WIDTH, BORDA_HEIGHT):
                    f = f.resize((BORDA_WIDTH, BORDA_HEIGHT), Image.LANCZOS)
                final_frames.append(f)

            if output_path:
                if str(output_path).lower().endswith(".gif"):
                    gif_frames = [frame.convert("P", palette=Image.ADAPTIVE) for frame in final_frames]
                    gif_frames[0].save(
                        output_path,
                        format="GIF",
                        save_all=True,
                        append_images=gif_frames[1:],
                        loop=0,
                        duration=duration,
                        disposal=2,
                    )
                else:
                    final_frames[0].save(
                        output_path,
                        save_all=True,
                        append_images=final_frames[1:],
                        loop=0,
                        duration=duration,
                        optimize=True,
                        quality=90,
                    )
                return {'status': 'success', 'path': path, 'saved_to': output_path}
            else:
                return {'status': 'success', 'frames': final_frames, 'duration': duration, 'path': path, 'type': 'anim'}

        else:
            final = ImageProcessor.add_borda_to_image(cropped, border_color)
            if output_path:
                final.save(output_path)
                return {'status': 'success', 'path': path, 'saved_to': output_path}
            else:
                return {'status': 'success', 'image': final, 'path': path, 'type': 'static'}

    except Exception as e:
        return {'status': 'error', 'path': path, 'error': str(e)}
