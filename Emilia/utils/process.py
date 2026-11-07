import asyncio
import os
import signal
from dataclasses import dataclass

from Emilia.utils.tasks import finish_cleanup


@dataclass(frozen=True)
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int
    pid: int
    truncated: bool


async def run_process(*args, timeout=30, max_output_bytes=64 * 1024, merge_stderr=False):
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT if merge_stderr else asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    async def read(stream):
        output = bytearray()
        truncated = False
        if stream is not None:
            while chunk := await stream.read(65536):
                remaining = max(0, max_output_bytes - len(output))
                output.extend(chunk[:remaining])
                truncated |= len(chunk) > remaining
        return output.decode("utf-8", errors="replace"), truncated

    async def collect():
        stdout, stderr = await asyncio.gather(read(process.stdout), read(process.stderr))
        returncode = await process.wait()
        return ProcessResult(stdout[0], stderr[0], returncode, process.pid, stdout[1] or stderr[1])

    collector = asyncio.create_task(collect())
    try:
        return await asyncio.wait_for(asyncio.shield(collector), timeout=timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

        async def cleanup():
            await asyncio.gather(collector, return_exceptions=True)
            await process.wait()

        await finish_cleanup(cleanup())
        raise
