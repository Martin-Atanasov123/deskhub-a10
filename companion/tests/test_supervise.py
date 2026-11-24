"""Background loops: restarted after a crash, and resting while no display is connected.

    uv run python tests/test_supervise.py
"""
import asyncio
import logging
import sys
import time

from deskhub.supervise import Pacer, Supervisor

logging.disable(logging.CRITICAL)
problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


async def main():
    # ---- Supervisor ----
    sup = Supervisor(base_delay=0.05, max_delay=0.2)
    runs = []

    async def flaky():
        runs.append(time.monotonic())
        if len(runs) < 3:
            raise ValueError("boom")
        while True:
            await asyncio.sleep(0.01)

    task = sup.spawn("flaky", flaky)
    await asyncio.sleep(0.5)
    check(len(runs) == 3, f"a loop that crashed twice runs a third time and stays up: {len(runs)} runs")
    check(sup.restarts.get("flaky") == 2, f"restarts counted: {sup.restarts}")
    check(runs[2] - runs[1] > runs[1] - runs[0], "the pause grows between restarts")
    check(not task.done(), "the supervised loop is still running")

    finished = []

    async def one_shot():
        finished.append(1)

    sup.spawn("one", one_shot)
    await asyncio.sleep(0.2)
    check(finished == [1], "a loop that ends on purpose is not restarted")

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    check(task.cancelled(), "cancelling a supervised loop stops it (no restart)")

    # backoff starts over after a stable run
    sup2 = Supervisor(base_delay=0.05, max_delay=1.0, stable_after=0.15)
    starts = []

    async def stable_then_crash():
        starts.append(time.monotonic())
        await asyncio.sleep(0.2 if len(starts) == 2 else 0.01)
        raise RuntimeError("x")

    t2 = sup2.spawn("s", stable_then_crash)
    await asyncio.sleep(0.9)
    t2.cancel()
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    check(len(gaps) >= 3 and gaps[2] < gaps[1] + 0.1, f"after a stable run the pause is short again: {gaps}")

    # ---- Pacer ----
    watched = [True]
    pacer = Pacer(lambda: watched[0], idle_s=5)
    t0 = time.monotonic()
    await pacer.sleep(0.1)
    check(0.09 < time.monotonic() - t0 < 0.4, "with a display connected it sleeps exactly as asked")

    watched[0] = False
    t0 = time.monotonic()
    waiter = asyncio.create_task(pacer.sleep(0.1))
    await asyncio.sleep(0.4)
    check(not waiter.done(), "with nobody watching it keeps resting well past the normal pause")
    pacer.wake()
    await asyncio.wait_for(waiter, 1)
    check(time.monotonic() - t0 < 1.5, "a display connecting wakes it at once")

    quick = Pacer(lambda: False, idle_s=0.2)
    t0 = time.monotonic()
    await quick.sleep(0.01)
    check(0.15 < time.monotonic() - t0 < 0.6, "with nobody watching it still wakes up by itself after the idle time")

    # many loops rest on one pacer and all wake together
    pacer2 = Pacer(lambda: False, idle_s=5)
    loops = [asyncio.create_task(pacer2.sleep(1)) for _ in range(5)]
    await asyncio.sleep(0.1)
    pacer2.wake()
    done, pending = await asyncio.wait(loops, timeout=1)
    check(not pending, f"every resting loop wakes: {len(pending)} still resting")

    # ---- following the displays' power mode ----
    factor = [4.0]
    slow = Pacer(lambda: True, idle_s=5, scale=lambda: factor[0], max_s=0.5)
    t0 = time.monotonic()
    await slow.sleep(0.1)
    check(0.35 < time.monotonic() - t0 < 0.7, f"every display wants slower updates: the loop sleeps 4x as long: {time.monotonic() - t0:.2f}")
    t0 = time.monotonic()
    await slow.sleep(0.1, scalable=False)
    check(time.monotonic() - t0 < 0.3, "a loop marked not scalable keeps its own pace")
    factor[0] = 100.0
    t0 = time.monotonic()
    await slow.sleep(0.1)
    check(time.monotonic() - t0 < 0.8, f"the slowdown is capped: {time.monotonic() - t0:.2f}")
    factor[0] = 0.0
    t0 = time.monotonic()
    await slow.sleep(0.1)
    check(time.monotonic() - t0 < 0.3, "a factor below 1 never speeds a loop up")
    factor[0] = 4.0
    t0 = time.monotonic()
    waiter = asyncio.create_task(slow.sleep(0.1))
    await asyncio.sleep(0.1)
    slow.wake()
    await asyncio.wait_for(waiter, 1)
    check(time.monotonic() - t0 < 0.3, "a display changing its mode wakes a slowed loop at once")


asyncio.run(main())
print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
sys.exit(1 if problems else 0)
