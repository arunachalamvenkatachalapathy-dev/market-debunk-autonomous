"""Private, ephemeral Tamil voice QA. Never log credentials, speech, or model IDs."""
import os, subprocess, tempfile, json, sys
from pathlib import Path
import requests

API='https://api.fish.audio'
SOURCE='https://www.youtube.com/watch?v=rPK5QW8XxM8'
TEXT='உங்கள் கையில் ஒரு அட்டை இருக்கு. வெளிநாட்டில் பண இயந்திரம் முன்னால் நிக்கிறீங்க. இந்திய ரூபாயில் கணக்கு போடலாமா என்று திரையில் கேட்கிறது. உடனே சரி என்று சொல்லாதீங்க.'
KEYWORDS=('அட்டை','வெளிநாட்டில்','இந்திய','ரூபாய்','மாற்ற')

def run():
 key=os.environ.get('FISH_AUDIO_API_KEY','')
 if not key: raise RuntimeError('credential missing')
 with tempfile.TemporaryDirectory(prefix='tamil-private-') as tmp:
  base=Path(tmp)
  speech=base/'speech.mp3'
  cipher=Path('review_scripts/private_cipher/arun-tamil-100s.enc')
  passphrase=os.environ.get('TEMP_ARUN_TAMIL_AUDIO_KEY','')
  if not passphrase or not cipher.exists(): raise RuntimeError('encrypted owner audio unavailable')
  subprocess.run(['openssl','enc','-d','-aes-256-cbc','-pbkdf2','-iter','200000','-in',str(cipher),'-out',str(speech),'-pass','env:TEMP_ARUN_TAMIL_AUDIO_KEY'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
  if speech.stat().st_size<100000: raise RuntimeError('audio extraction invalid')
  auth={'Authorization':'Bearer '+key}
  with speech.open('rb') as f:
   response=requests.post(API+'/model',headers=auth,data={'visibility':'private','type':'tts','title':'Arun Tamil private voice QA','train_mode':'fast','enhance_audio_quality':'true','generate_sample':'false'},files=[('voices',('speech.mp3',f,'audio/mpeg'))],timeout=120)
  if response.status_code!=201: raise RuntimeError(f'private voice creation HTTP {response.status_code}')
  obj=response.json(); model=obj.get('_id'); state=obj.get('state')
  if not model or state=='failed': raise RuntimeError('private model unavailable')
  headers={**auth,'model':'s2.1-pro-free','Content-Type':'application/json'}
  result=requests.post(API+'/v1/tts',headers=headers,json={'text':TEXT,'reference_id':model,'format':'mp3','temperature':0.7,'top_p':0.7,'prosody':{'speed':1.0,'volume':0},'normalize':True},timeout=120)
  if result.status_code!=200 or len(result.content)<3000: raise RuntimeError(f'Tamil TTS HTTP {result.status_code}')
  generated=base/'test.mp3';generated.write_bytes(result.content)
  output=Path('out');output.mkdir(exist_ok=True)
  (output/'tamil-owner-qa.mp3').write_bytes(result.content)
  model_plain=base/'model-id.txt';model_plain.write_text(model,encoding='ascii')
  subprocess.run(['openssl','enc','-aes-256-cbc','-pbkdf2','-iter','200000','-salt','-in',str(model_plain),'-out',str(output/'model-id.enc'),'-pass','env:TEMP_ARUN_TAMIL_AUDIO_KEY'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
  print('Tamil private clone created; synthetic QA audio artifact is ready for local transcript check. Model identifier encrypted, not logged.')

if __name__=='__main__':
 try:run()
 except Exception as exc:
  print('Tamil private clone QA blocked: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),file=sys.stderr)
  sys.exit(1)
