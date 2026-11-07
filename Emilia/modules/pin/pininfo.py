from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker


@command("pininfo", chat_scope="group")
@anonadmin_checker
async def pininfo(client, message):
    if not await is_user_admin(message):
        return

    await message.reply(tr("antichannelpin.antichannelpin_and_cleanlinked_can_t_be_enabled"))
