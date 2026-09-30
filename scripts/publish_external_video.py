"""Publish an externally-produced video (Drive-staged story video) to
YouTube Shorts, Instagram Reels and Facebook Reels with exact metadata.
Driven entirely by environment variables - see .github/workflows/publish_drive_video.yml."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.publishing.youtube_uploader import upload_video
from src.publishing.instagram_publisher import publish_reel as ig_publish_reel
from src.publishing.facebook_publisher import publish_reel as fb_publish_reel
from src.publishing.telegram_notifier import send_completion_notification
from src.utils.logger import get_logger

log = get_logger(__name__, phase="external_publish")


def main() -> int:
    video_path = Path(os.environ.get("VIDEO_PATH", "assets/incoming.mp4"))
    if not video_path.is_file() or video_path.stat().st_size == 0:
        log.error("Video file missing or empty: %s", video_path)
        return 1
    title = os.environ["YT_TITLE"]
    description = os.environ.get("YT_DESCRIPTION", "")
    hashtags = [t.lstrip("#") for t in os.environ.get("HASHTAGS", "Shorts").replace(",", " ").split()]
    privacy = os.environ.get("PRIVACY", "private")

    log.info("Publishing %s (%s) - title: %s", video_path, privacy, title)
    yt_url = None
    if os.environ.get("PUBLISH_YOUTUBE", "true").lower() != "false":
        yt_url = upload_video(video_path, title, description, hashtags, privacy=privacy)
    else:
        log.info("PUBLISH_YOUTUBE=false - skipping YouTube (already live elsewhere)")
    ig_url = None
    if os.environ.get("PUBLISH_INSTAGRAM", "true").lower() != "false":
        ig_url = ig_publish_reel(video_path, title, description, hashtags)
    else:
        log.info("PUBLISH_INSTAGRAM=false - skipping Instagram")
    fb_url = None
    if os.environ.get("PUBLISH_FACEBOOK", "true").lower() != "false":
        fb_url = fb_publish_reel(video_path, title, description, hashtags)
    else:
        log.info("PUBLISH_FACEBOOK=false - skipping Facebook")

    send_completion_notification(
        title=title,
        thesis=os.environ.get("THESIS", "Externally staged story video"),
        youtube_url=yt_url,
        instagram_url=ig_url,
        facebook_url=fb_url,
        run_stats={"source": os.environ.get("VIDEO_SOURCE", "external"), "privacy": privacy},
    )
    results = {"youtube": yt_url, "instagram": ig_url, "facebook": fb_url}
    print("RESULTS " + repr(results))
    return 0 if any(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
