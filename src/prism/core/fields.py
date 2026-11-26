"""The fields several classes share: each defined once here (its format, shape, push=,
raw or tiles), its varying size a constant given at the make, the largest any of its
users needs; each user registers its need in its own module (need)."""

import inspect
from dataclasses import dataclass

import komorebi as km

from prism.core.headers import INCLUDE, constexpr

TP = constexpr(INCLUDE / "texel_pages" / "protocol.h")  # the texel pages' protocol


@dataclass(frozen=True)
class Common:
    """A common field: its format, its shape with the name of its varying size (a
    constant) in place of that size, its pusher, raw words or whole tiles."""

    format: object
    shape: tuple
    push: str | None
    raw: bool


COMMON = {
    "out_ring": Common(km.u32, ("OUT_RING_PAGES", 32, 32), "pack", False),
    "own_page_1": Common(km.u32, (1, 32, 32), None, False),
    "own_page_2": Common(km.u32, (1, 32, 32), None, False),
    "in_planes": Common(km.u32, ("IN_PLANES_PAGES", 32, 32), "mover_a", False),
    "frame_table": Common(km.u32, (1, "FRAME_TABLE_WORDS"), "mover_a", True),
    "texel_asks": Common(
        km.u32, (TP["kShadeAskPages"], TP["kShadeAskBytes"] // 4), "pack", True
    ),
    "texel_dones": Common(
        km.u32, (TP["kShadeDonePages"], TP["kShadeDoneBytes"] // 4), "mover_a", True
    ),
    "command_space": Common(km.u32, (1, "COMMAND_SPACE_WORDS"), None, True),
}
# the command space: the field a handler has for the length of its command. Each stage
# lays its parts from byte 0, in this order, each from a 64-byte line; the stages'
# layouts overlap, as one stage's handlers are in a command at a time. A part holds
# nothing a command of another stage must leave alone; each part's writer and reader:
SPACE = "command_space"
TABLE = "frame_table"  # the scene's materials table: its words a define as well
LAYOUTS = {
    # SHADE and LIGHT, each within its command: the slots (their keys cleared, the
    # white or zero texels written, at each command); the pack CPU's texel indices,
    # then its profile's counters; the page passes' hash
    "texel": ("texel_slots", "pack_work", "texel_work"),
    # COUNT's counters (zeroed, counted, written out in one command); COUNT's
    # histograms, read by HIST (only SUM, between them, of the same layer's raster
    # commands), and SETUP's prefixes within its command; no later frame reads them
    "raster": ("raster_counters", "kept_hist"),
    # SHOW's converted pages, profile page and buckets, within its command
    "show": ("show_scratch",),
    # WORK's memory (the movers' shared line, the kept state, the planes), within its
    # command: a pull's commands each fill it before they read it
    "frame": ("frame_memory",),
}
PARTS = {part: stage for stage, parts in LAYOUTS.items() for part in parts}
PART_ALIGN = 64
# each varying size's constant, the one object every class declaring the field holds
CONSTANTS = {
    size: km.constant(1)
    for common in COMMON.values()
    for size in common.shape
    if isinstance(size, str)
}
# a field's or a part's users: {user: need(held)}, its varying size (a part's bytes)
NEEDS = {name: {} for name in (*COMMON, *PARTS)}


def field(name):
    """A common field's annotation, its varying size the shared constant."""
    common = COMMON[name]
    shape = tuple(CONSTANTS.get(size, size) for size in common.shape)
    return km.L1[(common.format, *shape)]


def own(name):
    """A common field's km.own: its pusher, raw or tiles."""
    common = COMMON[name]
    return km.own(push=common.push, raw=common.raw)


def varying(name):
    """The name of a common field's varying size (None: it has none)."""
    return next((s for s in COMMON[name].shape if isinstance(s, str)), None)


def need(name, user, function):
    """`user` needs `function(held)` of field `name`'s varying size, or of part
    `name`'s bytes (`held`: the frame's capacity, None for the default's)."""
    if name not in PARTS and varying(name) is None:
        raise ValueError(f"common field {name} has no varying size to need")
    NEEDS[name][user] = function
    field_name = SPACE if name in PARTS else name
    CONSTANTS[varying(field_name)].default = size(field_name, None)  # no size given


def largest(name, held):
    """The largest need of field or part `name` at the capacity `held` (a part none
    needs: 0); ValueError for a field none needs."""
    needs = NEEDS[name]
    if not needs and name not in PARTS:
        raise ValueError(f"common field {name}: no user has said what it needs")
    return max((function(held) for function in needs.values()), default=0)


def parts(held):
    """The command space's parts at the capacity `held`, each stage's from byte 0:
    {part: (byte, bytes)}."""
    places = {}
    for layout in LAYOUTS.values():
        at = 0
        for part in layout:
            at = -(-at // PART_ALIGN) * PART_ALIGN
            places[part] = (at, largest(part, held))
            at += places[part][1]
    return places


def space_bytes(held):
    """The command space's bytes at the capacity `held`: the largest stage's parts end
    to end, on 16 bytes."""
    ends = [at + bytes_ for at, bytes_ in parts(held).values()]
    return -(-max(ends) // 16) * 16


def size(name, held):
    """Field `name`'s varying size at the capacity `held`: the largest its users
    need; the command space's words."""
    if name != SPACE:
        return largest(name, held)
    return space_bytes(held) // 4


def defines(held):
    """The kernels' defines of the command space's parts at the capacity `held`: each
    part's first byte (PRISM_SPACE_<PART>_AT)."""
    return {
        f"PRISM_SPACE_{part.upper()}_AT": str(at)
        for part, (at, _) in parts(held).items()
    }


def table_defines(cls, held):
    """The kernels' define of the table field's words at the capacity `held`
    (PRISM_FRAME_TABLE_WORDS) for class `cls` when it declares the field."""
    if TABLE not in km_fields(cls):
        return {}
    return {f"PRISM_{varying(TABLE)}": str(size(TABLE, held))}


def given(cls, held):
    """The make's constants of the common fields class `cls` declares: each varying
    size at the capacity `held`."""
    declared = [name for name in km_fields(cls) if name in COMMON]
    return {
        varying(name): size(name, held)
        for name in declared
        if varying(name) is not None
    }


def km_fields(cls):
    """The names a class and its parents annotate."""
    names = []
    for klass in reversed(cls.__mro__):
        names += [n for n in inspect.get_annotations(klass) if n not in names]
    return names
