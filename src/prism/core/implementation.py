"""An implementation of items of the pipeline: its slots, its program on the card, its
host side and its check."""

from collections.abc import Callable
from dataclasses import dataclass

from prism_common.registry import Registry
from prism_common.slots import SLOTS


@dataclass(frozen=True)
class Command:
    """A thread command a host asks the loop for: its name, its words, and whether it
    runs views (writing a times row)."""

    name: str
    args: tuple = ()
    row: bool = True


def command_of(asked):
    """A Command of what a host's commands() gives: a Command, or a name (a command
    that runs views, without words)."""
    return asked if isinstance(asked, Command) else Command(asked)


class Host:
    """What an implementation's host tells the loop; each default does nothing. Made as
    `host(session, scene, options)`, then `prepare()` before its class is made, then
    `connect(assembled)` once every host is prepared, `bind(loaded)` once loaded. A host
    with layers holds them as `layers`, by name: the thread's follow the most a host
    holds; a host with views of its own holds them as `views` (view 1 on; 0 is the
    eye's)."""

    pictures = False  # whether picture() gives the frame's picture

    def prepare(self):
        """Everything its class and its frames need made (tensors, tables, capacity)."""

    def slots(self):
        """{slot: tensor} of the slots whose tensors it holds, for other hosts."""
        return {}

    def connect(self, assembled):
        """What it takes from other hosts, by slot name (`assembled.slot(name)`),
        once every host is prepared."""

    def bind(self, loaded):
        """What its unit needs written once the run `loaded` is loaded (its numbers,
        its regions' words)."""

    def need(self, size):
        """The Capacity a frame of `size` (W, H) needs; None when it needs none."""

    def view(self, loaded, camera, size):
        """What a frame of `camera` (16,) float32 at `size` needs, written into the
        loaded run `loaded` (its numbers, its regions' words)."""

    def commands(self, loaded):
        """The thread commands of its unit the loop sends after the views and before
        the next FRAME, in order: each a Command, or a name (a command that runs views
        and writes a times row); none. Asked after the earlier hosts' were served."""
        return []

    def served(self, loaded, command, code):
        """`command` of commands() came back with `code`."""

    def recover(self, loaded, code):
        """For a frame's `code` that is this host's: "retry" (its tables changed in
        the live run), "reload" (assemble again; it raised what it asks for in
        `loaded.options`), or None (not its code, or nothing to do)."""

    def picture(self, loaded):
        """The frame's picture as this host reads it back; asked only of a host whose
        `pictures` is true."""

    def controls(self):
        """What a person may change (a list of prism.core.control.Control); none."""
        return []

    def set(self, loaded, name, value):
        """The control `name` set to `value` (checked): None when applied in the live
        run `loaded`, "reload" when the loop must load again, else the refusal."""
        return f"no control {name!r}"


def hosted(host, name):
    """The contract's method `name` of `host`: its own, else Host's default."""
    method = getattr(host, name, None)
    return method if callable(method) else getattr(Host, name).__get__(host)


@dataclass(frozen=True)
class Implementation:
    """`device(host)` gives its made class (None: it has none, a unit alone);
    `host(session, scene, options)` holds what it needs on the host (the Host
    contract); `check(loaded)` its numbers; a unit's given slots are of its `writes`,
    its taken ones of its `reads`."""

    name: str
    fills: tuple
    reads: tuple
    writes: tuple
    device: Callable | None
    host: type
    check: Callable
    thread: object = None

    def __post_init__(self):
        for name in (*self.reads, *self.writes):
            SLOTS.get(name)
        if self.thread is not None:
            for slot in set(self.thread.gives) - set(self.writes):
                raise ValueError(
                    f"implementation {self.name!r}: its unit gives slot {slot!r}, "
                    f"which it does not write"
                )
            for slot in set(self.thread.takes) - set(self.reads):
                raise ValueError(
                    f"implementation {self.name!r}: its unit takes slot {slot!r}, "
                    f"which it does not read"
                )


IMPLEMENTATIONS = Registry("implementation")
