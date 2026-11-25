"""Desk hub companion: streams PC data to the hub and runs its commands.

    uv run python -m deskhub [--config path/to/config.toml] [--verbose]
"""
import sys

if __name__ == "__main__" and "--tray" in sys.argv and "--child" not in sys.argv and "--no-guardian" not in sys.argv:
    # Started hidden (the Startup shortcut): a small watcher runs the companion and starts it again if it dies.
    # This runs before the heavy imports below, so the watcher itself stays small.
    from .guardian import run_guardian

    sys.exit(run_guardian(sys.argv[1:]))

import argparse
import asyncio
import json
import logging
import os
import pathlib
import subprocess
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor

import websockets

from . import audio_state, text
from .calendar_feed import fetch_events
from .claude_alerts import ClaudeAlerts
from .claude_usage import ClaudeUsage
from .codex_usage import CodexUsage, codex_home
from .media import Media
from .netstats import NetStats
from .pages import enabled_pages, home_grid, home_message, layout_message, pc_sleep_mode
from .pc_power import PowerWatch
from .printer import PrinterService
from .shortcuts import hub_view, lit_message, load_tiles, run_tile
from .stats import Stats
from .custom_games import CustomGames, load_games
from .steam import Steam, steam_installed
from .supervise import Pacer, Supervisor
from .weather import Weather
from .web_server import WebHub, answers_on, lan_ips, load_token, new_token, pair_url, qr_terminal

log = logging.getLogger("deskhub")

CALENDAR_REFRESH_S = 600
PRINTER_TICK_S = 2
PRINTER_KEEPALIVE_S = 30
STEAM_TICK_S = 2
STEAM_KEEPALIVE_S = 60
NET_TICK_S = 2
SPEEDTEST_MIN_GAP_S = 120
GITHUB_TICK_S = 30
WEATHER_REFRESH_S = 900
WEATHER_RETRY_S = 60
IDLE_PACE_S = 30   # how long a polling loop rests while no display is connected
# How many times slower the polling loops may run when every connected display is in this power mode.
POLL_SCALE = {"normal": 1, "low": 3, "ultra": 8, "idle": 30}


LOG_FILE = pathlib.Path.home() / ".deskhub" / "companion.log"
_instance_mutex = None


def single_instance(name: str = "Local\\DeskHubCompanion") -> bool:
    """True if no other companion runs for this user (a named Windows mutex)."""
    global _instance_mutex
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    _instance_mutex = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def release_instance():
    """Let another companion start (before restarting this one)."""
    global _instance_mutex
    if _instance_mutex:
        import ctypes

        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_instance_mutex))
        _instance_mutex = None


def find_config(arg: str | None) -> pathlib.Path:
    candidates = [pathlib.Path(arg)] if arg else [
        pathlib.Path.cwd() / "config.toml",
        pathlib.Path(__file__).resolve().parent.parent / "config.toml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    sys.exit("config.toml not found. Copy config.example.toml to config.toml and edit it.")


def pick_ai(agent: str, claude: dict | None, codex: dict | None) -> dict:
    """The AI page message. "auto" shows whichever agent was active last (Claude on a tie)."""
    if agent == "codex" and codex is not None:
        provider = "codex"
    elif agent == "auto" and codex is not None and claude is not None \
            and codex.get("last_active", 0) > claude.get("last_active", 0):
        provider = "codex"
    elif claude is not None:
        provider = "claude"
    else:
        provider = "codex"
    snap = codex if provider == "codex" else claude
    return {**snap, "type": "ai", "provider": provider, "agent": agent}


def _steam_key(msg: dict) -> dict:
    """The Steam message without the session clock, which the board counts itself."""
    playing = msg.get("playing")
    return {**msg, "playing": {k: v for k, v in playing.items() if k != "session_s"} if playing else None}


class Companion:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        hub = cfg.get("hub", {})
        web_cfg = cfg.get("web", {})
        # The ESP32 board is used only when a [hub] is configured (or enabled = true);
        # the browser display is on unless [web] enabled = false.
        self.use_board = bool(hub.get("enabled", "host" in hub))
        self.use_web = bool(web_cfg.get("enabled", True))
        self.web = None
        self.stats_msg = None
        self.media_msg = None
        self.weather = Weather(cfg.get("weather", {}))
        self.weather_msg = None
        self.supervisor = Supervisor()
        self.pacer = Pacer(self.has_audience, IDLE_PACE_S, self.poll_scale)
        text.UNICODE = not self.use_board   # a browser shows any language; the board's fonts are ASCII
        self.host = hub.get("host", "deskhub.local")
        self.url = f"ws://{self.host}/ws"
        self.on_status = None   # (connected, detail) -> None, e.g. the tray icon
        self.token = hub.get("token", "")
        self.stats = Stats()
        self.media = Media()
        self.tiles = load_tiles(cfg)
        # Core Audio calls need COM, so they run on one dedicated thread.
        self.audio_pool = ThreadPoolExecutor(1, thread_name_prefix="audio", initializer=audio_state.com_thread)
        self.lit_msg = None
        self.panel = None   # panel.Panel, set by the desktop app before run()
        self.events: list[dict] = []
        live = None
        if cfg.get("claude", {}).get("live_limits"):
            from .claude_live import LiveLimits
            live = LiveLimits()
            log.info("live Claude limits enabled")
        self.agent = cfg.get("ai", {}).get("agent", "auto")
        if self.agent not in ("auto", "claude", "codex"):
            log.warning("[ai] agent = %r is not auto, claude or codex; using auto", self.agent)
            self.agent = "auto"
        # Both agents are read so the phone can switch between them (ai_agent message).
        self.claude = ClaudeUsage(live=live)
        codex_live = None
        if cfg.get("codex", {}).get("live_limits"):
            from .codex_live import CodexLiveLimits
            codex_live = CodexLiveLimits()
            log.info("live Codex limits enabled")
        self.codex = CodexUsage(live=codex_live) if self.agent == "codex" or (
            self.agent == "auto" and codex_home().is_dir()) else None
        self.claude_msg = None
        ccfg = cfg.get("claude", {})
        self.alerts = (ClaudeAlerts(idle_after=float(ccfg.get("idle_alert_seconds", 30)))
                       if ccfg.get("alerts", True) else None)
        self.printer_msg = None
        custom = CustomGames(load_games(cfg))
        use_steam = bool(cfg.get("steam", {}).get("enabled", True))
        web = None
        if use_steam:
            from .steam_web import SteamWeb, get_key

            key = get_key()  # optional, from `deskhub-setup` (Games step)
            if key:
                web = SteamWeb(key)
                log.info("Steam Web API: friends and playtime on")
        self.steam = (Steam(custom=custom, use_steam=use_steam, web=web)
                      if use_steam or custom.games else None)
        self.steam_msg = None
        icfg = cfg.get("internet", {})
        self.net = (NetStats(show_ip=bool(icfg.get("show_ip", False)))
                    if icfg.get("enabled", True) else None)
        self.net_msg = None
        self.speedtest_at = -SPEEDTEST_MIN_GAP_S
        self.github = None
        gcfg = cfg.get("github", {})
        if gcfg.get("enabled", True) and (any(g["widget"] == "github" for g in home_grid(cfg))
                                          or "github" in enabled_pages(cfg)):
            from .github import GitHub, get_token

            token = get_token()  # from `deskhub-setup github`
            if token:
                self.github = GitHub(token, accent=str(gcfg.get("colors", "green")).lower() == "accent")
            else:
                log.info("the GitHub widget or page is on but no token is saved; run: uv run deskhub-setup github")
        self.connected_once = False
        self.ws = None
        self.loop = None
        self.pc_asleep = False
        self.power = PowerWatch(self.on_pc_power) if pc_sleep_mode(cfg) != "none" else None

    def on_pc_power(self, asleep: bool):
        """From the power-watch thread: tell the board the PC's display slept or woke."""
        self.pc_asleep = asleep
        if self.loop is None:
            return
        fut = asyncio.run_coroutine_threadsafe(self.send({"type": "pc_power", "asleep": asleep}), self.loop)
        try:
            # Before a suspend the network goes down soon after this returns.
            fut.result(timeout=2)
        except Exception:
            pass

    def status(self, connected: bool, detail: str):
        if self.on_status:
            try:
                self.on_status(connected, detail)
            except Exception as e:
                log.debug("status callback failed: %s", e)

    def poll_scale(self) -> float:
        """The ESP32 board always gets full speed; browsers set the pace through their power mode."""
        if self.ws is not None or self.web is None or not self.web.clients:
            return 1.0
        return float(min(POLL_SCALE.get(c.mode, 1) for c in self.web.clients))

    def has_audience(self) -> bool:
        """True while a browser or the board is connected to look at the data."""
        return self.ws is not None or (self.web is not None and bool(self.web.clients))

    async def send(self, msg: dict | bytes):
        """To every connected browser and to the board."""
        if self.web is not None and isinstance(msg, dict):
            await self.web.broadcast(msg)
        await self.send_board(msg)

    async def send_board(self, msg: dict | bytes):
        ws = self.ws
        if ws is None:
            return
        try:
            await ws.send(msg if isinstance(msg, bytes) else json.dumps(msg, separators=(",", ":")))
        except websockets.ConnectionClosed:
            pass

    # ---- producers --------------------------------------------------------

    async def stats_loop(self):
        while True:
            self.stats_msg = self.stats.sample()
            await self.send(self.stats_msg)
            await self.pacer.sleep(1)

    async def media_loop(self):
        await self.media.start()
        while True:
            try:
                msg, art = await self.media.snapshot()
                if art:
                    await self.send(art)
                self.media_msg = msg
                await self.send(msg)
            except Exception as e:
                log.debug("media poll failed: %s", e)
            await self.pacer.sleep(1)

    def ai_snapshot(self) -> dict:
        claude = self.claude.snapshot() if self.claude else None
        codex = self.codex.snapshot() if self.codex else None
        return pick_ai(self.agent, claude, codex)

    async def sound_outputs(self) -> list[str]:
        """Names of the PC's active playback devices (for the control panel's Output button)."""
        return await asyncio.get_running_loop().run_in_executor(
            self.audio_pool, lambda: [name for _, name in audio_state.list_outputs()])

    async def tiles_loop(self):
        """Light up toggle tiles (mic and speaker mute) to match Windows."""
        while True:
            await self.refresh_lit()
            await self.pacer.sleep(1)

    async def refresh_lit(self):
        try:
            states = await asyncio.get_running_loop().run_in_executor(self.audio_pool, audio_state.read_states)
        except Exception as e:
            log.warning("tile states failed: %s", e)
            return
        msg = lit_message(self.tiles, states)
        if msg != self.lit_msg:
            self.lit_msg = msg
            await self.send(msg)

    async def weather_loop(self):
        """Open-Meteo through the PC; the browser page shows it (the ESP32 fetches its own)."""
        while True:
            delay = WEATHER_REFRESH_S
            try:
                self.weather_msg = await asyncio.to_thread(self.weather.poll)
                await self.send(self.weather_msg)
                if self.weather_msg.get("error"):
                    return   # nothing to refresh until config.toml changes (a restart)
            except Exception as e:
                log.warning("weather failed: %s", e)
                delay = WEATHER_RETRY_S
            await asyncio.sleep(delay)

    async def claude_loop(self):
        while True:
            try:
                self.claude_msg = await asyncio.to_thread(self.ai_snapshot)
                await self.send(self.claude_msg)
            except Exception as e:
                log.warning("AI usage failed: %s", e)
            await self.pacer.sleep(5)

    async def alerts_loop(self):
        while True:
            try:
                msg = await asyncio.to_thread(self.alerts.poll)
                if msg:
                    await self.send(msg)
            except Exception as e:
                log.warning("claude alerts failed: %s", e)
            await self.pacer.sleep(1, scalable=False)

    def events_message(self) -> dict:
        # "days" lets the hub say how far ahead it looked ("No more events in the next 7 days").
        days = int(self.cfg.get("calendar", {}).get("days", 7))
        return {"type": "events", "events": self.events, "days": days}

    async def calendar_loop(self):
        cal = self.cfg.get("calendar", {})
        feeds, days = cal.get("feeds", []), int(cal.get("days", 7))
        while True:
            self.events = await fetch_events(feeds, days)
            log.info("calendar: %d upcoming events", len(self.events))
            await self.send(self.events_message())
            await asyncio.sleep(CALENDAR_REFRESH_S)

    async def printer_loop(self):
        service = PrinterService(self.cfg.get("printers", []))
        if not service.workers:
            # Tell the display there are none, so its page can say so instead of waiting.
            self.printer_msg = {"type": "printer", "printers": []}
            await self.send(self.printer_msg)
            return
        service.start()
        sent_at = 0.0
        try:
            while True:
                msg = service.message()
                now = asyncio.get_running_loop().time()
                # Send on change (checked every 2 s) and at least every 30 s.
                if msg != self.printer_msg or now - sent_at >= PRINTER_KEEPALIVE_S:
                    self.printer_msg = msg
                    sent_at = now
                    await self.send(msg)
                await self.pacer.sleep(PRINTER_TICK_S)
        finally:
            service.stop()  # lets each printer connection close cleanly on exit

    async def steam_loop(self):
        if not (self.steam.use_steam and steam_installed()) and not self.steam.custom.games:
            return
        sent_at = 0.0
        last = None
        while True:
            try:
                msg = await asyncio.to_thread(self.steam.snapshot)
                self.steam_msg = msg
                key = _steam_key(msg)
                now = asyncio.get_running_loop().time()
                if key != last or now - sent_at >= STEAM_KEEPALIVE_S:
                    last, sent_at = key, now
                    await self.send(msg)
                for frame in await asyncio.to_thread(self.steam.frames):
                    await self.send(frame)
            except Exception as e:
                log.warning("steam poll failed: %s", e)
            await self.pacer.sleep(STEAM_TICK_S)

    async def net_loop(self):
        while True:
            try:
                await asyncio.to_thread(self.net.tick)
                self.net_msg = self.net.message()
                await self.send(self.net_msg)
            except Exception as e:
                log.warning("net stats failed: %s", e)
            await asyncio.sleep(NET_TICK_S)

    async def github_loop(self):
        while True:
            try:
                msg = await asyncio.to_thread(self.github.poll)
                if msg:
                    await self.send(msg)
            except Exception as e:
                log.warning("github poll failed: %s", e)
            await self.pacer.sleep(GITHUB_TICK_S)

    async def speedtest(self):
        """Run a speed test now (at most one at a time, one per two minutes)."""
        now = time.monotonic()
        if not self.net or self.net.testing or now - self.speedtest_at < SPEEDTEST_MIN_GAP_S:
            return
        self.speedtest_at = now
        task = asyncio.create_task(asyncio.to_thread(self.net.run_speedtest))
        await asyncio.sleep(0)  # let the thread flag testing = True
        while not self.net.testing and not task.done():
            await asyncio.sleep(0.05)
        self.net_msg = self.net.message()
        await self.send(self.net_msg)
        await task
        self.net_msg = self.net.message()
        await self.send(self.net_msg)

    async def speedtest_schedule(self, hours: float):
        while True:
            await asyncio.sleep(hours * 3600)
            await self.speedtest()

    # ---- hub commands -----------------------------------------------------

    async def handle(self, raw):
        if isinstance(raw, bytes):
            return
        msg = raw if isinstance(raw, dict) else json.loads(raw)
        kind = msg.get("type")
        if kind == "media":
            await self.media.command(msg.get("cmd", ""), int(msg.get("value", 0)))
        elif kind == "alert_action" and self.alerts:
            sid, action = str(msg.get("id", "")), msg.get("action")
            if action == "dismiss":
                self.alerts.dismiss(sid)
            elif action == "focus":
                await asyncio.to_thread(self.alerts.focus, sid)
        elif kind == "ai_agent":
            agent = msg.get("agent")
            if agent in ("auto", "claude", "codex") and (agent != "codex" or self.codex) and agent != self.agent:
                self.agent = agent
                log.info("AI page now shows: %s", agent)
                self.claude_msg = await asyncio.to_thread(self.ai_snapshot)
                await self.send(self.claude_msg)
        elif kind == "speedtest" and self.net:
            asyncio.create_task(self.speedtest())
        elif kind == "steam_launch" and self.steam:
            await asyncio.to_thread(self.steam.launch, int(msg.get("appid", 0)))
        elif kind == "shortcut":
            i = int(msg.get("id", -1))
            if 0 <= i < len(self.tiles):
                try:
                    if self.tiles[i]["action"] == "mic":
                        log.info("shortcut %r: mic", self.tiles[i]["label"])
                        await asyncio.get_running_loop().run_in_executor(self.audio_pool, audio_state.toggle_mic)
                        await self.refresh_lit()
                        return
                    if self.tiles[i]["action"] == "output":
                        used = await asyncio.get_running_loop().run_in_executor(
                            self.audio_pool, audio_state.toggle_output, self.tiles[i]["target"])
                        log.info("shortcut %r: output -> %s", self.tiles[i]["label"],
                                 used or "not switched (a device is missing)")
                        return
                    pending = run_tile(self.tiles[i], self.media)
                    if pending is not None:
                        await pending
                except Exception as e:
                    log.warning("shortcut %d failed: %s", i, e)

    def snapshot_messages(self) -> list[dict]:
        """The state a new display needs, in the order the board has always received it."""
        msgs = [layout_message(self.cfg), {"type": "pc_power", "asleep": self.pc_asleep},
                home_message(self.cfg), hub_view(self.tiles)]
        if self.lit_msg:
            msgs.append(self.lit_msg)
        msgs.append(self.events_message())
        for m in (self.claude_msg, self.alerts.msg if self.alerts else None, self.printer_msg,
                  self.net_msg, self.github.msg if self.github else None,
                  self.steam_msg if self.steam else None, self.stats_msg, self.media_msg,
                  self.weather_msg):
            if m:
                msgs.append(m)
        return msgs

    def web_art(self, art_id: int):
        got = self.media.current_art_jpeg()
        return (got[1], "image/jpeg") if got and got[0] == art_id else None

    def web_steam_art(self, appid: int, kind: str):
        data = self.steam.web_art(appid, kind) if self.steam else None
        return (data, "image/jpeg") if data else None

    async def web_snapshot(self) -> list[dict]:
        return self.snapshot_messages()

    async def start_web(self):
        wcfg = self.cfg.get("web", {})
        token = load_token(self.cfg)
        port = int(wcfg.get("port", 8787))
        self.web = WebHub(token=token, snapshot=self.web_snapshot, command=self.handle, art=self.web_art,
                          steam_art=self.web_steam_art, on_connect=self.pacer.wake,
                          host=str(wcfg.get("host", "0.0.0.0")), port=port, panel=self.panel)
        if not await self.web.start():
            self.web = None
            return
        ips = lan_ips()
        url = pair_url(ips[0] if ips else "127.0.0.1", port, token)
        # The phone will use the PC's network address, so test that one, not just localhost.
        local_only = str(wcfg.get("host", "0.0.0.0")) in ("127.0.0.1", "localhost")
        if ips and not local_only and not await answers_on(ips[0], port):
            log.error("the web display does not answer on %s:%d, the address the phone uses. A security "
                      "program may be closing connections; try a different [web] port in config.toml.",
                      ips[0], port)
        # The pairing code is a secret: the log file gets the address only, a console the full one.
        log.info("open on the phone: %s  (pairing code: on this PC open http://localhost:%d/setup)",
                 url.split("#")[0], port)
        if sys.stderr is not None:
            print(f"\nPairing address (keep it private): {url}", file=sys.stderr)
            qr = qr_terminal(url)
            if qr:
                print("Scan with the phone (same Wi-Fi):\n" + qr, file=sys.stderr)
        self.status(True, "web display ready")

    async def session(self):
        async with websockets.connect(self.url, max_size=2**20, ping_interval=10,
                                      ping_timeout=10, open_timeout=10) as ws:
            await ws.send(json.dumps({"type": "hello", "token": self.token}))
            reply = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if reply.get("type") != "hello_ok":
                raise RuntimeError(f"hub refused hello: {reply}")
            log.info("connected to hub (firmware %s)", reply.get("version", "?"))
            self.connected_once = True
            peer = ws.remote_address[0] if ws.remote_address else ""
            self.status(True, f"connected to {self.host}" + (f" ({peer})" if peer else ""))
            self.ws = ws
            self.pacer.wake()
            # Everything the hub keeps in RAM, resent after each (re)connect.
            for m in self.snapshot_messages():
                await self.send_board(m)
            if self.steam_msg and self.steam:
                for frame in await asyncio.to_thread(self.steam.all_frames):
                    await self.send_board(frame)
            art = self.media.current_art()
            if art:
                await self.send_board(art)
            async for raw in ws:
                try:
                    await self.handle(raw)
                except Exception as e:
                    log.warning("bad message from hub: %s", e)

    async def run(self):
        self.loop = asyncio.get_running_loop()
        if self.use_web:
            await self.start_web()
        if self.power:
            self.power.start()
        spawn = self.supervisor.spawn   # a loop that crashes is restarted, not left dead
        spawn("stats", self.stats_loop)
        spawn("media", self.media_loop)
        spawn("calendar", self.calendar_loop)
        spawn("ai usage", self.claude_loop)
        spawn("weather", self.weather_loop)
        if any(t["state"] for t in self.tiles):
            spawn("tile states", self.tiles_loop)
        if self.alerts:
            spawn("claude alerts", self.alerts_loop)
        if "printer" in enabled_pages(self.cfg):
            spawn("printers", self.printer_loop)
        if self.steam:
            spawn("steam", self.steam_loop)
        if self.github:
            spawn("github", self.github_loop)
        if self.net:
            spawn("internet", self.net_loop)
            hours = float(self.cfg.get("internet", {}).get("speedtest_hours", 0))
            if hours > 0:
                spawn("speed test schedule", lambda: self.speedtest_schedule(hours))
        if not self.use_board:
            await asyncio.Event().wait()   # the browser hub runs in the background
        delay = 2
        while True:
            try:
                await self.session()
                delay = 2
            except (OSError, asyncio.TimeoutError, websockets.WebSocketException, RuntimeError) as e:
                log.info("hub not reachable at %s (%s), retrying in %ds", self.url, e, delay)
            finally:
                self.ws = None
                self.status(False, f"looking for {self.host}")
            # A link that came up and later dropped (e.g. the hub rebooted) retries fast.
            if self.connected_once:
                self.connected_once = False
                delay = 2
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--log", help=f"log to this file (default when started hidden: {LOG_FILE})")
    ap.add_argument("--tray", action="store_true", help="show an icon in the notification area")
    ap.add_argument("--new-token", action="store_true",
                    help="make a new phone pairing code and exit (every phone must pair again)")
    ap.add_argument("--no-guardian", action="store_true",
                    help="with --tray: do not watch the companion and restart it if it dies")
    ap.add_argument("--child", type=int, metavar="GUARDIAN_PID", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.new_token:
        new_token()
        print("A new pairing code is saved. Restart the companion, then pair each phone again\n"
              "(open http://localhost:<port>/setup on this PC and scan the QR code).")
        return
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    level = logging.DEBUG if args.verbose else logging.INFO
    # Started hidden (pythonw, e.g. from the login shortcut) there's no console to log to.
    log_file = pathlib.Path(args.log) if args.log else LOG_FILE if sys.stderr is None else None
    if log_file:
        from logging.handlers import RotatingFileHandler

        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
        logging.basicConfig(level=level, format=fmt, handlers=[handler])
    else:
        logging.basicConfig(level=level, format=fmt)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not args.child and not single_instance():   # a guarded companion: the guardian holds the lock
        # Two companions would keep knocking each other off the board.
        log.error("the companion is already running (maybe started with Windows); not starting another")
        sys.exit("The Desk Hub companion is already running. Stop that one first.")
    if args.child:   # started by the guardian: end if it (or whatever started us) goes away
        from .guardian import watch_parents

        def _guardian_gone():
            log.info("the guardian is gone; stopping")
            os._exit(0)

        watch_parents([args.child, os.getppid()], _guardian_gone)
    path = find_config(args.config)
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    log.info("using %s", path)
    companion = Companion(cfg)
    if args.tray:
        from .tray import Tray

        def restart():
            # A fresh process re-reads config.toml and rebuilds everything cleanly.
            log.info("restarting from the tray")
            if args.child:
                from .guardian import RESTART_CODE

                os._exit(RESTART_CODE)   # the guardian starts a fresh companion at once
            release_instance()
            subprocess.Popen([sys.executable, "-m", "deskhub", *sys.argv[1:]], cwd=os.getcwd())
            os._exit(0)

        def quit_():
            log.info("quit from the tray")
            os._exit(0)

        tray = Tray(path.resolve(), log_file, restart, quit_)
        if tray.start():
            companion.on_status = tray.set_status
    try:
        asyncio.run(companion.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
