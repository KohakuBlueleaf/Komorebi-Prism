"""What an implementation gives the frame's thread: its C, the functions the director calls
and what it asks the core to assign (regions, numbers, columns, times, results)."""

from collections.abc import Callable
from dataclasses import dataclass, field

from prism_common.slots import SLOTS

KINDS = ("numbers", "columns", "times", "results", "serves", "takes")
ROLES = ("setup", "layer", "frame")


@dataclass(frozen=True)
class Region:
    """A thread region a unit asks for: `bytes` an int or a function of the host (with
    `by_area`, of the host and the frame's areas: a view's layers, every view);
    `contents` None or a function of the host giving its first words; `own`: a region of
    its own, else a part of the director's numbers region."""

    bytes: int | Callable
    contents: Callable | None = None
    own: bool = True
    by_area: bool = False

    def size(self, host, areas):
        """Its bytes for `host` and the frame's `areas`."""
        if not callable(self.bytes):
            return int(self.bytes)
        return int(self.bytes(host, areas) if self.by_area else self.bytes(host))


@dataclass(frozen=True)
class Unit:
    """An implementation's part of the thread: `sources` and `includes` relative to the
    implementation's folder; which of its C functions exist (`<name>_unit_setup`,
    `_layer`, `_frame`; `serves`: thread commands, each `<name>_unit_<command>`;
    `gives`: {slot: function}, each `<name>_unit_<function>(frame)` producing the slot
    once; `takes`: the slots it has produced by the unit that gives them, or reads from
    the columns its writer shares; `shares`: {slot: its own columns that carry it});
    what it asks for (a layer unit's times and results once a layer); `defines`: a
    function of the host giving its build-time {name: value}."""

    sources: tuple = ()
    includes: tuple = ()
    setup: bool = False
    layer: bool = False
    frame: bool = False
    serves: tuple = ()
    gives: dict = field(default_factory=dict)
    takes: tuple = ()
    shares: dict = field(default_factory=dict)
    regions: dict = field(default_factory=dict)
    numbers: tuple = ()
    columns: tuple = ()
    times: tuple = ()
    results: tuple = ()
    defines: Callable | None = None

    def __post_init__(self):
        for kind in KINDS:
            names = getattr(self, kind)
            twice = sorted({name for name in names if names.count(name) > 1})
            if twice:
                raise ValueError(f"unit: {kind} {', '.join(twice)} named twice")
        for name in set(self.serves) & set(ROLES):
            raise ValueError(f"unit: command {name!r} is the name of a role")
        for slot in (*self.gives, *self.takes):
            SLOTS.get(slot)
        for slot, function in self.gives.items():
            if not function.isidentifier() or function in (*ROLES, *self.serves):
                raise ValueError(
                    f"unit: slot {slot!r} given by {function!r}, not a function name "
                    f"of its own"
                )
        for slot, names in self.shares.items():
            SLOTS.get(slot)
            unknown = sorted(set(names) - set(self.columns))
            if unknown:
                raise ValueError(
                    f"unit: slot {slot!r} shares {', '.join(unknown)}, not columns "
                    f"of its own"
                )
        for slot in (set(self.gives) | set(self.shares)) & set(self.takes):
            raise ValueError(f"unit: slot {slot!r} both given and taken")
        for name, region in self.regions.items():
            if not isinstance(region, Region):
                raise TypeError(f"unit: region {name!r} is not a Region")

    def functions(self, prefix):
        """{role or command: C function name} of the functions it gives, for the
        function prefix `prefix` of its implementation."""
        roles = [role for role in ROLES if getattr(self, role)] + list(self.serves)
        return {role: f"{prefix}_unit_{role}" for role in roles}

    def given(self, prefix):
        """{slot: C function name} of the slots it gives, for the function prefix
        `prefix` of its implementation."""
        return {slot: f"{prefix}_unit_{name}" for slot, name in self.gives.items()}

    def build_defines(self, host):
        """The -D definitions its C needs for `host`: {name: text}."""
        return {} if self.defines is None else dict(self.defines(host))
