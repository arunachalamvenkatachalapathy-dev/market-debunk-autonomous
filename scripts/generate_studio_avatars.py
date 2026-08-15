"""
Studio Avatar Generator for Market Debunk AI Studio.
Generates and caches photorealistic character sets for:
1. The Skeptic (Red Team / Retail Investor Persona)
2. The Analyst (Green Team / Expert Analyst Persona)

Generates both Listening (mouth closed) and Speaking (mouth open) states.
"""
import os
import io
import logging
from PIL import Image, ImageDraw, ImageFont, ImageFilter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AVATARS_DIR = os.path.join(os.getcwd(), "assets", "avatars")
os.makedirs(AVATARS_DIR, exist_ok=True)

def generate_procedural_avatar(role="skeptic", state="closed", size=(720, 720)):
    """
    Creates a sleek, high-definition studio avatar graphic with character illustration,
    lighting gradients, and facial expression states.
    """
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    w, h = size
    cx, cy = w // 2, h // 2

    # Background studio circle / vignette
    glow_color = (255, 46, 84, 180) if role == "skeptic" else (0, 255, 163, 180)
    bg_base = (20, 24, 33, 255)
    
    # Draw background gradient disc
    disc_radius = int(w * 0.45)
    draw.ellipse([cx - disc_radius, cy - disc_radius, cx + disc_radius, cy + disc_radius], fill=bg_base)
    
    # Outer neon rim glow
    rim_width = 8
    draw.ellipse(
        [cx - disc_radius, cy - disc_radius, cx + disc_radius, cy + disc_radius],
        outline=glow_color[:3] + (220,),
        width=rim_width
    )

    # Torso / Suit shoulders
    suit_color = (35, 40, 52) if role == "skeptic" else (18, 28, 48)
    draw.chord([cx - 240, cy + 80, cx + 240, cy + 500], start=180, end=360, fill=suit_color)
    
    # Shirt collar & tie
    shirt_color = (220, 225, 235)
    draw.polygon([(cx - 45, cy + 120), (cx + 45, cy + 120), (cx, cy + 220)], fill=shirt_color)
    tie_color = (220, 40, 60) if role == "skeptic" else (0, 180, 120)
    draw.polygon([(cx - 15, cy + 150), (cx + 15, cy + 150), (cx + 20, cy + 300), (cx, cy + 330), (cx - 20, cy + 300)], fill=tie_color)

    # Neck
    skin_color = (235, 185, 155) if role == "skeptic" else (225, 175, 145)
    neck_shadow = (200, 150, 120)
    draw.rectangle([cx - 38, cy + 60, cx + 38, cy + 140], fill=neck_shadow)
    draw.rectangle([cx - 35, cy + 60, cx + 35, cy + 130], fill=skin_color)

    # Head shape
    head_w, head_h = 160, 200
    draw.ellipse([cx - head_w//2, cy - 100, cx + head_w//2, cy + head_h//2], fill=skin_color)

    # Hair
    hair_color = (40, 30, 25) if role == "skeptic" else (30, 35, 45)
    if role == "skeptic":
        # Messy / expressive hair for skeptic
        draw.chord([cx - 95, cy - 140, cx + 95, cy - 20], start=180, end=360, fill=hair_color)
        draw.polygon([(cx - 90, cy - 60), (cx - 70, cy - 110), (cx - 30, cy - 130)], fill=hair_color)
        draw.polygon([(cx + 90, cy - 60), (cx + 70, cy - 110), (cx + 30, cy - 130)], fill=hair_color)
    else:
        # Neat side-part professional hair for analyst
        draw.chord([cx - 90, cy - 135, cx + 90, cy - 25], start=170, end=370, fill=hair_color)
        draw.ellipse([cx - 92, cy - 110, cx + 20, cy - 40], fill=hair_color)

    # Eyebrows
    brow_color = (30, 20, 15)
    if role == "skeptic":
        # Worried / skeptical raised eyebrow
        draw.line([(cx - 65, cy - 40), (cx - 25, cy - 55)], fill=brow_color, width=6)
        draw.line([(cx + 25, cy - 50), (cx + 65, cy - 35)], fill=brow_color, width=6)
    else:
        # Sharp confident horizontal eyebrows
        draw.line([(cx - 65, cy - 45), (cx - 25, cy - 45)], fill=brow_color, width=6)
        draw.line([(cx + 25, cy - 45), (cx + 65, cy - 45)], fill=brow_color, width=6)

    # Eyes
    eye_white = (255, 255, 255)
    pupil_color = (30, 25, 20)
    # Left eye
    draw.ellipse([cx - 55, cy - 35, cx - 30, cy - 15], fill=eye_white)
    draw.ellipse([cx - 46, cy - 31, cx - 36, cy - 19], fill=pupil_color)
    # Right eye
    draw.ellipse([cx + 30, cy - 35, cx + 55, cy - 15], fill=eye_white)
    draw.ellipse([cx + 36, cy - 31, cx + 46, cy - 19], fill=pupil_color)

    if role == "analyst":
        # Analyst stylish glasses
        glasses_frame = (210, 180, 80)
        draw.ellipse([cx - 62, cy - 42, cx - 22, cy - 8], outline=glasses_frame, width=4)
        draw.ellipse([cx + 22, cy - 42, cx + 62, cy - 8], outline=glasses_frame, width=4)
        draw.line([(cx - 22, cy - 25), (cx + 22, cy - 25)], fill=glasses_frame, width=4)

    # Nose
    draw.line([(cx, cy - 20), (cx - 5, cy + 10), (cx + 8, cy + 10)], fill=neck_shadow, width=4)

    # Mouth based on state
    if state == "closed":
        if role == "skeptic":
            # Wavy / doubting closed mouth
            draw.line([(cx - 25, cy + 45), (cx - 5, cy + 42), (cx + 25, cy + 48)], fill=(150, 70, 60), width=5)
        else:
            # Subtle smirk / confident smile
            draw.arc([cx - 25, cy + 30, cx + 25, cy + 55], start=20, end=160, fill=(140, 60, 50), width=5)
    else:
        # Speaking / Open mouth
        mouth_inner = (60, 20, 20)
        teeth_white = (250, 250, 250)
        draw.ellipse([cx - 25, cy + 35, cx + 25, cy + 65], fill=mouth_inner)
        draw.chord([cx - 20, cy + 35, cx + 20, cy + 50], start=180, end=360, fill=teeth_white)

    # Badge overlay at bottom of avatar
    badge_bg = (220, 30, 60, 230) if role == "skeptic" else (0, 200, 120, 230)
    badge_text = "THE SKEPTIC" if role == "skeptic" else "THE ANALYST"
    
    badge_w, badge_h = 220, 44
    draw.rounded_rectangle(
        [cx - badge_w//2, h - 60, cx + badge_w//2, h - 16],
        radius=12,
        fill=badge_bg,
        outline=(255, 255, 255, 220),
        width=2
    )
    
    # Draw simple text label
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
        
    bbox = draw.textbbox((0, 0), badge_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw//2, h - 50), badge_text, fill=(255, 255, 255), font=font)

    return img

def ensure_studio_avatars():
    """Generates all 4 avatar asset states if not already cached."""
    roles = ["skeptic", "analyst"]
    states = ["closed", "open"]
    
    created_paths = []
    for role in roles:
        for state in states:
            filename = f"{role}_{state}.png"
            filepath = os.path.join(AVATARS_DIR, filename)
            if not os.path.exists(filepath) or os.path.getsize(filepath) < 1000:
                logger.info(f"Generating studio avatar: {filename}...")
                avatar_img = generate_procedural_avatar(role=role, state=state)
                avatar_img.save(filepath, format="PNG")
                logger.info(f"✅ Saved {filename} ({os.path.getsize(filepath)} bytes)")
            created_paths.append(filepath)
            
    return created_paths

if __name__ == "__main__":
    ensure_studio_avatars()
