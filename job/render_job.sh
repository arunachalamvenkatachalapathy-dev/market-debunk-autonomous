#!/bin/bash
# Market Debunk farm renderer. Bundle layout (job/):
#   manifest.json  {"id","title","description","lang","beats":[[bid,text,heading],...]}
#   img/<bid>.png  aud/<bid>.mp3  logo.png  bgm.mp3
set -e
cd job
mkdir -p ../out sc subs
python3 - <<'PYEOF'
import json, subprocess
m = json.load(open('manifest.json'))
open('../out/title.txt','w').write(m['title']+'\n')
open('../out/description.txt','w').write(m['description']+'\n')
beats = m['beats']
HDR = """[Script Info]
PlayResX: 1080
PlayResY: 1920
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00141E30,&H90141E30,-1,0,0,0,100,100,0.5,0,3,10,0,2,60,60,120,1
Style: Head,DejaVu Sans,64,&H00FFC46B,&H00FFC46B,&H00141E30,&H90141E30,-1,0,0,0,100,100,1,0,3,10,0,7,70,60,200,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
def ts(t):
    h=int(t//3600); mm=int((t%3600)//60); s=t%60
    return f"{h}:{mm:02d}:{s:05.2f}"
lst=[]
for i,(b,text,heading) in enumerate(beats):
    d = float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f'aud/{b}.mp3'],capture_output=True,text=True).stdout.strip())
    words = text.split()
    chunks = [' '.join(words[j:j+4]) for j in range(0,len(words),4)]
    per = d/len(chunks)
    ev = [f"Dialogue: 1,{ts(0)},{ts(d)},Head,,0,0,0,,{heading}"]
    for j,c in enumerate(chunks):
        ev.append(f"Dialogue: 0,{ts(j*per)},{ts(min((j+1)*per,d))},Sub,,0,0,0,,{c}")
    open(f'subs/{b}.ass','w').write(HDR+'\n'.join(ev)+'\n')
    lst.append(f"file 'aud/{b}.mp3'")
    if i < len(beats)-1: lst.append("file 'pad.mp3'")
open('audio_list.txt','w').write('\n'.join(lst)+'\n')
open('beats.txt','w').write('\n'.join(b[0] for b in beats))
PYEOF
ffmpeg -nostdin -y -v error -f lavfi -i anullsrc=r=44100:cl=mono -t 0.35 -c:a libmp3lame -q:a 4 pad.mp3
i=0
for b in $(cat beats.txt); do
  i=$((i+1))
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 aud/$b.mp3)
  N=$(wc -l < beats.txt)
  if [ $i -lt $N ]; then d=$(python3 -c "print($d+0.35)"); fi
  FRAMES=$(python3 -c "print(int(round($d*30)))")
  if [ $((i % 2)) -eq 0 ]; then
    Z="if(eq(on,0),1.055,max(zoom-0.00045,1.0))"; X="iw/2-(iw/zoom/2)+sin(on/90)*8"; Y="ih/2-(ih/zoom/2)"
  else
    Z="min(zoom+0.00045,1.055)"; X="iw/2-(iw/zoom/2)"; Y="ih/2-(ih/zoom/2)"
  fi
  ffmpeg -nostdin -y -v error -loop 1 -framerate 30 -i img/$b.png \
    -filter_complex "[0:v]scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,zoompan=z='$Z':x='$X':y='$Y':d=$FRAMES:s=1080x1920:fps=30,subtitles=subs/$b.ass[v]" \
    -map "[v]" -t "$d" -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p sc/$b.mp4
  echo "scene $b done"
done
for b in $(cat beats.txt); do echo "file '$PWD/sc/$b.mp4'"; done > sc_list.txt
ffmpeg -nostdin -y -v error -f concat -safe 0 -i sc_list.txt -c copy vcat.mp4
ffmpeg -nostdin -y -v error -i vcat.mp4 -i logo.png -filter_complex \
 "[0:v]scale=720:1280,hqdn3d,fps=24[v0];[1:v]scale=130:-1[lg];[v0][lg]overlay=W-w-22:22[v]" \
 -map "[v]" -c:v libx264 -preset medium -maxrate 2.0M -bufsize 4.0M -pix_fmt yuv420p vv.mp4
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 vcat.mp4)
FADEOUT=$(python3 -c "print($DUR-3)")
ffmpeg -nostdin -y -v error -f concat -safe 0 -i audio_list.txt -c:a aac -b:a 128k aonly.m4a
ffmpeg -nostdin -y -v error -i aonly.m4a -stream_loop -1 -i bgm.mp3 -filter_complex \
 "[1:a]atrim=0:$DUR,acompressor=threshold=0.25:ratio=6:attack=15:release=250:makeup=1,volume=0.14,afade=t=in:d=1.2,afade=t=out:st=$FADEOUT:d=3[bgm];[bgm]aformat=sample_rates=44100:channel_layouts=stereo[bgmf];[0:a]aformat=sample_rates=44100:channel_layouts=stereo[vc];[bgmf][vc]sidechaincompress=threshold=0.012:ratio=14:attack=30:release=350:makeup=1[bgmd];[0:a][bgmd]amix=inputs=2:duration=first:normalize=0[a]" \
 -map "[a]" -vn -c:a aac -b:a 96k afinal.m4a
ffmpeg -nostdin -y -v error -i vv.mp4 -i afinal.m4a -map 0:v -map 1:a -c:v copy -c:a copy -shortest ../out/final.mp4
FIRST=$(head -1 beats.txt)
cp img/$FIRST.png ../out/thumbnail.png
ffprobe -v error -show_entries format=duration,size -of csv=p=0 ../out/final.mp4
echo RENDER_JOB_DONE
