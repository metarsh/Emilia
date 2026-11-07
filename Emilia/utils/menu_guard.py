from collections.abc import Callable
from dataclasses import dataclass
from inspect import isawaitable

from pyrogram.enums import ChatType

from Emilia.application import redis_client
from Emilia.locales import tr


def callback_is_present(client, query) -> bool:
    from Emilia.utils.client_context import bot_id

    message = query.message
    if (
        not message
        or not query.from_user
        or not message.chat
        or getattr(message, "empty", False)
        or getattr(message, "forward_origin", None)
    ):
        return False
    if message.chat.type == ChatType.PRIVATE and message.chat.id != query.from_user.id:
        return False
    author = getattr(message, "from_user", None)
    channel_post = (
        message.chat.type == ChatType.CHANNEL
        and message.outgoing is True
        and message.sender_chat is not None
        and message.sender_chat.id == message.chat.id
    )
    if not channel_post and (author is None or author.id != bot_id(client)):
        return False
    markup = getattr(message, "reply_markup", None)
    return bool(query.data) and any(
        query.data == button.callback_data
        for row in (getattr(markup, "inline_keyboard", None) or ())
        for button in row
    )


MENU_TTL = 86400  # a day-old menu is scrollback, not a live workspace
TAP_TTL = 5  # long enough to cover a slow handler, short enough to not annoy


def bot_namespace(client=None) -> str:
    from Emilia.config import Config
    from Emilia.utils.client_context import bot_id

    return f"{Config.CACHE_NAMESPACE or Config.MONGO_DATABASE}:{bot_id(client)}"


def _menu_key(chat_id: int, message_id: int, client=None) -> str:
    return f"menu_owner:{bot_namespace(client)}:{chat_id}:{message_id}"


async def remember_menu(message, user_id: int, ttl: int = MENU_TTL, *, client=None) -> None:
    client = client or getattr(message, "_client", None)
    await redis_client.set(_menu_key(message.chat.id, message.id, client), str(user_id), ex=ttl)


async def _resolve(value, client, query):
    result = value(client, query) if callable(value) else value
    return await result if isawaitable(result) else result


@dataclass(frozen=True)
class CallbackAccess:
    public: bool | Callable = False
    user_id: int | Callable | None = None
    chat_id: int | Callable | None = None
    owner: bool = False
    privilege: str | None = None
    account_resolver: Callable | None = None
    allow_admin: bool = False
    denial: str | None = None

    def __post_init__(self):
        if (self.owner or self.privilege) and self.chat_id is None:
            raise ValueError("Chat permissions require a chat_id")

    async def resolve_owner(self, client, query) -> int | None:
        if self.user_id is not None:
            return await _resolve(self.user_id, client, query)
        raw = await redis_client.get(_menu_key(query.message.chat.id, query.message.id, client))
        try:
            owner_id = int(raw)
        except (TypeError, ValueError):
            return None
        return owner_id or None

    async def resolve_chat(self, client, query) -> int | None:
        return (
            await _resolve(self.chat_id, client, query)
            if self.chat_id is not None
            else query.message.chat.id
        )

    async def allows(self, client, query, *, notify: bool = True) -> bool:
        async def deny(key):
            if notify:
                await query.answer(tr(key), show_alert=True)
            return False

        if not callback_is_present(client, query):
            return await deny("custom_filter.this_button_has_expired")

        from Emilia.utils.chat_status import has_chat_permission

        # Public actions apply to the tapper, even on somebody else's menu.
        public = await _resolve(self.public, client, query)
        if not public and (self.chat_id is None or self.user_id is not None):
            owner_id = await self.resolve_owner(client, query)
            if not isinstance(owner_id, int) or isinstance(owner_id, bool):
                return await deny(self.denial or "menu.owner_required")
            allowed = owner_id > 0 and query.from_user.id == owner_id
            if owner_id < 0 and self.account_resolver is not None:
                allowed = await self.account_resolver(owner_id, client=client) == query.from_user.id
            if not allowed and self.allow_admin:
                allowed = await has_chat_permission(
                    client, await self.resolve_chat(client, query), query.from_user.id
                )
            if not allowed:
                return await deny(self.denial or "menu.owner_required")

        if self.chat_id is not None:
            chat_id = await self.resolve_chat(client, query)
            if chat_id is None or not await has_chat_permission(
                client, chat_id, query.from_user.id, owner=self.owner, privilege=self.privilege
            ):
                return await deny(
                    self.denial
                    or (
                        "permissions.owner_required" if self.owner else "permissions.admin_required"
                    )
                )
        return True


async def claim_tap(scope: int, key: str, ttl: int = TAP_TTL, *, client=None) -> bool:
    return bool(
        await redis_client.set(
            f"menu_tap:{bot_namespace(client)}:{scope}:{key}", "1", ex=ttl, nx=True
        )
    )
