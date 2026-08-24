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
    
    # 1. Add Background Music
    bgm_files = [f for f in os.listdir(BGM_DIR) if f.endswith(".mp3") or f.endswith(".webm")]
    if not bgm_files:
        logger.warning("No BGM files found. Outputting voice only.")
        voice.export(output_path, format="mp3")
        return True
        
    chosen_bgm = random.choice(bgm_files)
    logger.info(f"Mixing BGM: {chosen_bgm}")
    bgm = AudioSegment.from_file(os.path.join(BGM_DIR, chosen_bgm))
    
    # Lower BGM volume heavily so it doesn't overpower voice
    bgm = bgm - 15  # Reduce by 15 dB
    
    # Loop BGM if voiceover is longer
    if len(bgm) < len(voice):
        loops = (len(voice) // len(bgm)) + 1
        bgm = bgm * loops
    
    # Trim BGM to exact length of voiceover
    bgm = bgm[:len(voice)]
    
    # Overlay BGM onto voice
    mixed_audio = voice.overlay(bgm)
    
    # 2. Add SFX every ~4 seconds
    sfx_files = [f for f in os.listdir(SFX_DIR) if f.endswith(".mp3") or f.endswith(".webm")]
    if sfx_files:
        logger.info("Adding premium SFX hits...")
        # 4 seconds = 4000 ms
        interval = 4000
        current_time = interval
        
        while current_time < len(mixed_audio):
            chosen_sfx = random.choice(sfx_files)
            sfx = AudioSegment.from_file(os.path.join(SFX_DIR, chosen_sfx))
            # Lower SFX slightly
            sfx = sfx - 5 
            
            mixed_audio = mixed_audio.overlay(sfx, position=current_time)
            # Randomize interval between 3 and 5 seconds for natural feel
            current_time += random.randint(3000, 5000)
    
    logger.info("Exporting mixed master audio...")
    mixed_audio.export(output_path, format="mp3")
    return True

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python mix_audio.py <voice_input> <output_path>")
        sys.exit(1)
    mix_audio_track(sys.argv[1], sys.argv[2])
