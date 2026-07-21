import os
import sys
import yaml
import time
import random
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(config_path):
        config_path = "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def create_directory_structure(config):
    print("\nPreparing clean local data directories...")
    categories = list(config["detectors"].keys())
    
    base_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    
    # Purge old directories completely to remove any mixed or overfitted files
    import shutil
    if os.path.exists(base_data_dir):
        print(f"Purging old data directories under: {base_data_dir}...")
        try:
            shutil.rmtree(base_data_dir)
            time.sleep(0.3)
        except Exception as e:
            print(f"Warning clearing old folders: {e}")
            
    os.makedirs(base_data_dir, exist_ok=True)
        
    for cat in categories:
        labels = config["detectors"][cat]["labels"]
        for split in ["train", "val"]:
            for label in labels:
                dir_path = os.path.join(base_data_dir, cat, split, label)
                os.makedirs(dir_path, exist_ok=True)
                
    print("Clean directory structure successfully created.")
    return base_data_dir

# ==============================================================================
# ADVANCED DOMAIN-SHIFTED SYNTHESIS ENGINE
# ==============================================================================

def apply_extreme_augmentations(img, split, noise_level=25):
    """
    Applies extreme pixel-level Gaussian noise, heavy lighting/exposure shifts,
    domain-specific contrast changes, and out-of-focus blurs to mimic webcams.
    """
    # Convert image to numpy array
    arr = np.array(img, dtype=np.float32)
    
    # 1. Add Severe Gaussian Noise
    noise = np.random.normal(0, noise_level, arr.shape)
    arr = np.clip(arr + noise, 0, 255)
    
    # 2. Extreme Brightness / Exposure shift (simulates bad webcam lighting)
    # Train has moderate lighting shifts; Val has extreme exposure shifts to force generalization
    brightness_factor = random.uniform(0.65, 1.35) if split == "train" else random.uniform(0.50, 1.50)
    arr = np.clip(arr * brightness_factor, 0, 255)
    
    # 3. Uneven Room Light Leaks / Gradients
    h, w, c = arr.shape
    grad_start = random.uniform(0.65, 0.85)
    grad_end = random.uniform(1.15, 1.35)
    gradient = np.linspace(grad_start, grad_end, w)
    gradient = np.tile(gradient[:, np.newaxis], (1, h)).T # H x W
    for i in range(c):
        arr[:, :, i] *= gradient
        
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    augmented_img = Image.fromarray(arr)
    
    # 4. Out-of-focus webcam blur (30% probability in Train, 50% in Val)
    blur_prob = 0.30 if split == "train" else 0.50
    if random.random() < blur_prob:
        radius = random.uniform(0.5, 1.8)
        augmented_img = augmented_img.filter(ImageFilter.GaussianBlur(radius=radius))
        
    return augmented_img

def draw_textured_shirt(draw, pts, color, pattern_type="stripes"):
    """Draws a clothing shape filled with complex patterns to make features hard to learn."""
    # Draw base solid shape
    draw.polygon(pts, fill=color)
    
    # Overlay high-frequency patterns
    xmin = min(p[0] for p in pts)
    xmax = max(p[0] for p in pts)
    ymin = min(p[1] for p in pts)
    ymax = max(p[1] for p in pts)
    
    pattern_color = (max(0, color[0]-35), max(0, color[1]-35), max(0, color[2]-35))
    
    if pattern_type == "stripes":
        for x in range(xmin, xmax, 6):
            draw.line([(x, ymin), (x, ymax)], fill=pattern_color, width=2)
    elif pattern_type == "checks":
        for x in range(xmin, xmax, 8):
            draw.line([(x, ymin), (x, ymax)], fill=pattern_color, width=2)
        for y in range(ymin, ymax, 8):
            draw.line([(xmin, y), (xmax, y)], fill=pattern_color, width=2)

def generate_posture_image(label, split, idx, size=(224, 224)):
    """
    Generates office desk posture photos.
    DOMAIN SHIFT: 
    - Train: Dark theme backdrops, blue striped shirts, warm skin, small camera tilt.
    - Val: Bright walls, red checkered shirts, cool skin, large camera tilt & offsets.
    """
    w, h = size
    random.seed(f"posture_{split}_{label}_{idx}")
    
    # 1. SETUP STRICT DOMAIN SHIFT PARAMS
    if split == "train":
        bg_color = (20, 24, 34)
        wall_color = (12, 15, 22)
        shirt_color = (50, 110, 220) # Blue
        shirt_pattern = "stripes"
        skin_color = (245, 205, 175) # Warm skin
        monitor_color = (8, 10, 14)
        chair_color = (30, 35, 45)
    else: # split == "val" (Severe domain shift)
        bg_color = (230, 230, 225) # Bright wall
        wall_color = (200, 200, 195)
        shirt_color = (180, 40, 50) # Burgundy Red
        shirt_pattern = "checks"
        skin_color = (230, 190, 160) # Cool skin
        monitor_color = (50, 50, 55) # Light gray monitor
        chair_color = (80, 80, 90)
        
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # Render background walls/panels
    draw.polygon([(0, 0), (w, 0), (w, h//2), (0, h*2//3)], fill=wall_color)
    # Monitor distractor
    draw.rectangle([0, h//3, w//4, h*4//5], fill=monitor_color, outline=(100, 100, 110) if split=="val" else (40, 50, 60), width=2)
    # Chair backrest
    draw.ellipse([w//3, h//4, w*2//3, h*3//4], fill=chair_color)
    
    # Scale/crop translation augmentation
    dx = random.randint(-6, 6) if split == "train" else random.randint(-14, 14)
    dy = random.randint(-4, 6) if split == "train" else random.randint(-10, 15)
    
    head_r = random.randint(18, 22)
    head_cx = w//2 + dx
    head_cy = h//4 + dy
    
    # 2. RENDER POSTURAL GEOMETRY
    if label == "good":
        neck_pts = [(w//2 - 6 + dx, head_cy + head_r - 5), (w//2 + 6 + dx, head_cy + head_r - 5), 
                    (w//2 + 6 + dx, h//3 + 12 + dy), (w//2 - 6 + dx, h//3 + 12 + dy)]
        draw.polygon(neck_pts, fill=skin_color)
        
        shoulder_left = (w//4 + dx, h//3 + 15 + dy)
        shoulder_right = (w*3//4 + dx, h//3 + 15 + dy)
        torso_pts = [shoulder_left, shoulder_right, (w*3//4 + dx, h), (w//4 + dx, h)]
        draw_textured_shirt(draw, torso_pts, shirt_color, shirt_pattern)
        
        draw.line([shoulder_left, shoulder_right], fill=(30, 35, 45), width=4)
        draw.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], fill=skin_color)
        
    elif label == "slouched":
        # Curved/hunched spine, dropped forward shoulders
        lean = random.choice([-10, 10]) if split == "train" else random.choice([-18, 18])
        head_cx += lean
        head_cy += 12 # Dropped head
        
        neck_pts = [(w//2 - 6 + dx + lean//2, head_cy + head_r - 5), (w//2 + 6 + dx + lean//2, head_cy + head_r - 5),
                    (w//2 + 10 + dx, h//3 + 22 + dy), (w//2 - 10 + dx, h//3 + 22 + dy)]
        draw.polygon(neck_pts, fill=skin_color)
        
        shoulder_left = (w//4 + dx, h//3 + 25 + dy + lean//4)
        shoulder_right = (w*3//4 + dx, h//3 + 35 + dy - lean//4)
        
        torso_pts = [
            shoulder_left, 
            (w//2 + dx + lean, h//3 + 20 + dy), 
            shoulder_right, 
            (w*3//4 - lean + dx, h), 
            (w//4 - lean + dx, h)
        ]
        draw_textured_shirt(draw, torso_pts, shirt_color, shirt_pattern)
        
        draw.line([shoulder_left, (w//2 + dx + lean, h//3 + 20 + dy), shoulder_right], fill=(30, 35, 45), width=4)
        draw.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], fill=skin_color)
        
    return apply_extreme_augmentations(img, split, noise_level=20 if split=="train" else 28)

def generate_eye_contact_image(label, split, idx, size=(224, 224)):
    """
    Generates detailed skin-textured eye crops.
    DOMAIN SHIFT:
    - Train: Green/blue irises, warm skin tones, close-up camera crop.
    - Val: Brown/amber irises, cool skin tones, wider camera crop (wider sclera).
    """
    w, h = size
    random.seed(f"eye_{split}_{label}_{idx}")
    
    # 1. SETUP DOMAIN SHIFT PARAMS
    if split == "train":
        skin_base = (215, 165, 135)
        crease_color = (160, 110, 80)
        iris_color = (25, 150, 200) # Green-Blue
        fiber_color = (20, 80, 120)
        eye_w = random.randint(110, 125) # Close up
        eye_h = random.randint(50, 60)
    else: # split == "val"
        skin_base = (235, 185, 155) # Lighter cool skin
        crease_color = (180, 130, 100)
        iris_color = (130, 85, 40) # Brown-Amber
        fiber_color = (80, 50, 20)
        eye_w = random.randint(85, 100) # Wider crop (iris appears smaller in ratio)
        eye_h = random.randint(40, 48)
        
    img = Image.new("RGB", size, color=skin_base)
    draw = ImageDraw.Draw(img)
    
    # Eyelid crease
    draw.arc([w//2 - eye_w - 5, h//2 - 50, w//2 + eye_w + 5, h//2 + 20], start=180, end=360, fill=crease_color, width=4)
    
    dx = random.randint(-4, 4) if split=="train" else random.randint(-12, 12)
    dy = random.randint(-2, 2) if split=="train" else random.randint(-8, 8)
    cx, cy = w//2 + dx, h//2 + dy
    
    # SCLERA
    draw.ellipse([cx - eye_w, cy - eye_h//2, cx + eye_w, cy + eye_h//2], fill=(245, 248, 255), outline=(130, 90, 70), width=3)
    
    iris_r = random.randint(22, 25) if split=="train" else random.randint(17, 20)
    pupil_r = random.randint(7, 9) if split=="train" else random.randint(5, 7)
    
    # Gaze positions
    if label == "focused":
        iris_cx = cx + random.randint(-3, 3)
        iris_cy = cy + random.randint(-2, 2)
    elif label == "distracted":
        direction = random.choice(["left", "right", "up_left", "up_right"])
        offset_x = random.randint(26, 36) if split=="train" else random.randint(20, 26)
        offset_y = random.randint(8, 14) if split=="train" else random.randint(6, 10)
        if direction == "left":
            iris_cx = cx - offset_x
            iris_cy = cy + random.randint(-2, 2)
        elif direction == "right":
            iris_cx = cx + offset_x
            iris_cy = cy + random.randint(-2, 2)
        elif direction == "up_left":
            iris_cx = cx - offset_x + 3
            iris_cy = cy - offset_y
        else:
            iris_cx = cx + offset_x - 3
            iris_cy = cy - offset_y
            
    # IRIS fibers
    draw.ellipse([iris_cx - iris_r, iris_cy - iris_r, iris_cx + iris_r, iris_cy + iris_r], fill=iris_color)
    
    # Radial fiber lines
    for angle in range(0, 360, 15):
        rad = np.radians(angle)
        x1 = iris_cx + int((iris_r - 6) * np.cos(rad))
        y1 = iris_cy + int((iris_r - 6) * np.sin(rad))
        x2 = iris_cx + int(iris_r * np.cos(rad))
        y2 = iris_cy + int(iris_r * np.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=fiber_color, width=1)
        
    # PUPIL
    draw.ellipse([iris_cx - pupil_r, iris_cy - pupil_r, iris_cx + pupil_r, iris_cy + pupil_r], fill=(12, 14, 18))
    
    # Specular highlights
    draw.ellipse([iris_cx - 4, iris_cy - 4, iris_cx, iris_cy], fill=(255, 255, 255))
    
    # Upper eyelashes
    draw.arc([cx - eye_w - 1, cy - eye_h//2 - 1, cx + eye_w + 1, cy + eye_h//2 + 1], start=180, end=360, fill=(40, 30, 25), width=4)
    # Lash lines
    for lx in range(cx - eye_w + 15, cx + eye_w - 15, 12):
        ly = cy - 20 - int(15 * (1 - ((lx - cx)/eye_w)**2))
        draw.line([(lx, ly), (lx + random.randint(-4, 4), ly - random.randint(8, 14))], fill=(40, 30, 25), width=2)
        
    return apply_extreme_augmentations(img, split, noise_level=16 if split=="train" else 25)

def generate_attire_image(label, split, idx, size=(224, 224)):
    """
    Generates presentation apparel photos.
    DOMAIN SHIFT:
    - Train: Charcoal suits with red ties vs. bright yellow/green casual hoodies, warm skin.
    - Val: Navy blue suits with light blue ties vs. dark gray casual crewnecks, cool skin, wider camera distance.
    """
    w, h = size
    random.seed(f"attire_{split}_{label}_{idx}")
    
    # 1. SETUP DOMAIN SHIFT PARAMS
    if split == "train":
        bg_color = (22, 26, 34)
        suit_color = (35, 40, 48) # Charcoal
        tie_color = (180, 40, 50) # Red
        casual_color = (78, 222, 163) # Bright Green
        casual_pattern = "stripes"
        skin_color = (245, 205, 175)
        zoom_factor = 1.0
    else: # split == "val"
        bg_color = (240, 240, 245) # Bright boardroom backdrop
        suit_color = (15, 22, 38) # Navy Blue
        tie_color = (40, 80, 160) # Light blue
        casual_color = (90, 95, 105) # Gray hoodie
        casual_pattern = "checks"
        skin_color = (230, 190, 160)
        zoom_factor = 0.85 # Camera shifted back (person appears smaller)
        
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # RENDER BOARDROOM DISTRACTORS
    draw.polygon([(0, 0), (w, 0), (w//2, h)], fill=(max(0, bg_color[0]-15), max(0, bg_color[1]-15), max(0, bg_color[2]-15)))
    
    dx = random.randint(-5, 5) if split=="train" else random.randint(-12, 12)
    dy = random.randint(-4, 4) if split=="train" else random.randint(-8, 12)
    
    # Scaled parameters
    head_r = int(18 * zoom_factor)
    neck_w = int(6 * zoom_factor)
    shoulder_w = int(w//4 * zoom_factor)
    
    # Head & Neck
    draw.ellipse([w//2 - head_r + dx, h//4 - 5 + dy, w//2 + head_r + dx, h//4 + int(25 * zoom_factor) + dy], fill=skin_color)
    
    if label == "formal":
        shirt_color = (240, 245, 255)
        # Torso
        torso_pts = [(w//2 - shoulder_w + dx, h), (w//2 + shoulder_w + dx, h), 
                     (w//2 + shoulder_w + 10 + dx, h//3 + 20 + dy), (w//2 - shoulder_w - 10 + dx, h//3 + 20 + dy)]
        draw.polygon(torso_pts, fill=suit_color)
        
        # Shirt V-Neck
        draw.polygon([(w//2 - 20 + dx, h//3 + 12 + dy), (w//2 + 20 + dx, h//3 + 12 + dy), 
                     (w//2 + 30 + dx, h//2 + 10 + dy), (w//2 - 30 + dx, h//2 + 10 + dy)], fill=shirt_color)
        # Suit lapels
        draw.polygon([(w//2 - shoulder_w - 5 + dx, h//3 + 20 + dy), (w//2 - 12 + dx, h//2 + 20 + dy), (w//2 - 2 + dx, h), (w//2 - shoulder_w + dx, h)], fill=(max(0, suit_color[0]-12), max(0, suit_color[1]-12), max(0, suit_color[2]-12)))
        draw.polygon([(w//2 + shoulder_w + 5 + dx, h//3 + 20 + dy), (w//2 + 12 + dx, h//2 + 20 + dy), (w//2 + 2 + dx, h), (w//2 + shoulder_w + dx, h)], fill=(max(0, suit_color[0]-12), max(0, suit_color[1]-12), max(0, suit_color[2]-12)))
        
        # Necktie
        draw.polygon([(w//2 - 8 + dx, h//3 + 16 + dy), (w//2 + 8 + dx, h//3 + 16 + dy), 
                     (w//2 + 10 + dx, h*2//3 + dy), (w//2 + dx, h*2//3 + 18 + dy), (w//2 - 10 + dx, h*2//3 + dy)], fill=tie_color)
        # Tie Knot
        draw.polygon([(w//2 - 7 + dx, h//3 + 12 + dy), (w//2 + 7 + dx, h//3 + 12 + dy), 
                     (w//2 + 5 + dx, h//3 + 19 + dy), (w//2 - 5 + dx, h//3 + 19 + dy)], fill=tie_color)
        
    elif label == "casual":
        # Torso with patterns
        torso_pts = [(w//2 - shoulder_w + dx, h), (w//2 + shoulder_w + dx, h), 
                     (w//2 + shoulder_w + 8 + dx, h//3 + 20 + dy), (w//2 - shoulder_w - 8 + dx, h//3 + 20 + dy)]
        draw_textured_shirt(draw, torso_pts, casual_color, casual_pattern)
        
        # Crew neck collar opening
        draw.ellipse([w//2 - 25 + dx, h//3 + dy, w//2 + 25 + dx, h//3 + 28 + dy], fill=skin_color)
        draw.arc([w//2 - 25 + dx, h//3 + dy, w//2 + 25 + dx, h//3 + 29 + dy], start=0, end=180, fill=(35, 41, 60), width=3)
        # Drawstrings
        draw.line([w//2 - 8 + dx, h//3 + 25 + dy, w//2 - 10 + dx, h//2 + 15 + dy], fill=(255, 255, 255), width=2)
        draw.line([w//2 + 8 + dx, h//3 + 25 + dy, w//2 + 10 + dx, h//2 + 15 + dy], fill=(255, 255, 255), width=2)
        
    return apply_extreme_augmentations(img, split, noise_level=18 if split=="train" else 26)

def generate_confidence_image(label, split, idx, size=(224, 224)):
    """
    Generates presentation silhouettes.
    DOMAIN SHIFT:
    - Train: Stage with blue/cyan spotlight, blue textured garments.
    - Val: Gray stage with warm orange spotlight, red/crimson textured garments.
    """
    w, h = size
    random.seed(f"confidence_{split}_{label}_{idx}")
    
    if split == "train":
        bg_color = (20, 24, 32)
        spot_color = (35, 45, 60) # Cold Blue spotlight
        garment_color = (137, 206, 255) # Cyan
        pattern = "checks"
        skin_color = (245, 205, 175)
    else: # split == "val"
        bg_color = (35, 30, 30) # Warm stage wall
        spot_color = (55, 40, 30) # Warm Orange spotlight
        garment_color = (220, 80, 90) # Crimson Red
        pattern = "stripes"
        skin_color = (230, 190, 160)
        
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # Boardroom presentation outline
    draw.rectangle([w//10, h//12, w*9//10, h*2//3], fill=(10, 10, 12), outline=(60, 70, 85), width=2)
    # Stage spotlight
    draw.polygon([(w//2, 0), (w//6, h), (w*5//6, h)], fill=spot_color)
    
    dx = random.randint(-5, 5) if split=="train" else random.randint(-12, 12)
    dy = random.randint(-5, 5) if split=="train" else random.randint(-8, 12)
    
    head_r = 18
    head_cx = w//2 + dx
    head_cy = h//4 + dy
    
    if label == "confident":
        draw.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], fill=skin_color)
        torso_pts = [(w//4 + dx, h), (w*3//4 + dx, h), (w*3//4 + 12 + dx, h//3 + 12 + dy), (w//4 - 12 + dx, h//3 + 12 + dy)]
        draw_textured_shirt(draw, torso_pts, garment_color, pattern)
        
        draw.line([w//4 - 10 + dx, h//3 + 15 + dy, w//4 - 22 + dx, h + dy], fill=garment_color, width=10)
        draw.line([w*3//4 + 10 + dx, h//3 + 15 + dy, w*3//4 + 22 + dx, h + dy], fill=garment_color, width=10)
        
    elif label == "nervous":
        head_cy += 10
        draw.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], fill=skin_color)
        torso_pts = [(w//4 + 15 + dx, h), (w*3//4 - 15 + dx, h), (w*3//4 - 5 + dx, h//3 + 22 + dy), (w//4 + 5 + dx, h//3 + 22 + dy)]
        draw_textured_shirt(draw, torso_pts, garment_color, pattern)
        
        draw.line([w//4 + 5 + dx, h//3 + 22 + dy, w//2 - 12 + dx, h//2 + 18 + dy], fill=garment_color, width=9)
        draw.line([w*3//4 - 5 + dx, h//3 + 22 + dy, w//2 + 12 + dx, h//2 + 18 + dy], fill=garment_color, width=9)
        draw.line([w//2 - 28 + dx, h//2 + 18 + dy, w//2 + 28 + dx, h//2 + 18 + dy], fill=garment_color, width=7)
        
    return apply_extreme_augmentations(img, split, noise_level=20 if split=="train" else 27)

def generate_emotions_image(label, split, idx, size=(224, 224)):
    """
    Generates speaker headshots.
    DOMAIN SHIFT:
    - Train: Dark studio backdrop, black hair, close cropped face.
    - Val: Bright classroom backdrop, light brown hair, wider cropped face.
    """
    w, h = size
    random.seed(f"emotions_{split}_{label}_{idx}")
    
    if split == "train":
        bg_color = (24, 28, 38)
        spot_color = (32, 38, 50)
        hair_color = (30, 25, 20) # Black
        skin_base = 245
        face_zoom = 1.0
    else: # split == "val"
        bg_color = (235, 235, 230) # Classroom wall
        spot_color = (210, 210, 205)
        hair_color = (130, 95, 70) # Brown/Blonde hair
        skin_base = 230 # Lighter cool skin
        face_zoom = 0.88 # Face appears smaller
        
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # Background light shadow
    draw.ellipse([w//3, h//4, w*5//6, h*5//6], fill=spot_color)
    
    dx = random.randint(-3, 3) if split=="train" else random.randint(-10, 10)
    dy = random.randint(-3, 3) if split=="train" else random.randint(-8, 10)
    
    # Face Oval (scaled by zoom)
    face_w = int(w//4 * face_zoom)
    face_h_y = int(h//6 * face_zoom)
    face_color = (skin_base + random.randint(-5, 5), 205 + random.randint(-5, 5), 175)
    draw.ellipse([w//2 - face_w + dx, face_h_y + dy, w//2 + face_w + dx, h - face_h_y + dy], fill=face_color, outline=(220, 175, 140), width=2)
    
    # Hair outline
    draw.arc([w//2 - face_w - 2 + dx, face_h_y - 5 + dy, w//2 + face_w + 2 + dx, h//3 + 10 + dy], start=180, end=360, fill=hair_color, width=8)
    
    # Eyes
    eye_y = int(h//3 * face_zoom) + 12 + dy
    eye_offset = int(w//6 * face_zoom)
    draw.ellipse([w//2 - eye_offset - 7 + dx, eye_y - 4, w//2 - eye_offset + 7 + dx, eye_y + 4], fill=(24, 28, 38))
    draw.ellipse([w//2 + eye_offset - 7 + dx, eye_y - 4, w//2 + eye_offset + 7 + dx, eye_y + 4], fill=(24, 28, 38))
    
    mouth_y = int(h*2//3 * face_zoom) + dy
    mouth_w = int(32 * face_zoom)
    
    if label == "confident":
        draw.arc([w//2 - eye_offset - 10 + dx, eye_y - 18, w//2 - eye_offset + 10 + dx, eye_y - 6], start=200, end=340, fill=(35, 25, 20), width=3)
        draw.arc([w//2 + eye_offset - 10 + dx, eye_y - 18, w//2 + eye_offset + 10 + dx, eye_y - 6], start=200, end=340, fill=(35, 25, 20), width=3)
        draw.arc([w//2 - mouth_w + dx, mouth_y - 18, w//2 + mouth_w + dx, mouth_y + 12], start=0, end=180, fill=(160, 40, 48), width=4)
        
    elif label == "stressed":
        draw.line([w//2 - eye_offset - 10 + dx, eye_y - 15, w//2 - eye_offset + 8 + dx, eye_y - 8], fill=(35, 25, 20), width=4)
        draw.line([w//2 + eye_offset + 10 + dx, eye_y - 15, w//2 + eye_offset - 8 + dx, eye_y - 8], fill=(35, 25, 20), width=4)
        draw.line([w//2 - 15 + dx, h//4 + dy, w//2 + 15 + dx, h//4 + dy], fill=(200, 150, 120), width=2)
        draw.arc([w//2 - mouth_w + dx, mouth_y + 6, w//2 + mouth_w + dx, mouth_y + 36], start=180, end=360, fill=(160, 40, 48), width=4)
        
    elif label == "neutral":
        draw.line([w//2 - eye_offset - 8 + dx, eye_y - 12, w//2 - eye_offset + 8 + dx, eye_y - 12], fill=(35, 25, 20), width=3)
        draw.line([w//2 + eye_offset - 8 + dx, eye_y - 12, w//2 + eye_offset + 8 + dx, eye_y - 12], fill=(35, 25, 20), width=3)
        draw.line([w//2 - mouth_w + dx, mouth_y + 10, w//2 + mouth_w + dx, mouth_y + 10], fill=(160, 40, 48), width=4)
        
    return apply_extreme_augmentations(img, split, noise_level=16 if split=="train" else 24)

def generate_pristine_offline_dataset(base_dir, config):
    print("\n" + "="*60)
    print("      SYNTHESIZING HIGH-FIDELITY OFFLINE CV DATASETS")
    print("="*60)
    print("Populating pure human-like photo structures locally (Zero Internet required)...")
    
    train_count = 350
    val_count = 80
    
    for cat, cfg in config["detectors"].items():
        print(f"\n* Generating offline human photo structures for '{cat}'...")
        labels = cfg["labels"]
        
        for split, count in [("train", train_count), ("val", val_count)]:
            for label in labels:
                dir_path = os.path.join(base_dir, cat, split, label)
                print(f"  -> Synthesizing {count} unique {split}/{label} images...")
                
                for idx in range(count):
                    # Call complex high-fidelity generators
                    if cat == "posture":
                        img = generate_posture_image(label, split, idx)
                    elif cat == "eye_contact":
                        img = generate_eye_contact_image(label, split, idx)
                    elif cat == "attire":
                        img = generate_attire_image(label, split, idx)
                    elif cat == "confidence":
                        img = generate_confidence_image(label, split, idx)
                    else: # emotions
                        img = generate_emotions_image(label, split, idx)
                        
                    # Save image
                    filename = f"model_frame_{split}_{idx+1}.jpg"
                    img.save(os.path.join(dir_path, filename), "JPEG", quality=92)
                    
                    if (idx+1) % 50 == 0:
                        sys.stdout.write(f"\r     Status: {idx+1}/{count} frames saved...")
                        sys.stdout.flush()
                print()
                
    print("\n" + "="*60)
    print("High-Fidelity Curation Complete! Pristine offline datasets ready.")
    print("="*60)

# ==============================================================================
# MAIN ROUTINE
# ==============================================================================

def main():
    print("================================================================")
    print("                 KEIKO LOCAL DATASET MANAGER")
    print("================================================================")
    
    try:
        config = load_config()
    except Exception as e:
        print(f"Error loading config.yaml: {e}")
        input("Press Enter to exit...")
        return
        
    base_dir = create_directory_structure(config)
    
    start_time = time.time()
    generate_pristine_offline_dataset(base_dir, config)
    duration = time.time() - start_time
    
    print(f"\nCuration successfully completed in {duration:.1f} seconds!")
    
    # Save statistics directly into the registry for display
    registry_path = os.path.join(os.path.dirname(base_dir), "models", "training_stats.json")
    if os.path.exists(registry_path):
        try:
            with open(registry_path, "r") as f:
                stats = json.load(f)
                
            for cat in config["detectors"].keys():
                labels = config["detectors"][cat]["labels"]
                train_total = 0
                val_total = 0
                
                for label in labels:
                    train_path = os.path.join(base_dir, cat, "train", label)
                    val_path = os.path.join(base_dir, cat, "val", label)
                    
                    if os.path.exists(train_path):
                        train_total += len([x for x in os.listdir(train_path) if x.endswith((".jpg", ".png", ".jpeg"))])
                    if os.path.exists(val_path):
                        val_total += len([x for x in os.listdir(val_path) if x.endswith((".jpg", ".png", ".jpeg"))])
                        
                # Update statistics in registry
                if cat in stats:
                    stats[cat]["status"] = "Untrained (MediaPipe Pre-trained active)"
                    stats[cat]["dataset_details"]["train_samples"] = train_total
                    stats[cat]["dataset_details"]["val_samples"] = val_total
                    stats[cat]["dataset_details"]["local_path"] = os.path.relpath(os.path.join(base_dir, cat), os.path.dirname(registry_path))
                    stats[cat]["metrics"] = {
                      "best_accuracy": 0.0,
                      "precision": 0.0,
                      "recall": 0.0,
                      "f1_score": 0.0,
                      "epochs_run": 0
                    }
                    stats[cat]["history"] = []
                    
            with open(registry_path, "w") as f:
                json.dump(stats, f, indent=2)
            print("Successfully updated database models/training_stats.json with real dataset details!")
        except Exception as e:
            print(f"Warning: Could not write statistics back to registry: {e}")
            
    input("\nPress Enter to return to menu...")

if __name__ == "__main__":
    main()
