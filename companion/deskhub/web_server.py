"""Browser display: serves the dashboard and streams the companion's messages to it.

The board protocol (see README "How it works") is reused as it is: JSON messages from
the PC, a few JSON commands back. Differences for a phone in a browser:

* the PC is the server (a browser can only be a client);
* cover art goes over HTTP (GET /art/<id>) instead of RGB565 binary frames;
* each client can ask for "low" power: slower updates, so the phone's radio and CPU
  can rest. Messages are coalesced (the newest one wins), never lost for good.

Everything here is plain HTTP and WebSocket on the local network, like the board.
"""
import asyncio
import hmac
import io
import json
import logging
import pathlib
import secrets
import socket
import sys
import time
from collections import deque
from urllib.parse import urlparse

import psutil
from aiohttp import WSMsgType, web

log = logging.getLogger(__name__)

VERSION = "web-0.1"
WEB_DIR = pathlib.Path(__file__).resolve().parent / "web"
TOKEN_FILE = pathlib.Path.home() / ".deskhub" / "web_token"

# Commands a browser may send (the same five the board sends). Anything else is dropped.
COMMANDS = {"media", "shortcut", "speedtest", "steam_launch", "alert_action", "ai_agent"}

# Minimum seconds between messages of a type, per power mode. Types not listed are
# change-driven already (events, tiles, layout...) and always go straight out.
INTERVALS = {
    "normal": {},
    "low": {"stats": 5, "media": 3, "net": 10, "ai": 30, "claude": 30, "printer": 10,
            "github": 60, "steam": 15},
    # Battery saver: numbers a few times a minute.
    "ultra": {"stats": 15, "media": 5, "net": 30, "ai": 60, "claude": 60, "printer": 20,
              "github": 120, "steam": 30},
    # The screen shows only a dark clock: the phone barely needs the PC.
    "idle": {"stats": 60, "media": 30, "net": 60, "ai": 120, "claude": 120, "printer": 60,
             "github": 300, "steam": 60},
}
PAGE_PATHS = ("/", "/compat", "/diag", "/setup", "/ws")
MODES = ("normal", "low", "ultra", "idle")
# A message goes out at least this often (seconds), so a quiet link is told apart from a dead one.
HEARTBEAT_S = {"normal": 4, "low": 10, "ultra": 20, "idle": 60}
HELLO_FAILS, HELLO_WINDOW_S = 8, 60     # this many wrong codes in this many seconds blocks an address
CMD_LIMIT = (30, 10)                    # at most 30 commands per 10 s from one display
MAX_REPORTS = 20
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1")
HELLO_TIMEOUT_S = 10
SEND_TIMEOUT_S = 3
LOG_KEEP = 200
LOOPBACK = ("127.0.0.1", "::1")


def load_token(cfg: dict) -> str:
    """[web] token if set, else a random one kept in ~/.deskhub/web_token."""
    tok = str((cfg.get("web") or {}).get("token", "")).strip()
    if tok and tok != "change-me":
        return tok
    try:
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    except OSError:
        pass
    tok = secrets.token_urlsafe(16)
    try:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(tok, encoding="utf-8")
    except OSError as e:
        log.warning("could not save the web token to %s: %s", TOKEN_FILE, e)
    return tok


def new_token() -> str:
    """Replace the saved pairing code (every phone has to pair again)."""
    tok = secrets.token_urlsafe(16)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(tok, encoding="utf-8")
    return tok


def lan_ips() -> list[str]:
    """This PC's private IPv4 addresses, the one the OS would use first."""
    found = []
    try:
        stats = psutil.net_if_stats()
        for name, addrs in psutil.net_if_addrs().items():
            if name in stats and not stats[name].isup:
                continue
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith(("127.", "169.254.")):
                    found.append(a.address)
    except Exception as e:  # psutil can fail on odd adapters
        log.debug("listing addresses failed: %s", e)
    primary = None
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # sends nothing; asks the OS which interface it would use
        primary = s.getsockname()[0]
    except OSError:
        pass
    finally:
        s.close()
    if primary in found:
        found.remove(primary)
        found.insert(0, primary)
    return found


async def answers_on(ip: str, port: int, timeout: float = 3) -> bool:
    """True if a DeskHub web display answers at ip:port (checks the address the phone will use)."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
        try:
            writer.write(f"GET /api/ping HTTP/1.0\r\nHost: {ip}\r\n\r\n".encode())
            await writer.drain()
            data = await asyncio.wait_for(reader.read(400), timeout)
        finally:
            writer.close()
        return b'"version"' in data
    except (OSError, asyncio.TimeoutError):
        return False


def pair_url(ip: str, port: int, token: str) -> str:
    # The token rides in the fragment: it is never sent to the server in the request line.
    return f"http://{ip}:{port}/#t={token}"


def qr_svg(text: str) -> str:
    import segno

    return segno.make(text, error="m").svg_inline(scale=6, border=2, dark="#000", light="#fff")


def qr_terminal(text: str) -> str | None:
    """The QR code as text blocks for the console, or None if it can't be shown there."""
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    if "utf" not in enc:
        return None
    import segno

    buf = io.StringIO()
    segno.make(text, error="l").terminal(out=buf, compact=True, border=2)
    return buf.getvalue()


class Client:
    def __init__(self, ws, ip: str, ua: str, mode: str):
        self.ws, self.ip, self.ua, self.mode = ws, ip, ua, mode
        self.since = time.time()
        self.last_rx = self.since
        self.tx = self.rx = 0
        self.tx_bytes = 0
        self.last_tx = 0.0
        self.cmd_times: deque = deque(maxlen=CMD_LIMIT[0])
        self.cmd_blocked = False
        self.sent_at: dict[str, float] = {}
        self.last: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}
        self.info: dict = {}
        self.flusher: asyncio.Task | None = None


def _urgent(kind: str, prev: dict | None, new: dict) -> bool:
    """A change that must not wait for the low-power interval (play, pause, a new track)."""
    if kind == "media" and prev is not None:
        return any(prev.get(k) != new.get(k) for k in ("active", "playing", "title", "artist", "art_id"))
    return prev is None


class WebHub:
    def __init__(self, *, token: str, snapshot, command, art, host: str = "0.0.0.0", port: int = 8787,
                 clock=time.monotonic, intervals=None, trust_loopback: bool = True, steam_art=None, on_connect=None):
        """snapshot(): async, the messages a new client needs. command(dict): async, runs one
        of COMMANDS. art(id): (bytes, content type) or None. steam_art(appid, kind): the same for a
        game cover; it may block (network), so it runs in a thread."""
        self.token, self.snapshot, self.command, self.art = token, snapshot, command, art
        self.steam_art = steam_art
        self.on_connect = on_connect   # called when a display connects (wakes resting loops)
        self._hello_fails: dict[str, deque] = {}
        self.host, self.port, self.clock = host, port, clock
        self.trust_loopback = trust_loopback   # the PC's own browser needs no token
        self.intervals = intervals or INTERVALS
        self.clients: set[Client] = set()
        self.logs: deque = deque(maxlen=LOG_KEEP)
        self.reports: dict[str, dict] = {}
        self._seen: dict[str, float] = {}
        self.started = time.time()
        self.runner: web.AppRunner | None = None
        self._unauth_log_times: deque = deque(maxlen=60)

    # ---- lifecycle ---------------------------------------------------------------

    def build_app(self) -> web.Application:
        app = web.Application(middlewares=[self._headers], client_max_size=64 * 1024)
        app.router.add_get("/ws", self._ws)
        app.router.add_get("/api/ping", self._ping)
        app.router.add_get("/api/diag", self._diag)
        app.router.add_post("/api/log", self._post_log)
        app.router.add_post("/api/report", self._post_report)
        app.router.add_get("/art/{id}", self._art)
        app.router.add_get("/steam/{appid}/{kind}", self._steam)
        app.router.add_get("/setup", self._setup)
        for path, name in (("/", "index.html"), ("/compat", "compat.html"), ("/diag", "diag.html")):
            app.router.add_get(path, self._page(name))
        if WEB_DIR.is_dir():
            app.router.add_static("/", WEB_DIR, follow_symlinks=False)
        return app

    async def start(self) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sys.platform == "win32":
                # Without this, Windows lets two programs share a port: another program bound to
                # this PC's Wi-Fi address would silently take the phone's connections.
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
        except OSError as e:
            sock.close()
            log.error("web display: port %d is not available (%s). Another program is probably using it; "
                      "set a different port under [web] in config.toml.", self.port, e)
            return False
        self.runner = web.AppRunner(self.build_app(), access_log=None)
        await self.runner.setup()
        await web.SockSite(self.runner, sock).start()
        self.port = sock.getsockname()[1]   # port 0 (tests) means the OS picks one
        log.info("web display listening on port %d", self.port)
        return True

    async def stop(self):
        for c in list(self.clients):
            await c.ws.close()
        if self.runner:
            await self.runner.cleanup()

    # ---- helpers -----------------------------------------------------------------

    @web.middleware
    async def _headers(self, request, handler):
        try:
            resp = await handler(request)
        except web.HTTPException as e:
            resp = e
        # Show on the PC what a phone asks for: pages and failures always, anything else
        # when a device is heard from after a quiet spell.
        ip, now = request.remote or "?", time.time()
        if request.path in PAGE_PATHS or resp.status >= 400 or now - self._seen.get(ip, 0) > 300:
            log.info("[web %s] %s %s -> %s", ip, request.method, request.path, resp.status)
        self._seen[ip] = now
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"                      # no clickjacking of the shortcut buttons
        resp.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        if "Cache-Control" not in resp.headers:
            fonts = request.path.endswith((".ttf", ".woff2"))
            resp.headers["Cache-Control"] = "public, max-age=604800" if fonts else "no-cache"
        if isinstance(resp, web.HTTPException):
            raise resp
        return resp

    @staticmethod
    def _host_is_local(request) -> bool:
        """The Host header names this PC itself. A web page on another site can make the browser connect to
        127.0.0.1 under its own name (DNS rebinding); such a request must not get the PC's own trust."""
        host = (request.host or "").rsplit(":", 1)[0] if not (request.host or "").startswith("[") else \
            (request.host or "").split("]")[0] + "]"
        return host in LOCAL_HOSTS

    def _authed(self, request) -> bool:
        if self.trust_loopback and request.remote in LOOPBACK and self._host_is_local(request):
            return True
        given = request.headers.get("X-Token", "")
        return hmac.compare_digest(given.encode(), self.token.encode())

    def add_log(self, ip: str, level: str, msg: str, authed: bool = True):
        self.logs.append({"t": time.time(), "ip": ip, "level": level, "msg": str(msg)[:300], "authed": authed})
        (log.warning if level in ("warn", "error") else log.info)("[web %s] %s", ip, str(msg)[:300])

    def _page(self, name):
        async def handler(request):
            return web.FileResponse(WEB_DIR / name)
        return handler

    # ---- HTTP --------------------------------------------------------------------

    async def _ping(self, request):
        return web.json_response({"ok": True, "version": VERSION, "time": int(time.time() * 1000)})

    async def _diag(self, request):
        if not self._authed(request):
            raise web.HTTPForbidden(text="token needed")
        return web.json_response(self.diag())

    async def _post_log(self, request):
        authed = self._authed(request)
        if not authed:   # unpaired phones may still report why pairing failed, but only a little
            now = time.time()
            self._unauth_log_times.append(now)
            if len(self._unauth_log_times) == 60 and now - self._unauth_log_times[0] < 60:
                raise web.HTTPTooManyRequests()
        try:
            body = await request.json()
        except ValueError:
            raise web.HTTPBadRequest()
        self.add_log(request.remote or "?", str(body.get("level", "info"))[:8], body.get("msg", ""), authed)
        return web.json_response({"ok": True})

    async def _post_report(self, request):
        try:
            body = await request.json()
        except ValueError:
            raise web.HTTPBadRequest()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest()
        body["_received"] = time.time()
        if len(self.reports) >= MAX_REPORTS and (request.remote or "?") not in self.reports:
            self.reports.pop(next(iter(self.reports)))
        self.reports[request.remote or "?"] = body
        self.add_log(request.remote or "?", "info",
                     f"compat report: android {body.get('android')}, chrome {body.get('chrome')}, "
                     f"viewport {body.get('viewport')}", self._authed(request))
        return web.json_response({"ok": True})

    async def _art(self, request):
        if not self._authed(request):
            raise web.HTTPForbidden(text="token needed")
        try:
            art_id = int(request.match_info["id"])
        except ValueError:
            raise web.HTTPNotFound()
        got = self.art(art_id)
        if not got:
            raise web.HTTPNotFound()
        data, ctype = got
        return web.Response(body=data, content_type=ctype, headers={"Cache-Control": "public, max-age=86400"})

    async def _steam(self, request):
        if not self._authed(request):
            raise web.HTTPForbidden(text="token needed")
        try:
            appid = int(request.match_info["appid"])
        except ValueError:
            raise web.HTTPNotFound()
        got = await asyncio.to_thread(self.steam_art, appid, request.match_info["kind"]) if self.steam_art else None
        if not got:
            raise web.HTTPNotFound()
        data, ctype = got
        return web.Response(body=data, content_type=ctype, headers={"Cache-Control": "public, max-age=86400"})

    async def _setup(self, request):
        if request.remote not in LOOPBACK or not self._host_is_local(request):
            raise web.HTTPForbidden(text="open this page on the PC itself")
        ips = lan_ips() or ["127.0.0.1"]
        url = pair_url(ips[0], self.port, self.token)
        others = "".join(f"<li><code>{pair_url(ip, self.port, self.token)}</code></li>" for ip in ips[1:])
        html = f"""<!doctype html><meta charset=utf-8><title>Pair your phone</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<body style="font:16px sans-serif;max-width:640px;margin:24px auto;padding:0 16px">
<h1>Pair your phone</h1>
<p>On the phone, open the camera or a QR reader and scan this, or type the address into the phone's browser.
Both devices must be on the same Wi-Fi.</p>
<div style="width:280px">{qr_svg(url)}</div>
<p><b>Address:</b> <code>{url}</code></p>
{"<p>Other addresses of this PC, if that one does not work:</p><ul>" + others + "</ul>" if others else ""}
<p><a href="/diag">Diagnostics</a> · <a href="/compat">Compatibility test</a></p>
</body>"""
        return web.Response(text=html, content_type="text/html")

    # ---- diagnostics -------------------------------------------------------------

    def diag(self) -> dict:
        now = time.time()
        return {
            "server": {"version": VERSION, "uptime_s": int(now - self.started), "port": self.port,
                       "addresses": lan_ips(), "python": sys.version.split()[0]},
            "clients": [{"ip": c.ip, "ua": c.ua, "mode": c.mode, "connected_s": int(now - c.since),
                         "last_rx_s": int(now - c.last_rx), "tx": c.tx, "rx": c.rx, "tx_bytes": c.tx_bytes,
                         "pending": sorted(c.pending), "info": c.info} for c in self.clients],
            "reports": self.reports,
            "log": list(self.logs)[-100:],
        }

    # ---- WebSocket ---------------------------------------------------------------

    def _note_failure(self, ip: str):
        q = self._hello_fails.setdefault(ip, deque(maxlen=HELLO_FAILS))
        q.append(self.clock())
        while len(self._hello_fails) > 200:
            self._hello_fails.pop(next(iter(self._hello_fails)))

    def _too_many_failures(self, ip: str) -> bool:
        q = self._hello_fails.get(ip)
        return bool(q) and len(q) >= HELLO_FAILS and self.clock() - q[0] < HELLO_WINDOW_S

    async def _ws(self, request):
        ip = request.remote or "?"
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:   # a page from another site, not our dashboard
            self.add_log(ip, "warn", f"refused: a web page from another site tried to connect ({origin[:60]})", False)
            raise web.HTTPForbidden(text="cross-site connection refused")
        if self._too_many_failures(ip):
            raise web.HTTPTooManyRequests(text="too many wrong pairing codes; wait a minute")
        ws = web.WebSocketResponse(heartbeat=10, max_msg_size=64 * 1024)
        await ws.prepare(request)
        ua = request.headers.get("User-Agent", "")[:200]
        try:
            first = await ws.receive(timeout=HELLO_TIMEOUT_S)
            if first.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                return ws   # the page was reloaded or closed before it said hello
            hello = json.loads(first.data) if first.type == WSMsgType.TEXT else None
        except (asyncio.TimeoutError, ValueError):
            hello = None
        if not isinstance(hello, dict) or hello.get("type") != "hello" or not hmac.compare_digest(
                str(hello.get("token", "")).encode(), self.token.encode()):
            self.add_log(ip, "warn", "refused: no hello or wrong token (open the pairing address again)", False)
            self._note_failure(ip)
            await ws.send_str('{"type":"hello_denied"}')
            await ws.close(code=4401)
            return ws

        c = Client(ws, ip, ua, hello.get("mode") if hello.get("mode") in MODES else "normal")
        self.clients.add(c)
        self.add_log(ip, "info", f"connected ({c.mode} power)")
        c.last_tx = self.clock()
        c.flusher = asyncio.create_task(self._flush_loop(c))
        if self.on_connect:
            self.on_connect()
        try:
            await self._send(c, {"type": "hello_ok", "version": VERSION, "time": int(time.time() * 1000)})
            for m in await self.snapshot():
                await self._send(c, m)
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    c.rx += 1
                    c.last_rx = time.time()
                    await self._on_text(c, msg.data)
        except (ConnectionError, asyncio.TimeoutError):
            pass
        finally:
            c.flusher.cancel()
            self.clients.discard(c)
            self.add_log(ip, "info", f"disconnected after {int(time.time() - c.since)} s")
        return ws

    async def _on_text(self, c: Client, raw: str):
        try:
            m = json.loads(raw)
        except ValueError:
            return
        if not isinstance(m, dict):
            return
        kind = m.get("type")
        if kind == "power":
            c.mode = m.get("mode") if m.get("mode") in MODES else "normal"
            self.add_log(c.ip, "info", f"power mode {c.mode}")
            if self.on_connect:
                self.on_connect()   # the PC's polling loops follow the new wishes now
            await self._flush(c, force=True)
        elif kind == "info":
            c.info = {k: v for k, v in list(m.items())[:20] if k != "type" and len(json.dumps(v)) < 200}
        elif kind == "log":
            self.add_log(c.ip, str(m.get("level", "info"))[:8], m.get("msg", ""))
        elif kind in COMMANDS:
            now = self.clock()
            if len(c.cmd_times) == c.cmd_times.maxlen and now - c.cmd_times[0] < CMD_LIMIT[1]:
                if not c.cmd_blocked:
                    c.cmd_blocked = True
                    self.add_log(c.ip, "warn", "too many commands from this display; ignoring them for a moment")
                return
            c.cmd_blocked = False
            c.cmd_times.append(now)
            try:
                await self.command(m)
            except Exception as e:
                self.add_log(c.ip, "warn", f"command {kind} failed: {e}")

    # ---- sending, with low-power coalescing ---------------------------------------

    async def _send(self, c: Client, msg: dict):
        kind = msg.get("type", "")
        c.sent_at[kind] = self.clock()
        c.last[kind] = msg
        c.pending.pop(kind, None)
        payload = json.dumps(msg, separators=(",", ":"))
        try:
            await asyncio.wait_for(c.ws.send_str(payload), SEND_TIMEOUT_S)
        except (asyncio.TimeoutError, ConnectionError, RuntimeError):
            await c.ws.close()
            raise ConnectionError("client too slow or gone")
        c.tx += 1
        c.tx_bytes += len(payload)
        c.last_tx = self.clock()

    async def offer(self, c: Client, msg: dict):
        kind = msg.get("type", "")
        if msg == c.last.get(kind):      # the display already has exactly this: say nothing
            c.pending.pop(kind, None)
            return
        gap = self.intervals.get(c.mode, {}).get(kind, 0)
        if gap and self.clock() - c.sent_at.get(kind, -1e9) < gap and not _urgent(kind, c.last.get(kind), msg):
            c.pending[kind] = msg
            return
        await self._send(c, msg)

    async def broadcast(self, msg: dict):
        for c in list(self.clients):
            try:
                await self.offer(c, msg)
            except ConnectionError:
                pass

    async def _flush(self, c: Client, force: bool = False):
        for kind, msg in list(c.pending.items()):
            gap = self.intervals.get(c.mode, {}).get(kind, 0)
            if force or self.clock() - c.sent_at.get(kind, -1e9) >= gap:
                await self._send(c, msg)

    async def _flush_loop(self, c: Client):
        try:
            while True:
                await asyncio.sleep(0.5)
                await self._flush(c)
                if self.clock() - c.last_tx >= HEARTBEAT_S.get(c.mode, 10):   # tells a quiet link from a dead one
                    await self._send(c, {"type": "ping"})
        except (asyncio.CancelledError, ConnectionError):
            pass
