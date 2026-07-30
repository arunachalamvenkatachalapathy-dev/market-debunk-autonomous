import urllib.request
import re

channels = [
    {"name": "Money Pechu", "url": "https://www.youtube.com/channel/UCqhL6vNCwYLC9_jePXOIvBg"},
    {"name": "Makkal Pechu", "url": "https://www.youtube.com/@MakkalPechu"},
    {"name": "Rupee Driver", "url": "https://www.youtube.com/@RupeeDriver"},
    {"name": "Trade Achievers", "url": "https://www.youtube.com/@TRADEACHIEVERS"},
    {"name": "Money Purse", "url": "https://www.youtube.com/@MoneyPurse"}
]

req_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

for ch in channels:
    url = ch["url"]
    try:
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            # Extract channel ID
            match = re.search(r'\"channelId\":\"(UC[a-zA-Z0-9_-]{22})\"', html)
            if match:
                ch["id"] = match.group(1)
            else:
                match2 = re.search(r'https://www.youtube.com/channel/(UC[a-zA-Z0-9_-]{22})', html)
                if match2:
                    ch["id"] = match2.group(1)
                else:
                    ch["id"] = None
    except Exception as e:
        print(f"Error fetching {ch['name']}: {e}")
        ch["id"] = None

print("RESOLVED CHANNELS:")
for ch in channels:
    print(f"{ch['name']}: ID={ch['id']} -> RSS=https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}")
