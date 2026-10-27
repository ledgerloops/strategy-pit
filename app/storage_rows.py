"""Named and positional records for the protocol's small DB-API surface."""


class Row:
    def __init__(self, cursor, values):
        self._values = tuple(values)
        self._names = tuple(column[0] for column in cursor.description)

    def __getitem__(self, key):
        return self._values[self._names.index(key)] if isinstance(key, str) else self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._names)
