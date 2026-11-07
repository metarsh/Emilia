import asyncio
import functools
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

process_pool = None
thread_pool = None
_shutting_down = False


def _get_pool(process):
    global process_pool, thread_pool
    if _shutting_down:
        raise RuntimeError("Executors are shutting down")
    if process:
        if process_pool is None:
            process_pool = ProcessPoolExecutor(max_workers=min(4, os.cpu_count() or 1))
        return process_pool
    if thread_pool is None:
        thread_pool = ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 1) + 4))
    return thread_pool


async def run_in_process(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(_get_pool(True), call)


async def run_in_thread(func, *args, **kwargs):
    call = functools.partial(func, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(_get_pool(False), call)


async def shutdown_executors():
    global process_pool, thread_pool, _shutting_down
    _shutting_down = True
    for pool in (process_pool, thread_pool):
        if pool is not None:
            await asyncio.to_thread(pool.shutdown, wait=True, cancel_futures=True)
    process_pool = thread_pool = None
