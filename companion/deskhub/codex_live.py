"""Opt-in: current Codex plan limits straight from OpenAI.

Off unless `[codex] live_limits = true` in config.toml. When on, the companion reads
the access token that Codex saved in ~/.codex/auth.json ($CODEX_HOME overrides the
folder) and asks https://chatgpt.com/backend-api/wham/usage for the 5-hour and weekly
percentages, the same lookup Codex's own /status uses.

- No messages are sent to Codex, so this uses no tokens and no credits.
- The token stays in memory. It is never logged, saved elsewhere, or sent to the display.
- The token is never refreshed here (that could sign Codex out). When it is rejected the
  companion waits until Codex has renewed its own sign-in (open Codex once).
- The endpoint is undocumented and may change; failures fall back quietly to the
  readings in Codex's session logs.
"""
import json
import logging
import pathlib
import time

import httpx

from .codex_usage import codex_home

log = logging.getLogger(__name__)

URL = "https://chatgpt.com/backend-api/wham/usage"


def parse_usage(data: dict, now: float) -> dict:
    """{five_hour: {pct, reset}, seven_day: {...}, updated} from the usage reply, or {}.
    Windows are told apart by their length, like the log reader does."""
    rl = data.get("rate_limit") if isinstance(data, dict) else None
    out = {}
    for w in ((rl or {}).get("primary_window"), (rl or {}).get("secondary_window")):
        if not isinstance(w, dict):
            continue
        pct, secs = w.get("used_percent"), w.get("limit_window_seconds")
        reset = w.get("reset_at")
        if not isinstance(reset, (int, float)) and isinstance(w.get("reset_after_seconds"), (int, float)):
            reset = now + w["reset_after_seconds"]
        if not all(isinstance(v, (int, float)) for v in (pct, secs, reset)) or reset <= now:
            continue
        name = "five_hour" if secs <= 6 * 3600 else "seven_day" if secs >= 86400 else None
        if name:
            out[name] = {"pct": round(float(pct), 1), "reset": int(reset)}
    if out:
        out["updated"] = int(now)
    return out


class CodexLiveLimits:
    def __init__(self, path: pathlib.Path | None = None):
        self.path = path or codex_home() / "auth.json"
        self._next = 0.0
        self._last: dict = {}
        self._bad_mtime = None   # sign-in file state that got a 401
        self._state = ""         # last logged problem, so each is logged once

    def _note(self, state: str, msg: str):
        if state != self._state:
            self._state = state
            if msg:
                log.info("live Codex limits: %s", msg)

    def _read(self):
        """(access token, account id, file mtime) from Codex's sign-in file."""
        st = self.path.stat()
        tokens = json.loads(self.path.read_text(encoding="utf-8")).get("tokens") or {}
        return tokens.get("access_token"), tokens.get("account_id"), st.st_mtime

    def _fresh(self) -> bool:
        return bool(self._last) and time.time() - self._last.get("updated", 0) < 15 * 60

    def get(self, active: bool) -> dict:
        """Latest limits as {five_hour: {pct, reset}, seven_day: {...}, updated}, or {}.
        Polls every minute while Codex is in use, every 5 minutes otherwise."""
        now = time.time()
        if now < self._next:
            return self._last
        self._next = now + (60 if active else 300)
        try:
            token, account, mtime = self._read()
        except (OSError, ValueError):
            self._note("nofile", "no Codex sign-in found; open Codex once to sign in")
            return {}
        if not token:
            self._note("notoken", "no access token in the Codex sign-in (signed in with an API key?)")
            return {}
        if self._bad_mtime == mtime:
            return self._last if self._fresh() else {}
        headers = {"Authorization": f"Bearer {token}", "User-Agent": "deskhub"}
        if account:
            headers["ChatGPT-Account-Id"] = str(account)
        try:
            r = httpx.get(URL, timeout=15, headers=headers)
        except httpx.HTTPError as e:
            self._note("neterr", f"request failed ({type(e).__name__})")
            return self._last if self._fresh() else {}
        if r.status_code in (401, 403):
            self._bad_mtime = mtime
            self._note("401", f"sign-in was rejected (HTTP {r.status_code}); paused until Codex renews it (open Codex once)")
            return {}
        if r.status_code == 429:
            self._next = now + 600
            self._note("429", "rate limited; trying again in 10 minutes")
            return self._last if self._fresh() else {}
        if r.status_code != 200:
            self._note(f"http{r.status_code}", f"HTTP {r.status_code}")
            return self._last if self._fresh() else {}
        try:
            out = parse_usage(r.json(), now)
        except ValueError:
            self._note("badjson", "unexpected response")
            return {}
        if out:
            self._note("ok", "receiving live limits")
        else:
            self._note("empty", "the reply held no limit windows")
        self._last = out
        return out
