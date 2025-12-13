from PIL import Image, ImageDraw, ImageColor
import colorsys

class AnimationProcessor:
    @staticmethod
    def _clear_center(image, border_width):
        """Helper to make the center of the image transparent."""
        w, h = image.size
        # Create a mask that is opaque everywhere except the center
        mask = Image.new('L', (w, h), 255)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((border_width, border_width, w - border_width, h - border_width), fill=0)
        image.putalpha(mask)
        return image

    @staticmethod
    def generate_rainbow_frames(base_image, total_frames=30, border_width=10, overlay_only=False):
        """
        Generates a list of frames for a rainbow border animation.
        Returns: list of PIL.Image objects, duration_ms
        MAINTAINS input image size by resizing content to fit inside border.
        """
        frames = []
        if isinstance(base_image, tuple): width, height = base_image
        else: width, height = base_image.size
        
        # Ensure we work with RGBA
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA':
            base_image = base_image.convert('RGBA')
            
        # Resize base image to fit INSIDE the border (Inset)
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)
             
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
            
            if overlay_only:
                AnimationProcessor._clear_center(frame, border_width)
            else:
                # Paste the resized content image in the center
                if content_image:
                    frame.paste(content_image, (border_width, border_width), content_image)
            
            frames.append(frame)
            
        return frames, 50
             
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
    def generate_neon_frames(base_image, color_hex, total_frames=30, border_width=10, overlay_only=False):
        """
        Generates a list of frames for a neon pulsing border animation.
        MAINTAINS input image size.
        """
        frames = []
        if isinstance(base_image, tuple): width, height = base_image
        else: width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA': base_image = base_image.convert('RGBA')
        
        content_image = None
        # Resize base image to fit INSIDE
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        if not overlay_only and inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

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
            if overlay_only:
                AnimationProcessor._clear_center(frame, border_width)
            elif content_image:
                frame.paste(content_image, (border_width, border_width), content_image)
            frames.append(frame)
            
        return frames, 50

    @staticmethod
    def generate_marching_ants_frames(base_image, color1="#FFFFFF", color2="#000000", total_frames=20, border_width=10, dash_length=20):
        # Placeholder pending implementation
        return []

    @staticmethod
    def generate_strobe_frames(base_image, total_frames=10, border_width=10, overlay_only=False):
        frames = []
        if isinstance(base_image, tuple): width, height = base_image
        else: width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA': base_image = base_image.convert('RGBA')
        
        content_image = None
        # Resize base image to fit INSIDE
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        if not overlay_only and inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

        colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF", "#FFFFFF", "#000000"]
        
        for i in range(total_frames):
            color = colors[i % len(colors)]
            frame = Image.new('RGBA', (width, height), color)
            if overlay_only:
                AnimationProcessor._clear_center(frame, border_width)
            elif content_image:
                frame.paste(content_image, (border_width, border_width), content_image)
            frames.append(frame)
            
        return frames, 100 # Slower strobe

    @staticmethod
    def generate_glitch_frames(base_image, total_frames=20, border_width=10, overlay_only=False):
        """
        Generates a digital glitch effect animation.
        """
        frames = []
        if isinstance(base_image, tuple): width, height = base_image
        else: width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA': base_image = base_image.convert('RGBA')

        # Content Image Setup
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)
        
        import random
        
        for _ in range(total_frames):
            bg = Image.new('RGBA', (width, height), (20, 20, 20, 255)) # Dark BG
            
            # Draw random glitch artifacts in border
            draw = ImageDraw.Draw(bg)
            for _ in range(10):
                x = random.randint(0, width)
                y = random.randint(0, height)
                w = random.randint(5, 50)
                h = random.randint(2, 10)
                color = random.choice(["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF"])
                draw.rectangle([x, y, x+w, y+h], fill=color)

            # Paste content
            if overlay_only:
                AnimationProcessor._clear_center(bg, border_width)
            elif content_image:
                # Random slight offset for content
                off_x = random.randint(-2, 2)
                off_y = random.randint(-2, 2)
                bg.paste(content_image, (border_width + off_x, border_width + off_y), content_image)
                
                # RGB Shift Effect on content
                r, g, b, a = content_image.split()
                # content_shifted = Image.merge("RGBA", (r, g, b, a)) # Unused

            
            frames.append(bg)
            
        return frames, 50

    @staticmethod
    def generate_spin_frames(base_image, color_hex, total_frames=30, border_width=10, overlay_only=False):
        """
        Generates a spinning gradient border.
        """
        frames = []
        if isinstance(base_image, tuple): width, height = base_image
        else: width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA': base_image = base_image.convert('RGBA')
        
        # Resize Content
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)

        import math
        
        # Base Gradient Disk
        # We create a larger square image to rotate without cutting corners, then crop to size.
        diag = int(math.sqrt(width**2 + height**2))
        disk_size = diag + 20
        disk = Image.new("RGBA", (disk_size, disk_size), (0,0,0,0))
        draw = ImageDraw.Draw(disk)
        
        # Conical Gradientish simulation
        # Drawing many pie slices
        center = (disk_size // 2, disk_size // 2)
        steps = 360
        r = int(color_hex[1:3], 16)
        g = int(color_hex[3:5], 16)
        b = int(color_hex[5:7], 16)
        
        for i in range(steps):
            angle_start = i
            angle_end = i + 1
            # Fade alpha or brightness based on angle
            factor = i / steps
            nr = int(r * factor)
            ng = int(g * factor)
            nb = int(b * factor)
            fill = (nr, ng, nb, 255)
            draw.pieslice([0, 0, disk_size, disk_size], angle_start, angle_end, fill=fill)
            
        for i in range(total_frames):
            angle = (360 / total_frames) * i
            rotated_disk = disk.rotate(-angle) # Clockwise
            
            # Crop center to match target size
            left = (disk_size - width) // 2
            top = (disk_size - height) // 2
            bg = rotated_disk.crop((left, top, left + width, top + height))
            
            # Create hole for content? Or just paste over.
            # Paste content
            if overlay_only:
                 AnimationProcessor._clear_center(bg, border_width)
            elif content_image:
                 bg.paste(content_image, (border_width, border_width), content_image)
            
            frames.append(bg)
            
        return frames, 50

    @staticmethod
    def generate_flow_frames(base_image, color_hex, total_frames=30, border_width=10, overlay_only=False):
        """
        Generates a flowing linear gradient border.
        """
        frames = []
        if isinstance(base_image, tuple): width, height = base_image
        else: width, height = base_image.size
        if not overlay_only and hasattr(base_image, 'mode') and base_image.mode != 'RGBA': base_image = base_image.convert('RGBA')

        # Resize Content
        inner_width = width - (border_width * 2)
        inner_height = height - (border_width * 2)
        content_image = None
        if not overlay_only and inner_width > 0 and inner_height > 0:
             content_image = base_image.resize((inner_width, inner_height), Image.LANCZOS)
             
        # Create a tall gradient that slides down
        grad_height = height * 2
        gradient = Image.new("RGBA", (width, grad_height), (0,0,0,255))
        draw = ImageDraw.Draw(gradient)
        
        r = int(color_hex[1:3], 16)
        g = int(color_hex[3:5], 16)
        b = int(color_hex[5:7], 16)
        
        # Simple gradient strips
        steps = 20
        step_h = grad_height / steps
        for i in range(steps):
             # Alternating or pulsing?
             # Let's do a sine wave of brightness
             import math
             val = 0.5 + 0.5 * math.sin(2 * math.pi * i / steps)
             nr = int(r * val)
             ng = int(g * val)
             nb = int(b * val)
             draw.rectangle([0, i*step_h, width, (i+1)*step_h], fill=(nr, ng, nb, 255))

        for i in range(total_frames):
            # Shift Y
            offset = int((grad_height / 2) * (i / total_frames))
            
            # Crop the visible window
            bg = gradient.crop((0, offset, width, offset + height))
            
            if overlay_only:
                 AnimationProcessor._clear_center(bg, border_width)
            elif content_image:
                 bg.paste(content_image, (border_width, border_width), content_image)
                
            frames.append(bg)
            
        return frames, 60
