"""The control panel's settings: read from config.toml, validated, written back without losing anything else.

    uv run python tests/test_panel_config.py
"""
import pathlib
import sys
import tempfile
import tomllib

import tomlkit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from deskhub import panel_config as pc  # noqa: E402

problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "config.example.toml"
text = EXAMPLE.read_text(encoding="utf-8")
cfg = tomllib.loads(text)
s = pc.read_settings(cfg)
check(s["pages"]["enabled"][0] == "home" and "ai" in s["pages"]["enabled"], f"pages read: {s['pages']}")
check(len(s["tiles"]) == 8 and s["tiles"][0]["action"] == "mic", "tiles read")
check(s["ai"]["agent"] == "auto" and s["weather"]["units"] == "metric", "ai and weather read")

# Round trip: change things, save, read again; comments and unknown sections survive.
s["pages"]["enabled"] = ["home", "ai", "weather", "shortcuts"]
s["pages"]["nav"] = "bottom"
s["weather"] = {"city": "Sofia, Bulgaria", "units": "metric"}
s["ai"]["agent"] = "codex"
s["codex"]["live_limits"] = True
s["tiles"].append({"label": "Output", "icon": "headphones", "color": "#3a4256", "action": "output",
                   "target": "Speakers | Headset"})
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d) / "config.toml"
    p.write_text(text, encoding="utf-8")
    pc.save(p, s)
    out = p.read_text(encoding="utf-8")
    back = tomllib.loads(out)
    got = pc.read_settings(back)
    check(got["pages"] == {"enabled": ["home", "ai", "weather", "shortcuts"], "nav": "bottom"}, f"pages saved: {got['pages']}")
    check(got["weather"]["city"] == "Sofia, Bulgaria", "city saved")
    check(got["ai"]["agent"] == "codex" and got["codex"]["live_limits"] is True, "agent and live limits saved")
    check(got["tiles"][-1]["target"] == "Speakers|Headset", f"output target tidied: {got['tiles'][-1]}")
    check(len(got["tiles"]) == 9, "tile added")
    check("# Copy to config.toml and edit." in out and "[internet]" in out and "[[calendar.feeds]]" in out,
          "comments and other sections kept")
    check((pathlib.Path(d) / "config.toml.bak").read_text(encoding="utf-8") == text, "backup is the old file")

# A mic tile keeps its state setting across a save.
doc = tomlkit.parse(text + "\n")
doc["tiles"][0]["state"] = "mic_mute"
pc.apply_settings(doc, pc.read_settings(tomllib.loads(tomlkit.dumps(doc))))
check(doc["tiles"][0].get("state") == "mic_mute", "tile state kept")

# Coordinates left in [weather] would hide a typed city: they are removed.
doc = tomlkit.parse('[weather]\nlatitude = 1.0\nlongitude = 2.0\ncity = "X"\n')
pc.apply_settings(doc, {**pc.read_settings({}), "weather": {"city": "London", "units": "imperial"}})
w = tomllib.loads(tomlkit.dumps(doc))["weather"]
check(w == {"city": "London", "units": "imperial"}, f"weather cleaned: {w}")


def rejects(change, why):
    base = pc.read_settings(cfg)
    base.update(change)
    doc = tomlkit.parse(text)
    before = tomlkit.dumps(doc)
    try:
        pc.apply_settings(doc, base)
    except ValueError:
        check(tomlkit.dumps(doc) == before, f"{why}: document changed despite the error")
        return
    check(False, f"{why}: not rejected")


tile = {"label": "T", "icon": "apps", "color": "#3a4256", "action": "keys", "target": "ctrl+c"}
rejects({"tiles": [{**tile, "label": ""}]}, "empty label")
rejects({"tiles": [{**tile, "action": "format_c"}]}, "unknown action")
rejects({"tiles": [{**tile, "icon": "nope"}]}, "unknown icon")
rejects({"tiles": [{**tile, "color": "red"}]}, "bad colour")
rejects({"tiles": [{**tile, "target": "ctrl+nonsense"}]}, "bad key combination")
rejects({"tiles": [{**tile, "action": "volume", "target": "loud"}]}, "bad volume target")
rejects({"tiles": [{**tile, "action": "output", "target": "A|A"}]}, "same output twice")
rejects({"tiles": [{**tile, "action": "output", "target": "A"}]}, "one output")
rejects({"tiles": [tile] * 17}, "too many tiles")
rejects({"pages": {"enabled": ["home", "ai", "ai"], "nav": "left"}}, "page twice")
rejects({"pages": {"enabled": ["home"], "nav": "top"}}, "bad nav")
rejects({"ai": {"agent": "gpt"}}, "bad agent")
rejects({"weather": {"city": "x" * 90, "units": "metric"}}, "long city")

m = pc.meta()
check("output" in m["actions"] and "headphones" in m["icons"], "meta lists the output action")

print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
sys.exit(1 if problems else 0)
