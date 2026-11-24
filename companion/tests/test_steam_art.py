"""Game covers for browsers: right sizes as JPEG, only for games Steam reported, art fetched once.

    uv run python tests/test_steam_art.py
"""
import io

from PIL import Image

from deskhub.steam import Steam

problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


def jpeg(w, h, color=(200, 40, 40)):
    out = io.BytesIO()
    Image.new("RGB", (w, h), color).save(out, "JPEG")
    return out.getvalue()


calls = []
s = Steam()
s._snap = {"type": "steam", "found": True, "playing": {"appid": 10, "name": "Now"},
           "recent": [{"appid": 20, "name": "Then"}, {"appid": 30, "name": "No portrait"}]}


def fake_fetch(appid, portrait):
    calls.append((appid, portrait))
    if appid == 30 and portrait:
        return None            # only a wide header exists
    return jpeg(600, 900) if portrait else jpeg(460, 215)


s._fetch_art = fake_fetch

head = s.web_art(10, "header")
im = Image.open(io.BytesIO(head))
check(im.format == "JPEG" and im.size == (340, 159), f"header is a 340x159 JPEG: {im.format} {im.size}")
cover = Image.open(io.BytesIO(s.web_art(20, "cover")))
check(cover.size == (200, 300), f"cover is 200x300: {cover.size}")
wide_only = Image.open(io.BytesIO(s.web_art(30, "cover")))
check(wide_only.size == (200, 300), f"a cover made from a wide header is still 200x300: {wide_only.size}")

n = len(calls)
s.web_art(10, "header")
s.web_art(20, "cover")
check(len(calls) == n, "a game's art is fetched once, then served from memory")

check(s.web_art(999, "header") is None, "a game Steam did not report is refused")
check(s.web_art(10, "../../etc") is None, "an unknown kind is refused")
check(not any(c[0] == 999 for c in calls), "nothing was fetched for the refused game")

# art that cannot be fetched: None, and no retry storm
s2 = Steam()
s2._snap = {"type": "steam", "found": True, "playing": None, "recent": [{"appid": 40, "name": "Lost"}]}
tries = []
s2._fetch_art = lambda appid, portrait: tries.append(1) or None
check(s2.web_art(40, "cover") is None, "missing art gives None")
t = len(tries)
check(s2.web_art(40, "cover") is None and len(tries) == t, "a failed fetch is not retried at once")

# a game that left the snapshot is forgotten
s._snap = {"type": "steam", "found": True, "playing": None, "recent": [{"appid": 20, "name": "Then"}]}
s.web_art(20, "cover")
check(all(k[0] == 20 for k in s._web), f"art of games no longer shown is dropped: {list(s._web)}")

print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
raise SystemExit(1 if problems else 0)
