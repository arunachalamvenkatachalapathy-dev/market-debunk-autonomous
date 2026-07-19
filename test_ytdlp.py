import yt_dlp
ydl_opts = {'extract_flat': True, 'quiet': True}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info('https://www.youtube.com/@PRSundar64/videos', download=False)
    latest_video = info['entries'][0]
    print(latest_video['title'])
