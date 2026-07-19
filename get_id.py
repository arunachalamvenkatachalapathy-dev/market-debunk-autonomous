import urllib.request, re
html = urllib.request.urlopen('https://www.youtube.com/@PRSundar64').read().decode('utf-8')
match = re.search(r'channelId":"(UC[^"]+)', html)
if match:
    print(match.group(1))
else:
    print("Not found")
