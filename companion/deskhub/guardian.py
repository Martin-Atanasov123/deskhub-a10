"""Keeps the companion running when it was started hidden (`--tray`, as the Startup shortcut does).

The guardian is a tiny process that runs the real companion as its child and starts it again if it dies:

* the companion exits with 0 (tray "Quit")            -> the guardian ends too;
* the companion exits with RESTART_CODE (tray "Restart") -> started again at once;
* anything else (a crash, "End task" on it)           -> started again after a pause that grows
  from 2 s up to 5 minutes, and starts over after a run of 2 minutes or more.

The guardian owns the "already running" lock. The child ends by itself if the guardian goes away, so
ending the guardian really stops everything. A plain console start (no `--tray`) is not guarded.
Its own small log is ~/.deskhub/guardian.log.
"""
import ctypes
import logging
import logging.handlers
import os
import pathlib
import subprocess
import sys
import threading
import time

RESTART_CODE = 75
MUTEX_NAME = "Local\\DeskHubCompanion"
LOG_FILE = pathlib.Path.home() / ".deskhub" / "guardian.log"
BASE_DELAY, MAX_DELAY, STABLE_AFTER = 2.0, 300.0, 120.0

log = logging.getLogger("deskhub.guardian")
_mutex = None


def next_step(code: int, ran_s: float, delay: float, base: float = BASE_DELAY, cap: float = MAX_DELAY,
              stable_after: float = STABLE_AFTER) -> tuple[bool, float, float]:
    """After the companion exited with `code` having run `ran_s` seconds:
    (start it again?, seconds to wait first, the pause to use if it crashes again)."""
    if code == 0:
        return False, 0.0, base
    if code == RESTART_CODE:
        return True, 0.5, base
    wait = base if ran_s >= stable_after else delay
    return True, wait, min(wait * 2, cap)


def take_lock() -> bool:
    """The same named lock the companion has always used: True if nobody else holds it."""
    global _mutex
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def _setup_log():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=200_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def run_guardian(argv: list[str], child_cmd: list[str] | None = None, popen=subprocess.Popen, sleep=time.sleep,
                 clock=time.monotonic, lock=take_lock, base_delay: float = BASE_DELAY, setup_log: bool = True) -> int:
    """Run the companion with `argv` and keep it running. Returns when it was told to quit."""
    if setup_log:
        _setup_log()
    if not lock():
        log.error("the companion is already running; not starting another")
        sys.exit("The Desk Hub companion is already running. Stop that one first.")
    cmd = child_cmd or [sys.executable, "-m", "deskhub", *argv, "--child", str(os.getpid())]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    delay = base_delay
    log.info("guardian %d started", os.getpid())
    while True:
        started = clock()
        proc = popen(cmd, cwd=os.getcwd(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags)
        try:
            code = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            return 0
        ran = clock() - started
        again, wait, delay = next_step(code, ran, delay, base_delay)
        if not again:
            log.info("the companion quit (code %s) after %.0f s; the guardian ends too", code, ran)
            return 0
        log.warning("the companion exited with code %s after %.0f s; starting it again in %.1f s", code, ran, wait)
        sleep(wait)


def watch_parents(pids: list[int], on_gone, interval: float = 5.0) -> threading.Thread:
    """In the companion: call on_gone() when any of these processes (the guardian and the process that started
    this one) is gone, so a companion can never outlive the guardian that is supposed to watch it."""
    import psutil

    watched, dead = [], False
    for pid in pids:
        try:
            p = psutil.Process(pid)
            watched.append((p, p.create_time()))
        except psutil.Error:
            dead = True

    def gone() -> bool:
        for p, created in watched:
            try:
                if not p.is_running() or p.create_time() != created:   # a reused process id is not the same process
                    return True
            except psutil.Error:
                return True
        return False

    def loop():
        if dead:
            on_gone()
            return
        while True:
            time.sleep(interval)
            if gone():
                on_gone()
                return

    t = threading.Thread(target=loop, daemon=True, name="guardian-watch")
    t.start()
    return t
