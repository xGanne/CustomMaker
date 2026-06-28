import os

from PIL import Image

from src.config.settings import BORDER_THICKNESS, BORDA_HEIGHT, BORDA_WIDTH
from src.core.animation_processor import AnimationProcessor
from src.core.image_processor import ImageProcessor


def process_image_task(task_data):
    path = task_data["path"]
    source_path = task_data.get("source_path") or path
    state = task_data["state"]
    borda_pos = task_data["borda_pos"]
    anim_type = task_data["anim_type"]
    border_color = task_data["border_color"]
    output_path = task_data.get("output_path")

    try:
        with Image.open(source_path) as source:
            orig = source.convert("RGBA")

        try:
            cropped = ImageProcessor.render_image_to_borda(orig, state["pos"], state["size"], borda_pos)
        finally:
            orig.close()

        try:
            return _process_cropped(cropped, anim_type, border_color, output_path, path)
        finally:
            cropped.close()

    except Exception as exc:
        return {"status": "error", "path": path, "error": str(exc)}


def _process_cropped(cropped, anim_type, border_color, output_path, path):
    if anim_type == "Nenhuma":
        final = ImageProcessor.add_borda_to_image(cropped, border_color)
        if output_path:
            final.save(output_path)
            final.close()
            return {"status": "success", "path": path, "saved_to": output_path}
        return {"status": "success", "image": final, "path": path, "type": "static"}

    frames, duration = _generate_frames(cropped, anim_type, border_color)
    try:
        final_frames = _resize_frames(frames)
        try:
            if output_path:
                _save_frames(final_frames, output_path, duration)
                return {"status": "success", "path": path, "saved_to": output_path}
            return {"status": "success", "frames": final_frames, "duration": duration, "path": path, "type": "anim"}
        finally:
            if output_path:
                for f in final_frames:
                    f.close()
    finally:
        for f in frames:
            f.close()


def _generate_frames(cropped, anim_type, border_color):
    dispatch = {
        "Rainbow": lambda: AnimationProcessor.generate_rainbow_frames(cropped, total_frames=40, border_width=BORDER_THICKNESS),
        "Neon Pulsante": lambda: AnimationProcessor.generate_neon_frames(cropped, border_color, total_frames=40, border_width=BORDER_THICKNESS),
        "Strobe (Pisca)": lambda: AnimationProcessor.generate_strobe_frames(cropped, total_frames=10, border_width=BORDER_THICKNESS),
        "Glitch": lambda: AnimationProcessor.generate_glitch_frames(cropped, total_frames=20, border_width=BORDER_THICKNESS),
        "Spin": lambda: AnimationProcessor.generate_spin_frames(cropped, border_color, total_frames=30, border_width=BORDER_THICKNESS),
        "Flow": lambda: AnimationProcessor.generate_flow_frames(cropped, border_color, total_frames=30, border_width=BORDER_THICKNESS),
    }
    fn = dispatch.get(anim_type) or dispatch["Rainbow"]
    return fn()


def _resize_frames(frames):
    result = []
    for f in frames:
        if f.size != (BORDA_WIDTH, BORDA_HEIGHT):
            resized = f.resize((BORDA_WIDTH, BORDA_HEIGHT), Image.LANCZOS)
            result.append(resized)
        else:
            result.append(f)
    return result


def _save_frames(final_frames, output_path, duration):
    if str(output_path).lower().endswith(".gif"):
        gif_frames = [frame.convert("P", palette=Image.ADAPTIVE) for frame in final_frames]
        try:
            gif_frames[0].save(
                output_path,
                format="GIF",
                save_all=True,
                append_images=gif_frames[1:],
                loop=0,
                duration=duration,
                disposal=2,
            )
        finally:
            for f in gif_frames:
                f.close()
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
