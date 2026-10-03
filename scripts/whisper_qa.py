from faster_whisper import WhisperModel
import glob
m=WhisperModel('small',device='cpu',compute_type='int8')
for f in sorted(glob.glob('qa_audio/*.mp3')):
    segs,_=m.transcribe(f,language='en',beam_size=5)
    print('RESULT',f,'|',' '.join(x.text.strip() for x in segs))
