import asyncio

from apscheduler.events import EVENT_SCHEDULER_SHUTDOWN
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class ManagedScheduler(AsyncIOScheduler):
    async def aclose(self):
        if not self.running:
            return
        self.pause()
        # The pinned AsyncIOExecutor cancels these futures and clears its set;
        # capture them first so asynchronous job cleanup can finish.
        pending = tuple(
            future
            for executor in self._executors.values()
            for future in getattr(executor, "_pending_futures", ())
        )
        stopped = asyncio.get_running_loop().create_future()

        def on_shutdown(event):
            if not stopped.done():
                stopped.set_result(None)

        self.add_listener(on_shutdown, EVENT_SCHEDULER_SHUTDOWN)
        try:
            self.shutdown(wait=False)
            await stopped
            await asyncio.gather(*pending, return_exceptions=True)
        finally:
            self.remove_listener(on_shutdown)
