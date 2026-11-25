"""DeskHub for Windows: the app you download and run.

Starts the companion (the server your phone connects to), puts an icon near the clock and opens the control
panel, where you choose what the phone shows and scan a QR code to show it. Its settings live in
%APPDATA%\\DeskHub\\config.toml (made on the first run).

    DeskHub.exe                # open the control panel
    DeskHub.exe --background   # start quietly (what "Start with Windows" does)
"""
import argparse
import asyncio
import logging
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import threading
import time
import tomllib
import urllib.request

import tomlkit

from . import install_startup
from .__main__ import Companion, release_instance, single_instance
from .panel import Panel, open_window

APP_VERSION = "0.2.0"
APP_DIR = pathlib.Path(os.environ.get("DESKHUB_APP_DIR")   # tests use their own folder
                       or pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home() / "AppData" / "Roaming")) / "DeskHub")
CONFIG = APP_DIR / "config.toml"
LOG_FILE = APP_DIR / "deskhub.log"
DEFAULT_PORT = 8787

log = logging.getLogger("deskhub.app")


def bundled(name: str) -> pathlib.Path:
    """A file shipped with the app: next to the exe's unpacked files, or in the project when run from source."""
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent.parent))
    return base / name


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def ensure_config() -> bool:
    """Make config.toml from the example on the first run. Returns True when it was just made."""
    if CONFIG.is_file():
        return False
    APP_DIR.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.parse(bundled("config.example.toml").read_text(encoding="utf-8"))
    port = DEFAULT_PORT
    if not port_free(port):   # another program has it: take the next free one, once, and remember it
        port = next((p for p in range(8790, 8900) if port_free(p)), DEFAULT_PORT)
    if "web" not in doc:
        doc["web"] = tomlkit.table()
    doc["web"]["port"] = port
    CONFIG.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return True


def relaunch():
    """Start this app again (it re-reads config.toml) and end this process."""
    log.info("restarting")
    release_instance()
    args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "deskhub.app"]
    subprocess.Popen(args + ["--background"], cwd=str(APP_DIR), close_fds=True)
    os._exit(0)


def panel_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/panel"


def open_panel(port: int):
    open_window(panel_url(port), APP_DIR / "panel-profile")


def wait_then_open(port: int):
    """Open the panel window once the server answers."""
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2).read()
            open_panel(port)
            return
        except OSError:
            time.sleep(0.5)
    log.error("the server did not come up, so the control panel was not opened")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--background", action="store_true", help="start quietly, without opening the control panel")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    from logging.handlers import RotatingFileHandler

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=1, encoding="utf-8")])
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    first_run = ensure_config()
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    port = int((cfg.get("web") or {}).get("port", DEFAULT_PORT))

    if not single_instance("Local\\DeskHubApp"):   # already running: just bring up its control panel
        log.info("DeskHub is already running; opening its control panel")
        open_panel(port)
        return

    log.info("DeskHub %s using %s", APP_VERSION, CONFIG)
    companion = Companion(cfg)
    panel = Panel(CONFIG, companion.sound_outputs, relaunch, startup=install_startup, version=APP_VERSION)
    companion.panel = panel

    from .tray import Tray

    def quit_():
        log.info("quit from the tray")
        os._exit(0)

    tray = Tray(CONFIG, LOG_FILE, relaunch, quit_, on_open=lambda: open_panel(port))
    if tray.start():
        companion.on_status = tray.set_status
    if first_run or not args.background:
        threading.Thread(target=wait_then_open, args=(port,), daemon=True, name="open-panel").start()
    try:
        asyncio.run(companion.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
