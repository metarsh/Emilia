import time

from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.admins import get_time

START_TIME = time.monotonic()


@command("ping", disable=True)
async def ping(client, event):
    start_time = time.monotonic()
    message = await event.reply(tr("ping.pinging"))
    end_time = time.monotonic()
    telegram_ping = str(round((end_time - start_time) * 1000, 3)) + " ms"
    uptime = get_time(int(end_time - START_TIME))

    await message.edit(
        tr("ping.pong_time_taken_service_uptime", telegram_ping=telegram_ping, uptime=uptime)
    )
