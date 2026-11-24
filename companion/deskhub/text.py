"""The hub's fonts only cover ASCII, so text sent to it is folded down."""
import unicodedata

_REPLACE = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "·": "-", "•": "-",
}


# False for the ESP32 board (ASCII-only fonts); the companion sets it True when only
# browsers are connected, so titles keep their own language.
UNICODE = False


def ascii_fold(s: str | None, limit: int = 120) -> str:
    if not s:
        return ""
    if UNICODE:
        return " ".join(s.split())[:limit]
    s = "".join(_REPLACE.get(c, c) for c in s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = " ".join(s.split())
    return s[:limit]
