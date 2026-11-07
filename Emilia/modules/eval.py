import asyncio
import os
import sys
from pathlib import Path

from Emilia.config import Config
from Emilia.custom_filter import auth
from Emilia.locales import tr
from Emilia.utils.executors import run_in_thread
from Emilia.utils.operator import (
    MAX_OUTPUT_BYTES,
    evaluate_command,
    operator_only,
    send_operator_result,
    terminal_command,
)


@auth(pattern="exec")
@operator_only
async def exec_command(client, message):
    return await terminal_command(client, message)


@auth(pattern="eval")
@operator_only
async def eval_command(client, message):
    return await evaluate_command(client, message)


@auth(pattern="restart")
@operator_only
async def restart_command(client, message):
    await asyncio.wait_for(
        message.reply_text(tr("clone.restarting")), timeout=Config.OPERATOR_TIMEOUT
    )
    os.execv(sys.executable, [sys.executable, "-m", "Emilia"])


def _read_log_tail():
    with Path(Config.LOG_FILE).open("rb") as logfile:
        logfile.seek(0, os.SEEK_END)
        logfile.seek(max(0, logfile.tell() - MAX_OUTPUT_BYTES))
        return logfile.read(MAX_OUTPUT_BYTES).decode("utf-8", errors="replace")


@auth(pattern="logs")
@operator_only
async def logs_command(client, message):
    result = await asyncio.wait_for(run_in_thread(_read_log_tail), timeout=Config.OPERATOR_TIMEOUT)
    return await send_operator_result(message, result or tr("eval.log_empty"))
