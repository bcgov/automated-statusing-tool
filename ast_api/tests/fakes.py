"""In-memory stand-ins for the services the API talks to, for the tests."""


class FakeRedis:
    """The few Redis commands the API and the worker use, kept in memory.

    Lists back the job queue (rpush / lrange / lpop) and plain keys back the job
    status store (set / get). Values are returned as they were stored, the way
    a client created with decode_responses=True returns them.
    """

    def __init__(self):
        self._lists = {}
        self._values = {}

    def rpush(self, key, value):
        self._lists.setdefault(key, []).append(value)

    def lrange(self, key, start, end):
        stop = None if end == -1 else end + 1
        return self._lists.get(key, [])[start:stop]

    def lpop(self, key):
        items = self._lists.get(key, [])
        return items.pop(0) if items else None

    def set(self, key, value, ex=None):
        self._values[key] = value

    def get(self, key):
        return self._values.get(key)
