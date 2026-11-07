from Emilia.custom_filter import command
from Emilia.utils.operator import evaluate_command, operator_only


@command(
    ["prun", "peval"], prefixes=["?", "!", ".", "*", "/", "$"], chat_scope="private", access="owner"
)
@operator_only
async def peval_handler(client, message):
    return await evaluate_command(client, message)
