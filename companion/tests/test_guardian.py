"""The guardian: restarts the companion after a crash, honours Quit and Restart, backs off, never loops
at full speed, and a companion cannot outlive its guardian.

    uv run python tests/test_guardian.py
"""
import logging
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

from deskhub import guardian
from deskhub.guardian import RESTART_CODE, next_step, run_guardian, watch_parents

logging.disable(logging.CRITICAL)
problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


# ---- the decision table ----
check(next_step(0, 5, 2) == (False, 0.0, 2.0), "a clean exit ends the guardian")
check(next_step(RESTART_CODE, 5, 8) == (True, 0.5, 2.0), "Restart starts again at once and resets the pause")
check(next_step(1, 3, 2) == (True, 2.0, 4.0), "a crash waits 2 s, then 4 s next time")
check(next_step(1, 3, 4) == (True, 4.0, 8.0), "the pause doubles")
check(next_step(1, 3, 200) == (True, 200.0, 300.0), "the pause is capped at 5 minutes")
check(next_step(1, 150, 64) == (True, 2.0, 4.0), "after a run of 2 minutes or more the pause starts over")
check(next_step(3221225477, 1, 2)[0] is True, "a Windows crash code is a crash, not a quit")


# ---- the loop, with a fake process ----
class FakeProc:
    def __init__(self, code):
        self.code = code

    def wait(self):
        return self.code

    def terminate(self):
        pass


def run_fake(codes, runtimes=None):
    waits, started = [], []
    clock = [0.0]
    it = iter(codes)
    rt = iter(runtimes or [])

    def popen(cmd, **kw):
        started.append((cmd, kw))
        clock[0] += next(rt, 1.0)      # how long this run "lasted"
        return FakeProc(next(it))

    rc = run_guardian(["--tray", "--config", "x.toml"], popen=popen, sleep=waits.append, clock=lambda: clock[0],
                      lock=lambda: True, setup_log=False)
    return rc, waits, started


rc, waits, started = run_fake([1, 1, RESTART_CODE, 0])
check(rc == 0, "the guardian returns 0 once the companion quits")
check(waits == [2.0, 4.0, 0.5], f"pauses after crash, crash, Restart: {waits}")
check(len(started) == 4, f"four runs: {len(started)}")
cmd = started[0][0]
check(cmd[1:4] == ["-m", "deskhub", "--tray"] and cmd[-2] == "--child" and cmd[-1] == str(os.getpid()),
      f"the companion is started with the same arguments plus --child <guardian pid>: {cmd}")
check(started[0][1]["stdin"] == subprocess.DEVNULL and started[0][1]["stdout"] == subprocess.DEVNULL,
      "no console handles are passed on (a hidden process has none)")

rc, waits, _ = run_fake([1, 1, 1, 1, 0], runtimes=[1, 1, 200, 1, 1])
check(waits == [2.0, 4.0, 2.0, 4.0], f"a long run resets the pause: {waits}")

rc, waits, _ = run_fake([1] * 12 + [0])
check(max(waits) == 300.0 and waits == sorted(waits), f"a crash loop slows down to 5 minutes and stays there: {waits}")

try:
    run_guardian(["--tray"], lock=lambda: False, setup_log=False)
    check(False, "a second guardian must not start")
except SystemExit as e:
    check("already running" in str(e), f"the 'already running' message: {e}")

# ---- real processes: a child that crashes twice, then quits ----
tmp = pathlib.Path(tempfile.mkdtemp())
counter = tmp / "runs.txt"
script = tmp / "child.py"
script.write_text(
    "import pathlib, sys\n"
    f"p = pathlib.Path(r'{counter}')\n"
    "n = int(p.read_text()) + 1 if p.exists() else 1\n"
    "p.write_text(str(n))\n"
    "sys.exit(1 if n < 3 else 0)\n", encoding="utf-8")
t0 = time.time()
rc = run_guardian([], child_cmd=[sys.executable, str(script)], lock=lambda: True, base_delay=0.05, setup_log=False)
check(rc == 0 and counter.read_text() == "3", f"real processes: crashed twice, third run quit cleanly (runs={counter.read_text()})")
check(time.time() - t0 < 10, "and it did not take long")

# ---- a companion cannot outlive its guardian ----
sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
gone = threading.Event()
watch_parents([os.getpid(), sleeper.pid], gone.set, interval=0.1)
time.sleep(0.5)
check(not gone.is_set(), "nothing happens while the guardian is alive")
sleeper.kill()
sleeper.wait()
check(gone.wait(3), "when a watched process ends, the companion is told to stop")

gone2 = threading.Event()
watch_parents([2_000_000_000], gone2.set, interval=0.1)
check(gone2.wait(2), "a guardian that is already gone stops the companion at once")

print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
sys.exit(1 if problems else 0)
