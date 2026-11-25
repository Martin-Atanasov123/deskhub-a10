"""The control panel's server side: only this PC may open it or change anything, and a change really lands in
config.toml. (The settings logic itself is tested in test_panel_config.py.)

    uv run python tests/test_panel.py
"""
import asyncio
import json
import pathlib
import sys
import tempfile
import tomllib

import aiohttp

from deskhub.panel import Panel
from deskhub.web_server import WebHub

problems = []
EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "config.example.toml"


def check(cond, msg):
    if not cond:
        problems.append(msg)


async def main():
    with tempfile.TemporaryDirectory() as d:
        cfg = pathlib.Path(d) / "config.toml"
        cfg.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        restarts = []

        async def outputs():
            return ["Speakers", "Headset"]

        class Startup:
            on = False

            def installed(self):
                return self.on

            def install(self):
                self.on = True

            def remove(self):
                self.on = False

        startup = Startup()
        panel = Panel(cfg, outputs, lambda: restarts.append(1), startup=startup, version="9.9")

        async def snapshot():
            return []

        async def command(m):
            pass

        hub = WebHub(token="secret-code", snapshot=snapshot, command=command, art=lambda i: None,
                     host="127.0.0.1", port=0, panel=panel)
        check(await hub.start(), "hub did not start")
        base = f"http://127.0.0.1:{hub.port}"
        mine = {"Origin": base, "X-Panel": "1", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as http:
            r = await http.get(f"{base}/panel")
            check(r.status == 200 and "DeskHub" in await r.text(), f"panel page: {r.status}")
            r = await http.get(f"{base}/api/panel/state")
            st = await r.json()
            check(r.status == 200 and st["version"] == "9.9" and st["outputs"] == ["Speakers", "Headset"], f"state: {r.status}")
            check(st["pair"]["url"].endswith("#t=secret-code") and "<svg" in st["pair"]["qr"], "state holds the pairing address and QR")
            check(st["settings"]["tiles"][0]["action"] == "mic" and st["startup"] is False, "state holds the settings")

            # A page on another site (DNS rebinding) is refused, even from this PC.
            r = await http.get(f"{base}/panel", headers={"Host": "evil.example"})
            check(r.status == 403, f"foreign Host got {r.status}")
            r = await http.get(f"{base}/api/panel/state", headers={"Host": "evil.example"})
            check(r.status == 403, f"foreign Host on state got {r.status}")

            # Changes need the panel's own page: same Origin and the header.
            body = json.dumps(st["settings"])
            for headers, why in (({"Content-Type": "application/json"}, "no headers"),
                                 ({**mine, "Origin": "http://evil.example"}, "foreign Origin"),
                                 ({"Origin": base, "Content-Type": "application/json"}, "no X-Panel header")):
                r = await http.post(f"{base}/api/panel/save", data=body, headers=headers)
                check(r.status == 403, f"save with {why} got {r.status}")
            r = await http.post(f"{base}/api/panel/restart", data="{}", headers={"Content-Type": "application/json"})
            check(r.status == 403 and not restarts, "restart without the headers")
            r = await http.post(f"{base}/api/panel/startup", data='{"enabled": true}', headers={"Content-Type": "application/json"})
            check(r.status == 403 and not startup.on, "startup without the headers")

            # A real change.
            st["settings"]["weather"]["city"] = "Sofia"
            st["settings"]["ai"]["agent"] = "codex"
            r = await http.post(f"{base}/api/panel/save", data=json.dumps(st["settings"]), headers=mine)
            check(r.status == 200, f"save got {r.status}: {await r.text()}")
            got = tomllib.loads(cfg.read_text(encoding="utf-8"))
            check(got["weather"]["city"] == "Sofia" and got["ai"]["agent"] == "codex", "the change reached config.toml")
            # A bad change is refused and leaves the file alone.
            before = cfg.read_text(encoding="utf-8")
            bad = {**st["settings"], "ai": {"agent": "gpt"}}
            r = await http.post(f"{base}/api/panel/save", data=json.dumps(bad), headers=mine)
            check(r.status == 400 and (await r.json())["ok"] is False and cfg.read_text(encoding="utf-8") == before,
                  "a bad change is refused")
            r = await http.post(f"{base}/api/panel/save", data="not json", headers=mine)
            check(r.status == 400, f"bad JSON got {r.status}")

            r = await http.post(f"{base}/api/panel/startup", data='{"enabled": true}', headers=mine)
            check(r.status == 200 and startup.on, "start with Windows turned on")
            r = await http.post(f"{base}/api/panel/restart", data="{}", headers=mine)
            await asyncio.sleep(0.8)
            check(r.status == 200 and restarts == [1], f"restart asked for: {restarts}")

            # The phone's own pages still work, and the panel page is not among its static files.
            r = await http.get(f"{base}/")
            check(r.status == 200, "the phone page still loads")
            r = await http.get(f"{base}/panel_web/index.html")
            check(r.status == 404, f"panel files are not served as static files: {r.status}")
        await hub.stop()


asyncio.run(main())
print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
sys.exit(1 if problems else 0)
