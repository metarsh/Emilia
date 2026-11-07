from collections import OrderedDict
from collections.abc import MutableMapping
from time import monotonic

from Emilia.config import Config


class QueryCache(MutableMapping):
    def __init__(self):
        self._items = OrderedDict()

    def _purge(self):
        now = monotonic()
        while self._items and next(iter(self._items.values()))[1] <= now:
            self._items.popitem(last=False)

    def __getitem__(self, key):
        self._purge()
        return self._items[key][0]

    def __setitem__(self, key, value):
        self._purge()
        self._items.pop(key, None)
        self._items[key] = (value, monotonic() + Config.CACHE_QUERY_TTL)
        while len(self._items) > Config.CACHE_QUERY_MAX_ENTRIES:
            self._items.popitem(last=False)

    def __delitem__(self, key):
        self._purge()
        del self._items[key]

    def __iter__(self):
        self._purge()
        return iter(self._items)

    def __len__(self):
        self._purge()
        return len(self._items)
