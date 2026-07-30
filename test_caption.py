import requests
import xml.etree.ElementTree as ET

def get_video_content_or_description(video_id):
    # Try RSS feed media:description
    url = "https://www.youtube.com/feeds/videos.xml?channel_id=UC7fQFl37yAOaPaoxQm-TqSA"
    r = requests.get(url, timeout=10)
    root = ET.fromstring(r.content)
    ns = {
        'yt': 'http://www.youtube.com/xml/schemas/2015',
        'default': 'http://www.w3.org/2005/Atom',
        'media': 'http://search.yahoo.com/mrss/'
    }
    for entry in root.findall("default:entry", ns):
        v_id = entry.findtext("yt:videoId", namespaces=ns)
        if v_id == video_id:
            group = entry.find("media:group", ns)
            desc = group.findtext("media:description", namespaces=ns) if group is not None else ""
            if desc and len(desc.strip()) > 50:
                print(f"Found RSS description for {video_id}, len: {len(desc)}")
                print("Preview:", desc[:200].encode('ascii', 'ignore').decode('ascii'))
                return desc
    return None

get_video_content_or_description("V7tdvqxx2lc")
