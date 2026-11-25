"""The control panel: a page on this PC (and only this PC) where you choose what the phone shows.

`Panel.register` adds its routes to the web display's server. Every one of them answers only a request that comes
from this PC itself, under this PC's own name (so a phone, or a web page on another site, gets "Forbidden"), and
every change must also come from the panel's own page (same Origin, plus a header a plain form cannot send).
`open_window` shows the page in its own window, using Edge or Chrome in app mode.
"""
import asyncio
import logging
import os
import pathlib
import shutil
import subprocess
import webbrowser

from aiohttp import web

from . import panel_config
from .web_server import LOOPBACK, lan_ips, pair_url, qr_svg

log = logging.getLogger(__name__)

PANEL_DIR = pathlib.Path(__file__).resolve().parent / "panel_web"


def _browser() -> str | None:
    """Edge (on every Windows 10/11) or Chrome."""
    roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    names = (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe")
    for name in names:
        for root in roots:
            if root and (pathlib.Path(root) / name).is_file():
                return str(pathlib.Path(root) / name)
    return shutil.which("msedge") or shutil.which("chrome")


def open_window(url: str, profile: pathlib.Path | None = None) -> None:
    """Show the panel in its own window (no tabs, no address bar); the default browser if there is no Edge/Chrome."""
    exe = _browser()
    if exe:
        args = [exe, f"--app={url}", "--window-size=1040,780", "--no-first-run", "--no-default-browser-check"]
        if profile:
            profile.mkdir(parents=True, exist_ok=True)
            args.append(f"--user-data-dir={profile}")   # its own profile: it never touches your browsing
        try:
            subprocess.Popen(args)
            return
        except OSError as e:
            log.warning("could not open the panel window: %s", e)
    webbrowser.open(url)


class Panel:
    """config_path: the config.toml to edit. outputs(): async, the names of the PC's sound outputs.
    restart(): applies a saved config (the app starts again). startup: object with installed/install/remove."""

    def __init__(self, config_path: pathlib.Path, outputs, restart, startup=None, version: str = ""):
        self.config_path = config_path
        self.outputs, self.restart, self.startup, self.version = outputs, restart, startup, version
        self.hub = None

    # ---- routes ------------------------------------------------------------------

    def register(self, app: web.Application, hub) -> None:
        self.hub = hub
        app.router.add_get("/panel", self._page)
        app.router.add_get("/api/panel/state", self._state)
        app.router.add_post("/api/panel/save", self._save)
        app.router.add_post("/api/panel/restart", self._restart)
        app.router.add_post("/api/panel/startup", self._startup)

    def _guard(self, request, change: bool = False):
        if request.remote not in LOOPBACK or not self.hub._host_is_local(request):
            raise web.HTTPForbidden(text="the control panel opens on the PC itself")
        if change:
            if request.headers.get("Origin") != f"http://{request.host}" or request.headers.get("X-Panel") != "1":
                raise web.HTTPForbidden(text="this change must come from the control panel")

    async def _page(self, request):
        self._guard(request)
        return web.FileResponse(PANEL_DIR / "index.html")

    async def _state(self, request):
        self._guard(request)
        import tomllib

        cfg = tomllib.loads(self.config_path.read_text(encoding="utf-8"))
        ips = lan_ips() or ["127.0.0.1"]
        url = pair_url(ips[0], self.hub.port, self.hub.token)
        try:
            outputs = await self.outputs()
        except Exception as e:
            log.info("panel: no list of sound outputs (%s)", e)
            outputs = []
        phones = [{"ip": c["ip"], "ua": c["ua"][:120], "seconds": c["connected_s"]} for c in self.hub.diag()["clients"]]
        return web.json_response({
            "version": self.version, "port": self.hub.port,
            "pair": {"url": url, "qr": qr_svg(url), "others": [pair_url(ip, self.hub.port, self.hub.token) for ip in ips[1:]]},
            "phones": phones, "outputs": outputs,
            "startup": bool(self.startup and self.startup.installed()),
            "settings": panel_config.read_settings(cfg), "meta": panel_config.meta(),
        })

    async def _save(self, request):
        self._guard(request, change=True)
        try:
            data = await request.json()
            panel_config.save(self.config_path, data)
        except ValueError as e:   # includes bad JSON
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        log.info("panel: settings saved")
        return web.json_response({"ok": True})

    async def _restart(self, request):
        self._guard(request, change=True)
        asyncio.get_running_loop().call_later(0.4, self.restart)   # after this answer has gone out
        return web.json_response({"ok": True})

    async def _startup(self, request):
        self._guard(request, change=True)
        if not self.startup:
            return web.json_response({"ok": False, "error": "not available here"}, status=400)
        try:
            want = bool((await request.json()).get("enabled"))
            if want:
                self.startup.install()
            else:
                self.startup.remove()
        except (ValueError, OSError, subprocess.SubprocessError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
        return web.json_response({"ok": True, "enabled": self.startup.installed()})
