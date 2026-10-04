"""ลิงก์รีวิว YouTube

- ถ้าตั้ง YOUTUBE_API_KEY: ใช้ YouTube Data API v3 ดึง 3 คลิปรีวิวภาษาไทยที่เกี่ยวข้อง (1 ครั้ง = 100 หน่วยโควต้า จากวันละ 10,000)
- ถ้าไม่ตั้ง: ให้ลิงก์หน้าค้นหา YouTube แทน (ใช้ได้เสมอ ไม่เสียโควต้า)
"""
from __future__ import annotations

import html

import requests

from config import secret
from scoring_service import youtube_search_url

API = "https://www.googleapis.com/youtube/v3/search"


def _key() -> str:
    return secret("YOUTUBE_API_KEY")


def has_youtube_key() -> bool:
    return bool(_key())


def review_videos(name: str, n: int = 3, session=None) -> list[dict]:
    """คืน [{title, channel, url, thumbnail}] ; ว่างถ้าไม่มี key หรือเรียกไม่สำเร็จ"""
    key = _key()
    if not key:
        return []
    http = session or requests
    try:
        r = http.get(API, params={"part": "snippet", "q": f"รีวิว {name}", "type": "video", "maxResults": n,
                                  "relevanceLanguage": "th", "regionCode": "TH", "safeSearch": "moderate", "key": key},
                     timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception:
        return []
    out = []
    for it in items:
        vid = (it.get("id") or {}).get("videoId")
        sn = it.get("snippet") or {}
        if not vid:
            continue
        out.append({"title": html.unescape(sn.get("title", "")), "channel": html.unescape(sn.get("channelTitle", "")),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "thumbnail": ((sn.get("thumbnails") or {}).get("medium") or {}).get("url")})
    return out


def search_link(name: str) -> str:
    return youtube_search_url(name)
