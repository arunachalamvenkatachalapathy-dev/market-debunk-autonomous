import os
import subprocess

def create_dummy_video(tag, color, text):
    os.makedirs('assets/animations', exist_ok=True)
    out_path = f'assets/animations/{tag}_1.mp4'
    if os.path.exists(out_path):
        print(f"Skipping {tag}, already exists.")
        return
        
    print(f"Generating placeholder video for {tag}...")
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c={color}:s=1080x1920:d=10",
        "-vf", f"drawtext=text='{text} Animation Placeholder':fontcolor=white:fontsize=80:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-t", "10",
        out_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Created {out_path}")

if __name__ == '__main__':
    create_dummy_video("bullish", "green", "Bullish")
    create_dummy_video("bearish", "red", "Bearish")
    create_dummy_video("neutral", "gray", "Neutral")
    create_dummy_video("educational", "blue", "Educational")
    print("Bootstrap complete. Asset pool is ready.")
