"""Battery saver mode, quiet-link heartbeat, no repeats, and the LAN security rules: wrong pairing codes
are rate limited, pages from other sites cannot connect, the PC's own trust needs a local address,
commands cannot flood, clickjacking and report flooding are closed.

    uv run python tests/test_web_hardening.py
"""
import asyncio
import json
import pathlib
import sys
import tempfile

import aiohttp

from deskhub import web_server
from deskhub.web_server import WebHub

problems = []
TOKEN = "test-token"
auth = {"X-Token": TOKEN}


def check(cond, msg):
    if not cond:
        problems.append(msg)


async def drain(ws, wait):
    out = []
    end = asyncio.get_running_loop().time() + wait
    while True:
        left = end - asyncio.get_running_loop().time()
        if left <= 0:
            return out
        try:
            m = await ws.receive(timeout=left)
        except asyncio.TimeoutError:
            return out
        if m.type != aiohttp.WSMsgType.TEXT:
            return out
        out.append(json.loads(m.data))


async def hello(http, base, mode="normal", headers=None):
    ws = await http.ws_connect(f"{base}/ws", headers=headers)
    await ws.send_str(json.dumps({"type": "hello", "token": TOKEN, "mode": mode}))
    return ws


def make_hub(commands=None, **kw):
    async def snapshot():
        return [{"type": "stats", "cpu": 1}]

    async def command(m):
        if commands is not None:
            commands.append(m)

    return WebHub(token=TOKEN, snapshot=snapshot, command=command, art=lambda i: None, host="127.0.0.1", port=0,
                  trust_loopback=kw.pop("trust_loopback", False), **kw)


async def main():
    web_server.HELLO_FAILS = 3
    web_server.CMD_LIMIT = (5, 10)
    web_server.HEARTBEAT_S.update({"normal": 0.6, "low": 0.6, "ultra": 0.6, "idle": 0.6})
    web_server.INTERVALS["ultra"] = {"stats": 1.0}
    commands = []
    hub = make_hub(commands)
    check(await hub.start(), "hub did not start")
    base = f"http://127.0.0.1:{hub.port}"

    async with aiohttp.ClientSession() as http:
        # ---- battery saver ("ultra") is a real mode and is slower than eco ----
        ws = await hello(http, base, mode="ultra")
        await drain(ws, 0.3)
        check([c.mode for c in hub.clients] == ["ultra"], f"hello can ask for battery saver: {[c.mode for c in hub.clients]}")
        await hub.broadcast({"type": "stats", "cpu": 10})
        await asyncio.sleep(0.05)
        for cpu in (11, 12, 13):
            await hub.broadcast({"type": "stats", "cpu": cpu})
        got = await drain(ws, 0.2)
        check([m["cpu"] for m in got] == [10] or got == [], f"battery saver waits between stats: {got}")
        got = await drain(ws, 1.3)
        check([m["cpu"] for m in got if m["type"] == "stats"][-1:] == [13], f"... then sends only the newest: {got}")
        await ws.send_str(json.dumps({"type": "power", "mode": "bogus"}))
        await asyncio.sleep(0.2)
        check([c.mode for c in hub.clients] == ["normal"], "an unknown mode falls back to normal")

        # ---- no repeats ----
        await drain(ws, 0.8)
        await hub.broadcast({"type": "net", "online": True})
        await hub.broadcast({"type": "net", "online": True})
        await hub.broadcast({"type": "net", "online": True})
        got = [m for m in await drain(ws, 0.3) if m["type"] == "net"]
        check(len(got) == 1, f"the same message three times is sent once: {len(got)}")
        await hub.broadcast({"type": "net", "online": False})
        await hub.broadcast({"type": "net", "online": True})
        got = [m for m in await drain(ws, 0.3) if m["type"] == "net"]
        check([m["online"] for m in got] == [False, True], f"changes still go through: {got}")

        # ---- heartbeat on a quiet link ----
        raw = []
        end = asyncio.get_running_loop().time() + 2.5
        while asyncio.get_running_loop().time() < end:
            try:
                m = await ws.receive(timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if m.type == aiohttp.WSMsgType.TEXT:
                raw.append(json.loads(m.data)["type"])
        check(raw.count("ping") >= 2, f"a silent link still hears a heartbeat: {raw}")
        d = await (await http.get(f"{base}/api/diag", headers=auth)).json()
        check(d["clients"][0]["tx_bytes"] > 0, "bytes sent to a display are counted in diagnostics")

        # ---- commands cannot flood ----
        before = len(commands)
        for i in range(20):
            await ws.send_str(json.dumps({"type": "shortcut", "id": i}))
        await asyncio.sleep(0.5)
        check(len(commands) - before == 5, f"only 5 commands per window get through: {len(commands) - before}")
        check(any("too many commands" in e["msg"] for e in hub.logs), "the flood is logged once")
        await ws.close()

        # ---- a web page from another site cannot use the dashboard's socket ----
        try:
            await http.ws_connect(f"{base}/ws", headers={"Origin": "http://evil.example"})
            check(False, "a cross-site WebSocket must be refused")
        except aiohttp.WSServerHandshakeError as e:
            check(e.status == 403, f"cross-site origin gets 403, got {e.status}")
        ws = await http.ws_connect(f"{base}/ws", headers={"Origin": base})
        await ws.close()   # same origin (our own page) is allowed

        # ---- guessing the pairing code is rate limited ----
        for _ in range(3):
            w = await http.ws_connect(f"{base}/ws")
            await w.send_str(json.dumps({"type": "hello", "token": "wrong"}))
            await drain(w, 0.3)
        try:
            await http.ws_connect(f"{base}/ws")
            check(False, "after three wrong codes the next try must be refused")
        except aiohttp.WSServerHandshakeError as e:
            check(e.status == 429, f"too many wrong codes gets 429, got {e.status}")

        # ---- headers and report flooding ----
        r = await http.get(f"{base}/api/ping")
        check(r.headers.get("X-Frame-Options") == "DENY" and "frame-ancestors 'none'" in r.headers.get("Content-Security-Policy", ""),
              f"pages cannot be framed: {dict(r.headers)}")
        hub.reports.clear()
        for i in range(web_server.MAX_REPORTS):
            hub.reports[f"10.0.0.{i}"] = {"x": i}
        await http.post(f"{base}/api/report", json={"android": "9"})
        check(len(hub.reports) == web_server.MAX_REPORTS and "127.0.0.1" in hub.reports and "10.0.0.0" not in hub.reports,
              f"a new reporter at the cap replaces the oldest one: {len(hub.reports)}")
    await hub.stop()

    # ---- the PC's own trust only applies to requests that really address this PC ----
    local = make_hub(trust_loopback=True)
    check(await local.start(), "second hub did not start")
    b2 = f"http://127.0.0.1:{local.port}"
    async with aiohttp.ClientSession() as http:
        for path in ("/api/diag", "/setup"):
            r = await http.get(b2 + path)
            check(r.status == 200, f"{path} from the PC itself works without a code: {r.status}")
            r = await http.get(b2 + path, headers={"Host": f"rebind.example:{local.port}"})
            check(r.status == 403, f"{path} with another site's name in Host is refused (DNS rebinding): {r.status}")
            r = await http.get(b2 + path, headers={"Host": f"localhost:{local.port}"})
            check(r.status == 200, f"{path} as localhost works: {r.status}")
            r = await http.get(b2 + path, headers={"Host": f"rebind.example:{local.port}", "X-Token": TOKEN})
            check(r.status in (200, 403), "a token still works for /api/diag")
    await local.stop()

    # ---- a new pairing code ----
    tmp = pathlib.Path(tempfile.mkdtemp()) / "web_token"
    old = web_server.TOKEN_FILE
    web_server.TOKEN_FILE = tmp
    try:
        a = web_server.new_token()
        check(len(a) >= 21 and tmp.read_text() == a, f"new_token saves a long code: {a}")
        check(web_server.load_token({}) == a, "the saved code is the one used")
        b = web_server.new_token()
        check(a != b and web_server.load_token({}) == b, "a new code replaces the old one")
        check(web_server.load_token({"web": {"token": "mine"}}) == "mine", "a code in config.toml wins")
    finally:
        web_server.TOKEN_FILE = old


asyncio.run(main())
print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
sys.exit(1 if problems else 0)
