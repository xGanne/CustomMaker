import math
import random

import colorsys
from PIL import Image, ImageColor, ImageDraw


class AnimationProcessor:
    @staticmethod
    def _clear_center(image, border_width):
        w, h = image.size
        mask = Image.new('L', (w, h), 255)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((border_width, border_width, w - border_width, h - border_width), fill=0)
        image.putalpha(mask)
        return image

    @staticmethod
    def generate_rainbow_frames(base_image, total_frames=30, border_width=10, overlay_only=False):
        frames = []
        if isinstance(base_image, tuple):
            width, height = base_image
        else:
            width, height = base_image.size

        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')

        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)

        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
            content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

        for i in range(total_frames):
            hue = i / total_frames
            rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            r, g, b = [int(x * 255) for x in rgb]

            frame = Image.new('RGBA', (width, height), (r, g, b, 255))

            if overlay_only:
                AnimationProcessor._clear_center(frame, border_width)
            elif content_image:
                frame.paste(content_image, (border_width, border_width), content_image)

            frames.append(frame)

        return frames, 50

    @staticmethod
    def generate_neon_frames(base_image, color_hex, total_frames=30, border_width=10, overlay_only=False):
        frames = []
        if isinstance(base_image, tuple):
            width, height = base_image
        else:
            width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')

        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
            content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

        r, g, b = ImageColor.getrgb(color_hex)[:3]

        for i in range(total_frames):
            intensity = 0.5 + 0.5 * math.sin(2 * math.pi * i / total_frames)
            nr = int(r * intensity)
            ng = int(g * intensity)
            nb = int(b * intensity)

            frame = Image.new('RGBA', (width, height), (nr, ng, nb, 255))
            if overlay_only:
                AnimationProcessor._clear_center(frame, border_width)
            elif content_image:
                frame.paste(content_image, (border_width, border_width), content_image)
            frames.append(frame)

        return frames, 50

    @staticmethod
    def generate_marching_ants_frames(base_image, color1="#FFFFFF", color2="#000000", total_frames=20, border_width=10, dash_length=20):
        return []

    @staticmethod
    def generate_strobe_frames(base_image, total_frames=10, border_width=10, overlay_only=False):
        frames = []
        if isinstance(base_image, tuple):
            width, height = base_image
        else:
            width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')

        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
            content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

        colors = [
            (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255),
            (255, 255, 0, 255), (0, 255, 255, 255), (255, 0, 255, 255),
            (255, 255, 255, 255), (0, 0, 0, 255),
        ]

        for i in range(total_frames):
            frame = Image.new('RGBA', (width, height), colors[i % len(colors)])
            if overlay_only:
                AnimationProcessor._clear_center(frame, border_width)
            elif content_image:
                frame.paste(content_image, (border_width, border_width), content_image)
            frames.append(frame)

        return frames, 100

    @staticmethod
    def generate_glitch_frames(base_image, total_frames=20, border_width=10, overlay_only=False):
        frames = []
        if isinstance(base_image, tuple):
            width, height = base_image
        else:
            width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')

        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
            content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

        glitch_colors = [
            (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255),
            (255, 255, 0, 255), (0, 255, 255, 255), (255, 0, 255, 255),
        ]

        for _ in range(total_frames):
            bg = Image.new('RGBA', (width, height), (20, 20, 20, 255))
            draw = ImageDraw.Draw(bg)
            for _ in range(10):
                x = random.randint(0, width)
                y = random.randint(0, height)
                w = random.randint(5, 50)
                h = random.randint(2, 10)
                draw.rectangle([x, y, x + w, y + h], fill=random.choice(glitch_colors))

            if overlay_only:
                AnimationProcessor._clear_center(bg, border_width)
            elif content_image:
                off_x = random.randint(-2, 2)
                off_y = random.randint(-2, 2)
                bg.paste(content_image, (border_width + off_x, border_width + off_y), content_image)

            frames.append(bg)

        return frames, 50

    @staticmethod
    def generate_spin_frames(base_image, color_hex, total_frames=30, border_width=10, overlay_only=False):
        frames = []
        if isinstance(base_image, tuple):
            width, height = base_image
        else:
            width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')

        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
            content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

        diag = int(math.sqrt(width ** 2 + height ** 2))
        disk_size = diag + 20
        disk = Image.new("RGBA", (disk_size, disk_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(disk)

        center_x = disk_size // 2
        center_y = disk_size // 2
        r, g, b = ImageColor.getrgb(color_hex)[:3]

        steps = 360
        for i in range(steps):
            factor = i / steps
            nr = int(r * factor)
            ng = int(g * factor)
            nb = int(b * factor)
            draw.pieslice([0, 0, disk_size, disk_size], i, i + 1, fill=(nr, ng, nb, 255))

        for i in range(total_frames):
            angle = (360 / total_frames) * i
            rotated_disk = disk.rotate(-angle)

            left = (disk_size - width) // 2
            top = (disk_size - height) // 2
            bg = rotated_disk.crop((left, top, left + width, top + height))

            if overlay_only:
                AnimationProcessor._clear_center(bg, border_width)
            elif content_image:
                bg.paste(content_image, (border_width, border_width), content_image)

            frames.append(bg)

        return frames, 50

    @staticmethod
    def generate_flow_frames(base_image, color_hex, total_frames=30, border_width=10, overlay_only=False):
        frames = []
        if isinstance(base_image, tuple):
            width, height = base_image
        else:
            width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')

        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
            content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

        grad_height = height * 2
        gradient = Image.new("RGBA", (width, grad_height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(gradient)

        r, g, b = ImageColor.getrgb(color_hex)[:3]

        steps = 20
        step_h = grad_height / steps
        for i in range(steps):
            val = 0.5 + 0.5 * math.sin(2 * math.pi * i / steps)
            nr = int(r * val)
            ng = int(g * val)
            nb = int(b * val)
            draw.rectangle([0, i * step_h, width, (i + 1) * step_h], fill=(nr, ng, nb, 255))

        for i in range(total_frames):
            offset = int((grad_height / 2) * (i / total_frames))
            bg = gradient.crop((0, offset, width, offset + height))

            if overlay_only:
                AnimationProcessor._clear_center(bg, border_width)
            elif content_image:
                bg.paste(content_image, (border_width, border_width), content_image)

            frames.append(bg)

        return frames, 60
