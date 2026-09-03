from PIL import Image, ImageDraw, ImageFont
import os
import cv2

def get_face_bbox(image_path):
    """Detects the largest face in the image using OpenCV Haar Cascades."""
    cascade_path = os.path.join("assets", "haarcascade_frontalface_default.xml")
    face_cascade = cv2.CascadeClassifier(cascade_path)
    img = cv2.imread(image_path)
    if img is None: 
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
    img_h, img_w = gray.shape
    # Reject implausibly small detections (Haar cascades sometimes false-positive on
    # ties, collars, glasses glare, etc.) - a real headshot face should be a
    # meaningful fraction of the frame.
    min_face_dim = 0.15 * min(img_w, img_h)
    faces = [f for f in faces if f[2] >= min_face_dim and f[3] >= min_face_dim]
    if len(faces) > 0:
        # Get the largest face
        faces = sorted(faces, key=lambda x: x[2]*x[3], reverse=True)
        return faces[0] # (x, y, w, h)
    return None

def create_circular_mask(size):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size[0], size[1]), fill=255)
    return mask

def clamp_to_image_bounds(left, top, w, h, img_size):
    left = max(0, min(left, img_size[0] - w))
    top = max(0, min(top, img_size[1] - h))
    return (int(left), int(top), int(left + w), int(top + h))

def crop_for_circle(image_pil, face_bbox):
    """Crops the image focusing on the face, with eyes in the upper 40%."""
    img_w, img_h = image_pil.size
    
    if face_bbox is None:
        side = min(img_w, img_h)
        left = (img_w - side) / 2
        top = img_h * 0.05 # 5% from top
        crop_box = clamp_to_image_bounds(left, top, side, side, image_pil.size)
        return image_pil.crop(crop_box)
        
    x, y, fw, fh = face_bbox
    cx = x + fw / 2
    eye_y = y + fh * 0.40 # eyes sit ~40% down a typical face bbox
    
    crop_side = fh * 2.2 # Zoom factor
    
    # Guardrail 2: Constrain crop_side to image bounds
    crop_side = min(crop_side, img_w, img_h)
    
    top = eye_y - crop_side * 0.40
    left = cx - crop_side / 2
    
    # Guardrail 3: Enforce minimum headroom
    if top > y - 0.10 * crop_side:
        top = y - 0.15 * crop_side # Push up to give headroom
        
    crop_box = clamp_to_image_bounds(left, top, crop_side, crop_side, image_pil.size)
    return image_pil.crop(crop_box)

def wrap_to_width(text, font, box_width_px):
    words = text.split()
    lines, current_line = [], []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = font.getbbox(test_line)
        if (bbox[2] - bbox[0]) <= box_width_px:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                # Word is longer than box width, force cut it
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def fit_title(text, box_width_px, max_height_px, font_path, max_font_px, min_font_px=22, max_lines=3):
    """Dynamic font-fit algorithm ensuring no overflow."""
    font_size = max_font_px
    while font_size >= min_font_px:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except:
            font = ImageFont.load_default()
            
        lines = wrap_to_width(text, font, box_width_px)
        line_height = font_size * 1.2
        block_height = len(lines) * line_height
        
        if len(lines) <= max_lines and block_height <= max_height_px:
            return lines, font, font_size
            
        font_size -= 2
        
    # Floor hit: truncate
    try:
        font = ImageFont.truetype(font_path, min_font_px)
    except:
        font = ImageFont.load_default()
    lines = wrap_to_width(text, font, box_width_px)
    return lines[:max_lines], font, min_font_px

def compose_poster(base_image_path, profile_image_path, title, author_name, output_path, font_path="assets/Roboto-Bold.ttf"):
    W, H = 1080, 1080
    
    # 1. Base Image
    try:
        base = Image.open(base_image_path).convert("RGBA")
        from PIL import ImageOps
        base = ImageOps.fit(base, (W, H), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"Error loading base: {e}")
        base = Image.new("RGBA", (W, H), (40, 44, 52, 255))
        
    # 2. Master Grid & Banner
    banner_y = int(0.75 * H)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    draw_overlay.rectangle([0, banner_y, W, H], fill=(44, 62, 80, 240))
    base = Image.alpha_composite(base, overlay)
    
    # 3. Photo Circle Rules
    try:
        profile = Image.open(profile_image_path).convert("RGB")
        face_bbox = get_face_bbox(profile_image_path)
        
        # Face Centering
        cropped_square = crop_for_circle(profile, face_bbox)
        
        diameter = int(0.19 * W)
        cropped_square = cropped_square.resize((diameter, diameter), Image.Resampling.LANCZOS)
        
        # Apply circular mask
        mask = create_circular_mask((diameter, diameter))
        circular_profile = Image.new("RGBA", (diameter, diameter), (0,0,0,0))
        circular_profile.paste(cropped_square, (0,0), mask)
        
        # Border (1.5% of diameter)
        border_thickness = int(0.015 * diameter)
        if border_thickness < 2: border_thickness = 2
        
        bordered_size = diameter + 2*border_thickness
        bordered_profile = Image.new("RGBA", (bordered_size, bordered_size), (0,0,0,0))
        draw_border = ImageDraw.Draw(bordered_profile)
        draw_border.ellipse((0, 0, bordered_size, bordered_size), fill=(255, 255, 255, 255))
        bordered_profile.paste(circular_profile, (border_thickness, border_thickness), circular_profile)
        
        # Position: Center X = 85%, Center Y = 85.5%
        cx = int(0.85 * W)
        cy = int(0.855 * H)
        pos_x = cx - (bordered_size // 2)
        pos_y = cy - (bordered_size // 2)
        
        base.paste(bordered_profile, (pos_x, pos_y), bordered_profile)
    except Exception as e:
        print(f"Error processing profile image: {e}")
        
    # 4. Typography Rules (Bottom-Up Anchoring)
    draw = ImageDraw.Draw(base)
    text_col_x = int(0.05 * W)
    text_col_w = int(0.65 * W) # 70% boundary - 5% left margin
    
    # Byline (fixed near bottom)
    byline_font_size = int(0.018 * W) # ~19px
    try:
        byline_font = ImageFont.truetype(font_path, byline_font_size)
    except:
        byline_font = ImageFont.load_default()
        
    byline_baseline_y = int(0.95 * H)
    byline_text = f"By {author_name}"
    byline_bbox = byline_font.getbbox(byline_text)
    byline_h = byline_bbox[3] - byline_bbox[1]
    byline_top_y = byline_baseline_y - byline_h
    
    # Title calculations
    title_bottom_y = byline_top_y - int(0.02 * H)
    title_top_y = banner_y + int(0.03 * H)
    available_title_height = title_bottom_y - title_top_y
    
    max_font_size = int(0.049 * W) # ~52px
    
    lines, title_font, f_size = fit_title(
        text=title, 
        box_width_px=text_col_w, 
        max_height_px=available_title_height, 
        font_path=font_path, 
        max_font_px=max_font_size
    )
    
    # Draw title bottom-up
    line_height = int(f_size * 1.2)
    total_block_height = len(lines) * line_height
    current_y = title_bottom_y - total_block_height
    
    for line in lines:
        draw.text((text_col_x, current_y), line, font=title_font, fill=(255,255,255,255))
        current_y += line_height
        
    # Draw byline
    draw.text((text_col_x, byline_top_y), byline_text, font=byline_font, fill=(220,224,230,255))
    
    # 5. Output
    final_image = base.convert("RGB")
    final_image.save(output_path, quality=100, subsampling=0)
    print(f"Poster successfully generated at {output_path}")
    return output_path
