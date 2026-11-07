from copy import copy
from dataclasses import dataclass, field

from pyrogram.enums import MessageEntityType
from pyrogram.types import MessageEntity, User


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


@dataclass
class FormattedText:
    text: str
    entities: list[MessageEntity] = field(default_factory=list)

    def record(self) -> dict:
        entities = []
        for entity in self.entities:
            data = {"type": entity.type.name, "offset": entity.offset, "length": entity.length}
            for attr in (
                "url",
                "language",
                "custom_emoji_id",
                "expandable",
                "unix_time",
                "date_time_format",
            ):
                if getattr(entity, attr, None) is not None:
                    data[attr] = getattr(entity, attr)
            if entity.user is not None:
                data["user"] = {
                    attr: getattr(entity.user, attr)
                    for attr in ("id", "first_name", "last_name", "username")
                }
            entities.append(data)
        return {"text": self.text, "entities": entities}

    def splice(self, start: int, end: int, replacement: str, entities=()):
        left, right = utf16_length(self.text[:start]), utf16_length(self.text[:end])
        width = utf16_length(replacement)
        delta = width - (right - left)
        rebased = []
        for original in self.entities:
            first, last = original.offset, original.offset + original.length
            formatting = original.type in {
                MessageEntityType.BOLD,
                MessageEntityType.ITALIC,
                MessageEntityType.UNDERLINE,
                MessageEntityType.STRIKETHROUGH,
                MessageEntityType.SPOILER,
                MessageEntityType.BLOCKQUOTE,
            }
            if formatting and first == left and last == right and width:
                entity = copy(original)
                entity.length = width
                rebased.append(entity)
                continue
            if first >= left and last <= right and right > left:
                continue
            entity = copy(original)
            if first >= right:
                first += delta
            elif first > left:
                first = left
            if last > right:
                last += delta
            elif last > left:
                last = left + width
            if last > first:
                entity.offset, entity.length = first, last - first
                rebased.append(entity)
        for original in entities:
            entity = copy(original)
            entity.offset += left
            rebased.append(entity)
        return FormattedText(
            self.text[:start] + replacement + self.text[end:],
            sorted(rebased, key=lambda entity: (entity.offset, -entity.length)),
        )

    def slice(self, start: int, end: int | None = None):
        end = len(self.text) if end is None else end
        value = self.splice(end, len(self.text), "")
        return value.splice(0, start, "")


def text_value(value) -> str:
    if isinstance(value, FormattedText):
        return value.text
    if isinstance(value, dict):
        return value["text"]
    return value or ""


def formatted_text(value) -> FormattedText:
    if isinstance(value, FormattedText):
        return value
    if not isinstance(value, dict):
        raise TypeError("Saved message text must be an entity record")
    entities = []
    for record in value.get("entities", []):
        data = dict(record)
        data["type"] = MessageEntityType[data["type"]]
        if data.get("user"):
            data["user"] = User(**data["user"])
        entities.append(MessageEntity(**data))
    return FormattedText(value["text"], entities)


def replace_range(value, start, end, replacement, entities=()):
    return formatted_text(value).splice(start, end, replacement, entities)


def replace_content(value, old, new):
    text = text_value(value)
    starts, position = [], 0
    while (position := text.find(old, position)) >= 0:
        starts.append(position)
        position += len(old)
    for start in reversed(starts):
        value = replace_range(value, start, start + len(old), new)
    return value


def prefix_content(value, prefix: str):
    return replace_range(value, 0, 0, prefix)
