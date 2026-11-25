"""What the control panel can change in config.toml, and how it is written back.

`read_settings` turns the parsed config into the plain dict the panel shows; `apply_settings` checks a dict from
the panel and writes it into a tomlkit document (so every comment and every setting the panel doesn't know about
stays as it was). Both are pure, so they are tested without a window or a server.
"""
import pathlib
import re

import tomlkit

from .pages import ALL_PAGES, NAV_POSITIONS, PAGE_LABELS, enabled_pages, nav_position
from .shortcuts import MAX_TILES, combo_problem
from .shortcuts_cli import ACTIONS, ICONS

AGENTS = ("auto", "claude", "codex")
UNITS = ("metric", "imperial")
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def read_settings(cfg: dict) -> dict:
    weather = cfg.get("weather") or {}
    return {
        "pages": {"enabled": enabled_pages(cfg), "nav": nav_position(cfg)},
        "weather": {"city": str(weather.get("city", "")), "units": str(weather.get("units", "metric")).lower()},
        "ai": {"agent": str((cfg.get("ai") or {}).get("agent", "auto"))},
        "claude": {"live_limits": bool((cfg.get("claude") or {}).get("live_limits", False))},
        "codex": {"live_limits": bool((cfg.get("codex") or {}).get("live_limits", False))},
        "tiles": [{"label": str(t.get("label", "")), "icon": str(t.get("icon", "apps")),
                   "color": str(t.get("color", "#3a4256")), "action": str(t.get("action", "")),
                   "target": str(t.get("target", ""))}
                  for t in (cfg.get("tiles") or [])[:MAX_TILES]],
    }


def meta() -> dict:
    """The fixed choices the panel offers."""
    return {
        "pages": [{"id": p, "label": PAGE_LABELS.get(p, p.title())} for p in ALL_PAGES if p != "home"],
        "navs": list(NAV_POSITIONS), "agents": list(AGENTS), "units": list(UNITS), "icons": ICONS,
        "actions": {k: {"what": v[0], "hint": v[1], "choices": v[2]} for k, v in ACTIONS.items()},
        "max_tiles": MAX_TILES,
    }


def _table(doc, name: str):
    if name not in doc:
        doc[name] = tomlkit.table()
    return doc[name]


def check_tile(t: dict) -> dict:
    """A cleaned tile, or ValueError naming what is wrong with it."""
    label = str(t.get("label", "")).strip()
    action = str(t.get("action", ""))
    target = str(t.get("target", "")).strip()
    if not label or len(label) > 30:
        raise ValueError("A button needs a label of 1 to 30 characters.")
    if action not in ACTIONS:
        raise ValueError(f"{label}: unknown action {action!r}.")
    icon = str(t.get("icon", "apps"))
    if icon not in ICONS:
        raise ValueError(f"{label}: no icon called {icon!r}.")
    color = str(t.get("color", "#3a4256"))
    if not _HEX.fullmatch(color):
        raise ValueError(f"{label}: the colour must look like #3a4256.")
    choices = ACTIONS[action][2]
    if choices:
        if target not in choices:
            raise ValueError(f"{label}: pick one of {', '.join(choices)}.")
    elif action == "output":
        parts = [p.strip() for p in target.split("|")]
        if len(parts) != 2 or not all(parts) or parts[0].lower() == parts[1].lower():
            raise ValueError(f"{label}: pick two different sound outputs.")
        target = "|".join(parts)
    elif ACTIONS[action][1]:   # keys / run / open need a value
        if not target:
            raise ValueError(f"{label}: this button needs a value.")
        if action == "keys":
            problem = combo_problem(target)
            if problem:
                raise ValueError(f"{label}: {problem}.")
    else:
        target = ""
    return {"label": label, "icon": icon, "color": color.lower(), "action": action, "target": target}


def apply_settings(doc, s: dict) -> None:
    """Write the panel's settings into the tomlkit document `doc`. Raises ValueError, changing nothing,
    when something is not valid."""
    pages = s.get("pages") or {}
    enabled = [p for p in pages.get("enabled", []) if p in ALL_PAGES and p != "home"]
    if len(set(enabled)) != len(enabled):
        raise ValueError("A page is listed twice.")
    nav = pages.get("nav", "left")
    if nav not in NAV_POSITIONS:
        raise ValueError(f"The navigation bar goes {', '.join(NAV_POSITIONS)}.")
    weather = s.get("weather") or {}
    city = str(weather.get("city", "")).strip()
    units = weather.get("units", "metric")
    if units not in UNITS or len(city) > 80:
        raise ValueError("Weather: check the place and the units.")
    agent = (s.get("ai") or {}).get("agent", "auto")
    if agent not in AGENTS:
        raise ValueError("AI agent: auto, claude or codex.")
    tiles = [check_tile(t) for t in (s.get("tiles") or [])]
    if len(tiles) > MAX_TILES:
        raise ValueError(f"At most {MAX_TILES} buttons.")

    p = _table(doc, "pages")
    p["enabled"] = ["home"] + enabled
    p["nav"] = nav
    w = _table(doc, "weather")
    for k in ("latitude", "longitude"):
        if k in w:
            del w[k]   # a typed place wins; coordinates left behind would hide it
    if city:
        w["city"] = city
    elif "city" in w:
        del w["city"]
    w["units"] = units
    _table(doc, "ai")["agent"] = agent
    _table(doc, "claude")["live_limits"] = bool((s.get("claude") or {}).get("live_limits"))
    _table(doc, "codex")["live_limits"] = bool((s.get("codex") or {}).get("live_limits"))

    old = {str(t.get("label")): t for t in (doc["tiles"] if "tiles" in doc else [])}
    new = tomlkit.aot()
    for t in tiles:
        row = tomlkit.table()
        for k, v in t.items():
            row[k] = v
        state = old.get(t["label"], {}).get("state") if old.get(t["label"]) is not None else None
        if state is not None:
            row["state"] = state   # keep a tile's "lights up while muted" setting
        new.append(row)
    if "tiles" in doc:
        del doc["tiles"]
    doc["tiles"] = new


def save(path: pathlib.Path, s: dict) -> None:
    """Validate, then rewrite config.toml (the old file stays as config.toml.bak)."""
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    apply_settings(doc, s)
    text = tomlkit.dumps(doc)
    path.with_name(path.name + ".bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
