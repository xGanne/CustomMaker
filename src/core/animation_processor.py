from PIL import Image, ImageDraw, ImageColor
import colorsys

class AnimationProcessor:
    @staticmethod
    def generate_rainbow_frames(base_image, total_frames=30, border_width=10):
        """
        Generates a list of frames for a rainbow border animation.
        Returns: list of PIL.Image objects, duration_ms
        MAINTAINS input image size by resizing content to fit inside border.
        """
        frames = []
        width, height = base_image.size
        
        # Ensure we work with RGBA
        if base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')
            
        # Resize base image to fit INSIDE the border (Inset)
        # This prevents the final image from being larger than expected 225x350
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        if inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)
        else:
             content_image = base_image # Should not happen with reasonable sizes
             
        for i in range(total_frames):
            # Calculate hue for this frame (0.0 to 1.0)
            hue = i / total_frames
            # Convert HSV to RGB (Saturation=1.0, Value=1.0)
            rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            # Convert float rgb (0-1) to int (0-255) and Hex
            r, g, b = [int(x * 255) for x in rgb]
            color_hex = '#{:02x}{:02x}{:02x}'.format(r, g, b)
            
            # Create a new frame with this border color
            frame = Image.new('RGBA', (width, height), color_hex)
            
            # Paste the resized content image in the center
            # Position: (border_width, border_width)
            if inner_width > 0 and inner_height > 0:
                frame.paste(content_image, (border_width, border_width), content_image)
            
            frames.append(frame)
            
        return frames, 50 # 50ms per frame = 20fps

    @staticmethod
    def generate_neon_frames(base_image, color_hex, total_frames=30, border_width=10):
        """
        Generates a list of frames for a neon pulsing border animation.
        MAINTAINS input image size.
        """
        frames = []
        width, height = base_image.size
        if base_image.mode != 'RGBA': base_image = base_image.convert('RGBA')
        
        # Resize base image to fit INSIDE
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        if inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)
        else:
             content_image = base_image

        # Convert hex to rgb
        r = int(color_hex[1:3], 16)
        g = int(color_hex[3:5], 16)
        b = int(color_hex[5:7], 16)
        
        for i in range(total_frames):
            # Calculate intensity (sin wave approx)
            # 0.5 to 1.0 intensity
            import math
            intensity = 0.5 + 0.5 * math.sin(2 * math.pi * i / total_frames)
            
            # Adjust color brightness
            nr = int(r * intensity)
            ng = int(g * intensity)
            nb = int(b * intensity)
            current_hex = '#{:02x}{:02x}{:02x}'.format(nr, ng, nb)
            
            frame = Image.new('RGBA', (width, height), current_hex)
            if inner_width > 0 and inner_height > 0:
                frame.paste(content_image, (border_width, border_width), content_image)
            frames.append(frame)
            
        return frames, 50

    @staticmethod
    def generate_marching_ants_frames(base_image, color1="#FFFFFF", color2="#000000", total_frames=20, border_width=10, dash_length=20):
        # Placeholder pending implementation
        return []

    @staticmethod
    def generate_strobe_frames(base_image, total_frames=10, border_width=10):
        frames = []
        width, height = base_image.size
        if base_image.mode != 'RGBA': base_image = base_image.convert('RGBA')
        
        # Resize base image to fit INSIDE
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        if inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)
        else:
             content_image = base_image

        colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF", "#FFFFFF", "#000000"]
        
        for i in range(total_frames):
            color = colors[i % len(colors)]
            frame = Image.new('RGBA', (width, height), color)
            if inner_width > 0 and inner_height > 0:
                frame.paste(content_image, (border_width, border_width), content_image)
            frames.append(frame)
            
        return frames, 100 # Slower strobe

