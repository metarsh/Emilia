import asyncio
import logging

LOGGER = logging.getLogger(__name__)
_BACKGROUND_TASKS = set()
_shutting_down = False


async def finish_cleanup(awaitable):
    task = asyncio.ensure_future(awaitable)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


def spawn(coro, *, name: str) -> asyncio.Task:
    if _shutting_down:
        coro.close()
        raise RuntimeError("Background tasks are shutting down")
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)

    def done(completed):
        _BACKGROUND_TASKS.discard(completed)
        if not completed.cancelled():
            error = completed.exception()
            if error is not None:
                LOGGER.error("Background task %s failed", completed.get_name(), exc_info=error)

    task.add_done_callback(done)
    return task


async def shutdown_background_tasks():
    global _shutting_down
    _shutting_down = True
    current = asyncio.current_task()
    tasks = [task for task in _BACKGROUND_TASKS if task is not current]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
