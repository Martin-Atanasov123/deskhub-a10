"""The browser display's server: pairing, replay on connect, low-power coalescing,
command whitelist, token checks. No phone needed; a local WebSocket client stands in.

    uv run python tests/test_web.py
"""
import asyncio
import json
import sys

import aiohttp

from deskhub import web_server
from deskhub.web_server import WebHub

problems = []
TOKEN = "test-token"


def check(cond, msg):
    if not cond:
        problems.append(msg)


async def recv_all(ws, wait: float) -> list[dict]:
    """Every JSON message that arrives within `wait` seconds."""
    out = []
    end = asyncio.get_running_loop().time() + wait
    while True:
        left = end - asyncio.get_running_loop().time()
        if left <= 0:
            return out
        try:
            msg = await ws.receive(timeout=left)
        except asyncio.TimeoutError:
            return out
        if msg.type == aiohttp.WSMsgType.TEXT:
            d = json.loads(msg.data)
            if d.get("type") != "ping":        # the heartbeat is not data
                out.append(d)
        else:
            return out


async def connect(http, base, token=TOKEN, mode="normal"):
    ws = await http.ws_connect(f"{base}/ws")
    await ws.send_str(json.dumps({"type": "hello", "token": token, "mode": mode}))
    return ws


async def main():
    web_server.HELLO_TIMEOUT_S = 0.6
    commands = []

    async def snapshot():
        return [{"type": "layout", "pages": ["home"]}, {"type": "stats", "cpu": 1}]

    async def command(m):
        commands.append(m)

    hub = WebHub(token=TOKEN, snapshot=snapshot, command=command,
                 art=lambda i: (b"JPEGDATA", "image/jpeg") if i == 5 else None,
                 steam_art=lambda appid, kind: (b"COVER", "image/jpeg") if (appid, kind) == (7, "cover") else None,
                 host="127.0.0.1", port=0, trust_loopback=False,
                 intervals={"normal": {}, "low": {"stats": 0.8, "media": 0.8}})
    check(await hub.start(), "hub did not start")
    base = f"http://127.0.0.1:{hub.port}"
    auth = {"X-Token": TOKEN}

    async with aiohttp.ClientSession() as http:
        # ---- HTTP ----
        r = await http.get(f"{base}/api/ping")
        check(r.status == 200 and (await r.json())["ok"], "ping")
        for path in ("/api/diag", "/art/5"):
            r = await http.get(base + path)
            check(r.status == 403, f"{path} without a token must be 403, got {r.status}")
        r = await http.get(f"{base}/art/5", headers=auth)
        check(r.status == 200 and await r.read() == b"JPEGDATA" and r.content_type == "image/jpeg", "art with token")
        r = await http.get(f"{base}/art/6", headers=auth)
        check(r.status == 404, "unknown art id is 404")
        r = await http.get(f"{base}/art/abc", headers=auth)
        check(r.status == 404, "bad art id is 404")
        r = await http.get(f"{base}/steam/7/cover")
        check(r.status == 403, f"game cover without a token must be 403, got {r.status}")
        r = await http.get(f"{base}/steam/7/cover", headers=auth)
        check(r.status == 200 and await r.read() == b"COVER", "game cover with token")
        for bad in ("/steam/8/cover", "/steam/7/header", "/steam/x/cover"):
            r = await http.get(base + bad, headers=auth)
            check(r.status == 404, f"{bad} is 404, got {r.status}")
        r = await http.get(f"{base}/%2e%2e/%2e%2e/pyproject.toml")
        check(r.status != 200, f"path traversal must not serve files, got {r.status}")
        r = await http.get(f"{base}/setup")
        check(r.status in (200, 403), "setup answers")   # 127.0.0.1 is allowed here
        r = await http.post(f"{base}/api/log", json={"level": "warn", "msg": "x" * 1000})
        check(r.status == 200, "unpaired phones can still report a problem")
        check(hub.logs[-1]["authed"] is False and len(hub.logs[-1]["msg"]) <= 300, "unauth log is marked and truncated")
        r = await http.post(f"{base}/api/report", json={"android": "9", "chrome": "100"})
        check(r.status == 200 and "127.0.0.1" in hub.reports, "compat report stored")
        r = await http.post(f"{base}/api/report", data=b"nope")
        check(r.status == 400, "bad report body is 400")

        # ---- pairing ----
        ws = await connect(http, base, token="wrong")
        msgs = await recv_all(ws, 1)
        check(msgs == [{"type": "hello_denied"}] and ws.closed, f"wrong token must be denied and closed: {msgs}")
        ws = await http.ws_connect(f"{base}/ws")   # never says hello
        await recv_all(ws, 1.2)
        check(ws.closed, "a socket that never says hello is closed")

        # ---- replay, normal power ----
        ws = await connect(http, base)
        msgs = await recv_all(ws, 0.5)
        check([m["type"] for m in msgs] == ["hello_ok", "layout", "stats"], f"hello_ok then the snapshot: {msgs}")
        check(len(hub.clients) == 1, "one client registered")
        for cpu in range(5):
            await hub.broadcast({"type": "stats", "cpu": cpu})
        got = await recv_all(ws, 0.3)
        check([m["cpu"] for m in got] == [0, 1, 2, 3, 4], f"normal power sends every message: {got}")

        # ---- low power: coalesce, newest wins, nothing lost for good ----
        await ws.send_str(json.dumps({"type": "power", "mode": "low"}))
        await asyncio.sleep(0.1)
        await asyncio.sleep(0.9)   # past the interval since the last send
        for cpu in range(10, 15):
            await hub.broadcast({"type": "stats", "cpu": cpu})
        got = await recv_all(ws, 0.3)
        check([m["cpu"] for m in got] == [10], f"low power: first goes out, the rest wait: {got}")
        got = await recv_all(ws, 1.5)
        check([m["cpu"] for m in got] == [14], f"low power: the newest one follows, not the old ones: {got}")

        # urgent media changes skip the wait, position ticks do not
        await hub.broadcast({"type": "media", "active": True, "playing": True, "title": "A", "pos": 1})
        await asyncio.sleep(0.1)
        await hub.broadcast({"type": "media", "active": True, "playing": True, "title": "A", "pos": 2})
        await hub.broadcast({"type": "media", "active": True, "playing": False, "title": "A", "pos": 2})
        got = await recv_all(ws, 0.3)
        check([(m["playing"], m["pos"]) for m in got] == [(True, 1), (False, 2)],
              f"pause is urgent, a position tick is not: {got}")

        # going back to normal power flushes what was waiting
        await recv_all(ws, 1.2)
        await hub.broadcast({"type": "stats", "cpu": 20})
        await hub.broadcast({"type": "stats", "cpu": 21})
        await ws.send_str(json.dumps({"type": "power", "mode": "normal"}))
        got = await recv_all(ws, 0.4)
        check(got and got[-1]["cpu"] == 21, f"switching to normal flushes the pending message: {got}")

        # ---- commands ----
        await ws.send_str(json.dumps({"type": "shortcut", "id": 2}))
        await ws.send_str(json.dumps({"type": "shell", "cmd": "calc"}))
        await ws.send_str(json.dumps({"type": "media", "cmd": "toggle", "value": 0}))
        await ws.send_str("not json")
        await asyncio.sleep(0.3)
        check([c["type"] for c in commands] == ["shortcut", "media"], f"only the five commands pass: {commands}")

        # ---- client info and logs show up in diagnostics ----
        await ws.send_str(json.dumps({"type": "info", "visible": True, "retries": 2}))
        await ws.send_str(json.dumps({"type": "log", "level": "error", "msg": "boom"}))
        await asyncio.sleep(0.2)
        d = await (await http.get(f"{base}/api/diag", headers=auth)).json()
        check(d["clients"] and d["clients"][0]["info"].get("retries") == 2, f"client info in diag: {d['clients']}")
        check(any(e["msg"] == "boom" and e["level"] == "error" for e in d["log"]), "client log in diag")
        check(d["server"]["version"].startswith("web-"), "server version in diag")

        # ---- a dead client is dropped, not waited on ----
        await ws.close()
        await asyncio.sleep(0.3)
        check(len(hub.clients) == 0, "closed client removed")
        await hub.broadcast({"type": "stats", "cpu": 99})   # must not raise with nobody connected

    # ---- the port is not silently shared with another program ----
    check(await web_server.answers_on("127.0.0.1", hub.port), "answers_on finds the running display")
    twin = WebHub(token=TOKEN, snapshot=snapshot, command=command, art=lambda i: None,
                  host="127.0.0.1", port=hub.port)
    check(not await twin.start(), "a second display on the same port must fail to start, not share it")
    check(not await web_server.answers_on("127.0.0.1", 9, timeout=1), "answers_on is False when nothing listens")
    # The real-life case: another program already listens on one specific address of the same port.
    import socket
    other = socket.socket()
    other.bind(("127.0.0.1", 0))
    other.listen()
    wide = WebHub(token=TOKEN, snapshot=snapshot, command=command, art=lambda i: None,
                  host="0.0.0.0", port=other.getsockname()[1])
    check(not await wide.start(), "must not start on 0.0.0.0 when another program holds that port on one address")
    other.close()

    await hub.stop()


asyncio.run(main())
print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
sys.exit(1 if problems else 0)
