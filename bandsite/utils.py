import json
import re
from urllib.parse import parse_qs, urlparse

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def youtube_id(url):
    """Extracts the video id from common YouTube links. Returns None if none is recognised."""
    if not url:
        return None
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlparse(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]

    video = None
    if host == "youtu.be":
        video = parts.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if parts.path == "/watch":
            video = (parse_qs(parts.query).get("v") or [None])[0]
        else:
            match = re.match(r"^/(?:embed|shorts|live|v)/([^/?#]+)", parts.path)
            if match:
                video = match.group(1)
    return video if video and _VIDEO_ID.match(video) else None


def is_safe_redirect(target):
    if not target or "\\" in target:
        return False
    parts = urlparse(target)
    return not parts.scheme and not parts.netloc and target.startswith("/") and not target.startswith("//")


def _number(value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("not a number")
    if not minimum <= value <= maximum:  # also rejects NaN
        raise ValueError("out of range")
    return round(float(value), 4)


def _color(value):
    if not isinstance(value, str) or not _COLOR.match(value):
        raise ValueError("invalid color")
    return value


def clean_annotations(raw, max_bytes=2_000_000):
    """Validates notes and drawings coming from the browser and rebuilds clean JSON from them.

    Returns the JSON string, or None if the data is invalid or too large.
    """
    try:
        if not isinstance(raw, dict) or not isinstance(raw.get("pages", {}), dict):
            raise ValueError("structure")
        clean = {}
        for key, page in raw.get("pages", {}).items():
            if not (isinstance(key, str) and key.isdigit() and 1 <= int(key) <= 1000):
                raise ValueError("page number")
            if not isinstance(page, dict):
                raise ValueError("page")
            strokes, texts = [], []
            raw_strokes = page.get("strokes", [])
            raw_texts = page.get("texts", [])
            if not isinstance(raw_strokes, list) or not isinstance(raw_texts, list):
                raise ValueError("lists")
            for s in raw_strokes[:5000]:
                if s.get("tool") not in ("pen", "marker"):
                    raise ValueError("tool")
                points = s.get("points")
                if not isinstance(points, list) or not 1 <= len(points) <= 20000:
                    raise ValueError("points")
                strokes.append(
                    {
                        "tool": s["tool"],
                        "color": _color(s.get("color")),
                        "width": _number(s.get("width"), 0.0005, 0.2),
                        "points": [[_number(p[0], -0.1, 1.1), _number(p[1], -0.1, 1.1)] for p in points],
                    }
                )
            for t in raw_texts[:500]:
                text = t.get("text")
                if not isinstance(text, str):
                    raise ValueError("text")
                text = text[:1000]
                if not text.strip():
                    continue
                texts.append(
                    {
                        "x": _number(t.get("x"), -0.1, 1.1),
                        "y": _number(t.get("y"), -0.1, 1.1),
                        "text": text,
                        "color": _color(t.get("color")),
                        "size": _number(t.get("size"), 0.005, 0.1),
                    }
                )
            if strokes or texts:
                clean[key] = {"strokes": strokes, "texts": texts}
        result = json.dumps({"pages": clean}, separators=(",", ":"), ensure_ascii=False)
        if len(result.encode("utf-8")) > max_bytes:
            raise ValueError("too large")
        return result
    except (ValueError, TypeError, AttributeError, KeyError, IndexError):
        return None
