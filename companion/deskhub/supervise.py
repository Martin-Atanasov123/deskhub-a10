"""Keeping the companion's background loops alive and quiet.

Supervisor: a loop that dies on an unexpected error is restarted (with a growing pause) instead
of silently staying dead until the next restart of the whole program.

Pacer: a loop that polls Windows every second has nobody to tell when no display is connected.
While nobody is watching it sleeps long; the moment a display connects it is woken at once.
With a display connected it sleeps exactly as long as it always did.
"""
import asyncio
import logging
import time

log = logging.getLogger(__name__)


class Supervisor:
    def __init__(self, base_delay: float = 2.0, max_delay: float = 60.0, stable_after: float = 60.0,
                 clock=time.monotonic):
        self.base_delay, self.max_delay, self.stable_after, self.clock = base_delay, max_delay, stable_after, clock
        self.tasks: list[asyncio.Task] = []      # kept, so a task cannot be garbage collected mid-run
        self.restarts: dict[str, int] = {}

    def spawn(self, name: str, factory) -> asyncio.Task:
        """Run factory() (a function returning a coroutine) for as long as the program lives."""
        task = asyncio.create_task(self._run(name, factory), name=name)
        self.tasks.append(task)
        return task

    async def _run(self, name: str, factory):
        delay = self.base_delay
        while True:
            started = self.clock()
            try:
                await factory()
                return                                   # the loop ended on purpose
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.restarts[name] = self.restarts.get(name, 0) + 1
                if self.clock() - started >= self.stable_after:
                    delay = self.base_delay              # it ran fine for a while: start the backoff over
                log.error("%s stopped unexpectedly (%s: %s); restarting in %.0f s", name, type(e).__name__, e,
                          delay, exc_info=True)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_delay)


class Pacer:
    def __init__(self, audience, idle_s: float = 30.0, scale=None, max_s: float = 30.0):
        """audience(): True while any display is connected.
        scale(): how many times slower the loops may run, because every connected display
        wants fewer updates (1 = full speed, e.g. for the ESP32 board)."""
        self.audience, self.idle_s, self.scale, self.max_s = audience, idle_s, scale, max_s
        self._wake = asyncio.Event()

    def wake(self):
        """A display connected or changed its wishes: every resting loop runs its next round now."""
        self._wake.set()

    async def sleep(self, seconds: float, scalable: bool = True):
        if self.audience():
            timeout = seconds
            if scalable and self.scale:
                timeout = min(seconds * max(1.0, self.scale()), max(seconds, self.max_s))
        else:
            timeout = self.idle_s
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout)
        except asyncio.TimeoutError:
            pass
