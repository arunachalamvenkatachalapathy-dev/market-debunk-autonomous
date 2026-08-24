import os
import random
import logging
from pydub import AudioSegment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AUDIO_DIR = os.path.join(os.getcwd(), "assets", "audio")
BGM_DIR = os.path.join(AUDIO_DIR, "bgm")
SFX_DIR = os.path.join(AUDIO_DIR, "sfx")

def mix_audio_track(voice_path, output_path):
    if not os.path.exists(voice_path):
        logger.error(f"Voice track not found: {voice_path}")
        return False

    logger.info("Loading voiceover...")
    voice = AudioSegment.from_file(voice_path)
    
    # 1. Add Background Music (Crossfade 2 tracks)
    bgm_files = [f for f in os.listdir(BGM_DIR) if f.endswith(".mp3") or f.endswith(".webm")]
    if not bgm_files:
        logger.warning("No BGM files found. Outputting voice only.")
        voice.export(output_path, format="mp3")
        return True
        
    import random
    if len(bgm_files) >= 2:
        chosen_bgms = random.sample(bgm_files, 2)
    else:
        chosen_bgms = [bgm_files[0], bgm_files[0]]
        
    logger.info(f"Mixing BGM Tracks: {chosen_bgms}")
    bgm1 = AudioSegment.from_file(os.path.join(BGM_DIR, chosen_bgms[0])) - 15
    bgm2 = AudioSegment.from_file(os.path.join(BGM_DIR, chosen_bgms[1])) - 15
    
    half_length = len(voice) // 2
    
    # Loop BGM to ensure it's long enough
    while len(bgm1) < half_length + 2000:
        bgm1 = bgm1 + bgm1
    while len(bgm2) < half_length + 2000:
        bgm2 = bgm2 + bgm2
        
    bgm1 = bgm1[:half_length + 2000].fade_out(2000)
    bgm2 = bgm2[:len(voice) - half_length + 2000].fade_in(2000)
    
    # Append with crossfade
    final_bgm = bgm1.append(bgm2, crossfade=2000)
    final_bgm = final_bgm[:len(voice)]
    
    # Overlay BGM onto voice
    mixed_audio = voice.overlay(final_bgm)
    
    logger.info("Exporting mixed master audio (No SFX clicks as requested)...")
    mixed_audio.export(output_path, format="mp3")
    return True

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python mix_audio.py <voice_input> <output_path>")
        sys.exit(1)
    mix_audio_track(sys.argv[1], sys.argv[2])
