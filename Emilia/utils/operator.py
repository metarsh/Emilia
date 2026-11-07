import functools
import json
import sys

from pyrogram.enums import ChatType, ParseMode

from Emilia.config import Config
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.process import run_process

MAX_OUTPUT_BYTES = 64 * 1024
MAX_INPUT_BYTES = 16 * 1024


def operator_allowed(client, message):
    user = getattr(message, "from_user", None)
    chat = getattr(message, "chat", None)
    if not user or user.id != Config.OWNER_ID or not chat:
        return False
    if chat.type != ChatType.PRIVATE or chat.id != Config.OWNER_ID:
        return False
    from Emilia.application import pgram

    return client is pgram


def operator_only(handler):
    @functools.wraps(handler)
    async def wrapped(client, message, *args, **kwargs):
        if operator_allowed(client, message):
            return await handler(client, message, *args, **kwargs)

    return wrapped


async def run_operator_process(*args, timeout=None):
    completed = await run_process(
        *args,
        timeout=Config.OPERATOR_TIMEOUT if timeout is None else timeout,
        max_output_bytes=MAX_OUTPUT_BYTES,
        merge_stderr=True,
    )
    result = completed.stdout
    if completed.truncated:
        result += tr("operator.output_truncated")
    if completed.returncode:
        result += tr("operator.exit_status", returncode=completed.returncode)
    return result or "Success"


def _snapshot(message):
    if message is None:
        return None
    chat = getattr(message, "chat", None)
    user = getattr(message, "from_user", None)
    return {
        "id": getattr(message, "id", None),
        "text": str(getattr(message, "text", None) or "")[:MAX_INPUT_BYTES],
        "caption": str(getattr(message, "caption", None) or "")[:MAX_INPUT_BYTES],
        "chat": {"id": getattr(chat, "id", None)},
        "from_user": {"id": getattr(user, "id", None)},
    }


async def run_evaluation(code, message):
    if len(code.encode()) > MAX_INPUT_BYTES:
        raise ValueError("Operator input exceeds the size limit")
    data = _snapshot(message)
    data["reply_to_message"] = _snapshot(getattr(message, "reply_to_message", None))
    runner = (
        "import asyncio,json,sys\nfrom types import SimpleNamespace\n"
        "def ns(value):\n return SimpleNamespace(**{k:ns(v) for k,v in value.items()}) if isinstance(value,dict) else value\n"
        "message=ns(json.loads(sys.argv[2]))\n"
        "source='async def evaluate(client,message):\\n event=e=message\\n r=message.reply_to_message\\n chat=message.chat.id\\n p=print'+''.join('\\n '+line for line in sys.argv[1].split('\\n'))\n"
        "exec(compile(source,'<operator>','exec'))\nasyncio.run(evaluate(None,message))\n"
    )
    return await run_operator_process(sys.executable, "-I", "-c", runner, code, json.dumps(data))


async def run_terminal(code):
    if len(code.encode()) > MAX_INPUT_BYTES:
        raise ValueError("Operator input exceeds the size limit")
    return await run_operator_process("/bin/sh", "-c", code)


async def send_operator_result(message, result):
    if len(result) <= 4000:
        return await message.reply_text(result, parse_mode=ParseMode.DISABLED)
    import io

    with io.BytesIO(result.encode()) as document:
        document.name = "operator-output.txt"
        return await message.reply_document(document)


async def evaluate_command(client, message):
    parts = (message.text or "").split(None, 1)
    if len(parts) < 2:
        return await reply_usage(message)
    try:
        result = await run_evaluation(parts[1], message)
    except TimeoutError:
        result = tr("operator.operator_command_timed_out")
    return await send_operator_result(message, result)


async def terminal_command(client, message):
    parts = (message.text or "").split(None, 1)
    if len(parts) < 2:
        return await reply_usage(message)
    try:
        result = await run_terminal(parts[1])
    except TimeoutError:
        result = tr("operator.operator_command_timed_out")
    return await send_operator_result(message, result)
