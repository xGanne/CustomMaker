import io
import os

from PIL import Image

from src.config.settings import BORDER_THICKNESS, BORDA_HEIGHT, BORDA_WIDTH
from src.core.animation_processor import AnimationProcessor
from src.core.image_processor import ImageProcessor


def process_image_task(task_data):
    path = task_data["path"]
    output_path = task_data.get("output_path")
    try:
        cropped = render_custom_crop(task_data)
        try:
            return _process_cropped(cropped, task_data["anim_type"], task_data["border_color"], output_path, path)
        finally:
            cropped.close()
    except Exception as exc:
        return {"status": "error", "path": path, "error": str(exc)}


def render_custom_crop(task_data):
    """Recorte 225x350 que vira a custom (sem borda), pelo caminho da exportação."""
    source_path = task_data.get("source_path") or task_data["path"]
    state = task_data["state"]
    with Image.open(source_path) as source:
        # JPEG pode ser decodificado já reduzido (1/2, 1/4, 1/8). Como o
        # render redimensiona para state["size"], basta decodificar com o
        # dobro disso: 2-4x mais rápido em originais grandes, com diferença
        # média de ~0,15/255 numa ilustração real. Outros formatos ignoram.
        target_w, target_h = state["size"]
        source.draft(source.mode, (int(target_w) * 2, int(target_h) * 2))
        orig = source.convert("RGBA")
    try:
        return ImageProcessor.render_image_to_borda(orig, state["pos"], state["size"], task_data["borda_pos"])
    finally:
        orig.close()


def render_custom_preview(task_data):
    """Custom estática (225x350 com borda) a partir dos dados de uma task.

    Mesmo caminho da exportação (enquadramento, borda individual, imagem
    editada), sem salvar: usado pela revisão em grade. Animações aparecem como
    a borda estática na cor escolhida.
    """
    cropped = render_custom_crop(task_data)
    try:
        return ImageProcessor.add_borda_to_image(cropped, task_data["border_color"])
    finally:
        cropped.close()


def custom_format(anim_type):
    """Formato do arquivo exportado: GIF para animações, PNG para estáticas."""
    return "png" if anim_type == "Nenhuma" else "gif"


def encode_custom(task_data):
    """Bytes exatos que a exportação gravaria, e o formato ("png" | "gif").

    Usa o mesmo caminho de `process_image_task`, só que codificando em memória:
    serve para medir o tamanho de cada custom antes de salvar ou enviar.
    """
    fmt = custom_format(task_data["anim_type"])
    buffer = io.BytesIO()
    cropped = render_custom_crop(task_data)
    try:
        _encode_cropped(cropped, task_data["anim_type"], task_data["border_color"], buffer, fmt)
    finally:
        cropped.close()
    return buffer.getvalue(), fmt


def measure_custom(task_data):
    """Tamanho em bytes da custom exportada (para o pool de processos: só o
    número volta ao processo principal, não os bytes)."""
    path = task_data["path"]
    try:
        data, fmt = encode_custom(task_data)
        return {"status": "success", "path": path, "bytes": len(data), "format": fmt}
    except Exception as exc:
        return {"status": "error", "path": path, "error": str(exc)}


def _process_cropped(cropped, anim_type, border_color, output_path, path):
    if output_path:
        _encode_cropped(cropped, anim_type, border_color, output_path, _format_for_path(output_path))
        return {"status": "success", "path": path, "saved_to": output_path}
    if anim_type == "Nenhuma":
        return {"status": "success", "image": ImageProcessor.add_borda_to_image(cropped, border_color), "path": path, "type": "static"}
    frames, duration = _generate_frames(cropped, anim_type, border_color)
    try:
        final_frames = _resize_frames(frames)
    finally:
        for f in frames:
            if f not in final_frames:
                f.close()
    return {"status": "success", "frames": final_frames, "duration": duration, "path": path, "type": "anim"}


def _format_for_path(output_path):
    """Formato a partir da extensão, como o PIL decidiria ao salvar."""
    ext = os.path.splitext(str(output_path))[1].lower().lstrip(".")
    return {"jpg": "jpeg"}.get(ext, ext)


def _encode_cropped(cropped, anim_type, border_color, target, fmt):
    """Grava a custom em `target` (caminho ou arquivo em memória) no formato `fmt`."""
    if anim_type == "Nenhuma":
        final = ImageProcessor.add_borda_to_image(cropped, border_color)
        try:
            final.save(target, format=fmt.upper())
        finally:
            final.close()
        return
    frames, duration = _generate_frames(cropped, anim_type, border_color)
    try:
        final_frames = _resize_frames(frames)
        try:
            _save_frames(final_frames, target, duration, fmt)
        finally:
            for f in final_frames:
                f.close()
    finally:
        for f in frames:
            f.close()


def _generate_frames(cropped, anim_type, border_color):
    # F13: gera a borda como overlay (centro transparente) e compõe sobre o
    # conteúdo em tamanho original — mesmo resultado visual do preview e do
    # caminho estático, sem o resize não proporcional para dentro da borda.
    size = cropped.size
    dispatch = {
        "Rainbow": lambda: AnimationProcessor.generate_rainbow_frames(size, total_frames=40, border_width=BORDER_THICKNESS, overlay_only=True),
        "Neon Pulsante": lambda: AnimationProcessor.generate_neon_frames(size, border_color, total_frames=40, border_width=BORDER_THICKNESS, overlay_only=True),
        "Strobe (Pisca)": lambda: AnimationProcessor.generate_strobe_frames(size, total_frames=10, border_width=BORDER_THICKNESS, overlay_only=True),
        "Glitch": lambda: AnimationProcessor.generate_glitch_frames(size, total_frames=20, border_width=BORDER_THICKNESS, overlay_only=True),
        "Spin": lambda: AnimationProcessor.generate_spin_frames(size, border_color, total_frames=30, border_width=BORDER_THICKNESS, overlay_only=True),
        "Flow": lambda: AnimationProcessor.generate_flow_frames(size, border_color, total_frames=30, border_width=BORDER_THICKNESS, overlay_only=True),
    }
    fn = dispatch.get(anim_type) or dispatch["Rainbow"]
    overlays, duration = fn()

    base = cropped if cropped.mode == "RGBA" else cropped.convert("RGBA")
    frames = []
    try:
        for overlay in overlays:
            frame = base.copy()
            frame.alpha_composite(overlay)
            frames.append(frame)
    finally:
        for overlay in overlays:
            overlay.close()
        if base is not cropped:
            base.close()
    return frames, duration


def _resize_frames(frames):
    result = []
    for f in frames:
        if f.size != (BORDA_WIDTH, BORDA_HEIGHT):
            resized = f.resize((BORDA_WIDTH, BORDA_HEIGHT), Image.LANCZOS)
            result.append(resized)
        else:
            result.append(f)
    return result


def _save_frames(final_frames, target, duration, fmt):
    if fmt == "gif":
        gif_frames = [frame.convert("P", palette=Image.ADAPTIVE) for frame in final_frames]
        try:
            gif_frames[0].save(
                target,
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
            target,
            format=fmt.upper(),
            save_all=True,
            append_images=final_frames[1:],
            loop=0,
            duration=duration,
            optimize=True,
            quality=90,
        )
