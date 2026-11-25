"""Named registries of things a config can select."""

import sys


class RegistryError(LookupError):
    """A name registered twice, or a name not registered."""


def place(depth):
    """The file and line of the frame `depth` levels above the caller."""
    frame = sys._getframe(depth + 1)
    return f"{frame.f_code.co_filename}:{frame.f_lineno}"


class Registry:
    """Things of one kind by name; `register(name)` is a decorator or, with the thing,
    a call."""

    def __init__(self, kind):
        self.kind = kind
        self.items = {}
        self.places = {}

    def register(self, name, item=None):
        """`item` under `name`, returned; without `item`, a decorator that registers
        what it decorates."""
        if item is None:

            def decorate(thing):
                self.add(name, thing, place(1))
                return thing

            return decorate
        return self.add(name, item, place(1))

    def add(self, name, item, where):
        """`item` under `name`, registered at `where`; a name taken is an error."""
        if name in self.items:
            raise RegistryError(
                f"{self.kind} {name!r} registered twice: at {self.places[name]} "
                f"and at {where}"
            )
        self.items[name] = item
        self.places[name] = where
        return item

    def get(self, name):
        """The thing registered under `name`."""
        if name not in self.items:
            known = ", ".join(self.names()) or "none"
            raise RegistryError(f"no {self.kind} {name!r}; registered: {known}")
        return self.items[name]

    def names(self):
        """The registered names, sorted."""
        return sorted(self.items)

    def __contains__(self, name):
        return name in self.items
