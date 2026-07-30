"""
Generate 10 hypnotic, satisfying vertical 1080x1920 looping background MP4 videos
using FFmpeg filters for high-retention short-form videos.
"""
import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKGROUNDS_DIR = os.path.join(os.getcwd(), "assets", "backgrounds")
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)

# 10 Hypnotic Vertical Looping Video Definitions (FFmpeg filter expressions)
BG_SPECS = [
    {
        "filename": "bg_01.mp4",
        "name": "Neon Cyber Grid",
        "filter": "testsrc=size=1080x1920:rate=30,hue=H=2*PI*t/5:s=1,geq=r='128+127*sin(X/30+t*3)':g='128+127*sin(Y/30+t*2)':b='255*sin(sqrt((X-540)^2+(Y-960)^2)/40-t*4)'"
    },
    {
        "filename": "bg_02.mp4",
        "name": "Gold Particle Vortex",
        "filter": "mandelbrot=size=1080x1920:rate=30:maxiter=100:start_scale=1.5:end_scale=0.5:bailout=10,hue=H=PI*t/4:s=2"
    },
    {
        "filename": "bg_03.mp4",
        "name": "Satisfying Plasma Gradient",
        "filter": "cellauto=size=1080x1920:rate=30:rule=30,format=gray,geq=r='128+127*sin(X/20+t*4)':g='50+50*cos(Y/20+t*3)':b='200+55*sin(t*2)'"
    },
    {
        "filename": "bg_04.mp4",
        "name": "Cosmic Hyperspace Tunnel",
        "filter": "life=size=1080x1920:rate=30:mold=10:life_color=0x00FFFF:death_color=0x050520,hue=H=2*PI*t/6:s=1.5"
    },
    {
        "filename": "bg_05.mp4",
        "name": "Emerald Digital Matrix",
        "filter": "testsrc2=size=1080x1920:rate=30,hue=H=PI*2/3:s=2,geq=r='20':g='128+127*sin(Y/15-t*10)':b='40'"
    },
    {
        "filename": "bg_06.mp4",
        "name": "Cyan Fluid Wave",
        "filter": "mptestsrc=size=1080x1920:rate=30:t=dc_burn,hue=H=PI*0.5+t*0.5:s=2,geq=r='10+30*sin(X/40)':g='150+105*sin(Y/40+t*3)':b='220+35*cos(X/30)'"
    },
    {
        "filename": "bg_07.mp4",
        "name": "Pulsing Radial Mandala",
        "filter": "sierpinski=size=1080x1920:rate=30:type=carpet,hue=H=t*0.8:s=1.8"
    },
    {
        "filename": "bg_08.mp4",
        "name": "Sunset Pastel Liquid",
        "filter": "testsrc=size=1080x1920:rate=30,geq=r='200+55*sin((X+Y)/100+t*2)':g='100+100*cos((X-Y)/100+t*2)':b='180+75*sin(t*3)'"
    },
    {
        "filename": "bg_09.mp4",
        "name": "Golden Bull Stock Matrix",
        "filter": "cellauto=size=1080x1920:rate=30:rule=110,geq=r='230+25*sin(X/30+t*5)':g='180+50*cos(Y/30+t*3)':b='20'"
    },
    {
        "filename": "bg_10.mp4",
        "name": "Sapphire Geometric Polygon",
        "filter": "testsrc2=size=1080x1920:rate=30,hue=H=PI*1.3+t*0.2:s=1.5,geq=r='15+15*sin(t)':g='40+40*cos(X/50)':b='200+55*sin(Y/50+t*4)'"
    }
]

def generate_background_video(spec, duration=10):
    filepath = os.path.join(BACKGROUNDS_DIR, spec["filename"])
    if os.path.exists(filepath) and os.path.getsize(filepath) > 50000:
        logger.info(f"Background {spec['filename']} already exists ({os.path.getsize(filepath)} bytes).")
        return filepath
        
    logger.info(f"Generating 1080x1920 hypnotic background loop: {spec['name']} ({spec['filename']})...")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", spec["filter"],
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-r", "30",
        "-an",
        filepath
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        logger.info(f"✅ Generated {spec['filename']} ({os.path.getsize(filepath)} bytes)")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to generate {spec['filename']}: {e.stderr.decode()}")
        # Simplest fallback loop if complex filter fails
        fallback_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:size=1080x1920:rate=30",
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-an",
            filepath
        ]
        subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
    return filepath

def generate_all():
    generated = []
    for spec in BG_SPECS:
        path = generate_background_video(spec, duration=10)
        generated.append(path)
    return generated

if __name__ == "__main__":
    generate_all()
