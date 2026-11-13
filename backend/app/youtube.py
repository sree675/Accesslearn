"""Optional YouTube Data API v3 helpers. Without an API key the app keeps its seeded search links."""
import requests

from . import config
from .services import ServiceError, create_content

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def search_videos(query, max_results=3, captioned=True):
    if not config.YOUTUBE_API_KEY:
        raise ServiceError("Add YOUTUBE_API_KEY to your .env file to fetch real videos.", 400)
    params = {
        "part": "snippet", "q": query, "type": "video", "maxResults": max_results, "safeSearch": "strict",
        "videoEmbeddable": "true", "relevanceLanguage": "en", "key": config.YOUTUBE_API_KEY,
    }
    if captioned:
        params["videoCaption"] = "closedCaption"
    try:
        r = requests.get(SEARCH_URL, params=params, timeout=20)
    except requests.RequestException as e:
        raise ServiceError(f"Could not reach YouTube: {e}", 502)
    if r.status_code != 200:
        msg = r.json().get("error", {}).get("message", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        raise ServiceError(f"YouTube API error: {msg}", 502)
    return [
        {"video_id": it["id"]["videoId"], "title": it["snippet"]["title"], "channel": it["snippet"]["channelTitle"]}
        for it in r.json().get("items", [])
    ]


def fetch_and_add(conn, subject, topic, difficulty=1, max_results=3):
    """Add real captioned, embeddable videos for a topic to the catalog."""
    added = []
    for v in search_videos(f"{topic} {subject} lesson for students", max_results, captioned=True):
        added.append(
            create_content(
                conn,
                dict(
                    title=f"{v['title']} ({v['channel']})", subject=subject, topic=topic, difficulty=difficulty,
                    format="video", duration_min=8, tags=f"{subject.lower()} {topic.lower()} video youtube",
                    description=f"YouTube video on {topic} from {v['channel']}.",
                    url=f"https://www.youtube.com/watch?v={v['video_id']}", video_id=v["video_id"],
                    has_captions=1, has_transcript=1, source="youtube",
                ),
            )
        )
    return added


def enrich_seed_videos(conn, limit=20):
    """Swap the seeded YouTube search links for real video IDs (captioned and embeddable)."""
    rows = conn.execute(
        "SELECT id, youtube_query FROM content WHERE format='video' AND video_id='' AND youtube_query!='' LIMIT ?", (limit,)
    ).fetchall()
    updated = 0
    for r in rows:
        found = search_videos(r["youtube_query"], max_results=1, captioned=True)
        if found:
            vid = found[0]["video_id"]
            conn.execute(
                "UPDATE content SET video_id=?, url=?, source='youtube' WHERE id=?",
                (vid, f"https://www.youtube.com/watch?v={vid}", r["id"]),
            )
            updated += 1
    conn.commit()
    return {"updated": updated, "checked": len(rows)}
