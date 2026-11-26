"""The stages' profile pages as named counters: for each command, each CPU's busy steps,
its waits by what it waited for, its total and its counts, a core a row; the words of
each page as its kernels write them."""

from dataclasses import dataclass, field

import numpy as np

from prism.stages.direct.light.model.numbers import LH
from prism.stages.material.texture.model.numbers import SH
from prism.stages.post.show.model.table import SHOW
from prism.stages.raster.model.numbers import K, S


@dataclass(frozen=True)
class Cpu:
    """A CPU's words in a profile page: busy steps, waits and counts {name: word}, the
    total's word."""

    name: str
    busy: dict = field(default_factory=dict)
    wait: dict = field(default_factory=dict)
    total: int = 0
    counts: dict = field(default_factory=dict)


def named(header, prefix, names):
    """{name: word} of `names` from a header's constants `<prefix><Name>` (snake case
    to camel case)."""
    return {
        name: header[prefix + "".join(p.title() for p in name.split("_"))]
        for name in names
    }


# the passes' page (setup.h kSProf*): a handler's words from byte 128 x (handler -
# kHandlerCount); the reader's, the pack thread's and the writer's words in them
PASS_STRIDE = 32
R, P, W = S["kSProfReader"], S["kSProfPack"], S["kSProfWriter"]
PASS_READER = Cpu(
    "reader", {"read": R + 1}, {"reserve": R + 0}, R + 2, {"bytes": R + 3}
)
PASS_PACK = Cpu(
    "pack",
    {"vector": P + 1, "scalar": P + 2},
    {"mail": P + 0, "out": P + 7},
    P + 3,
    {"kept": P + 4, "clipped": P + 5, "entries": P + 6},
)
PASS_WRITER = Cpu(
    "writer", {"write": W + 1}, {"pack": W + 0}, W + 2, {"bytes": W + 3, "pages": W + 5}
)
WRITER_TOTAL = Cpu("writer", total=W + 2)  # HIST, PLACE: the writer's total alone
PASS_HANDLER = {
    "count": S["kHandlerCount"],
    "setup": S["kHandlerSetup"],
    "hist": S["kHandlerHist"],
    "place": S["kHandlerPlace"],
}
PASS_CPUS = {
    "count": (PASS_READER, PASS_PACK, PASS_WRITER),
    "setup": (PASS_READER, PASS_PACK, PASS_WRITER),
    "hist": (WRITER_TOTAL,),
    "place": (WRITER_TOTAL,),
}

# FILL's page (raster.h): the pack thread's counters from word 0 in the order of
# fill/walk.hpp's profile item, its landing wait at kProfLanding, the reader's words
# (wait, read, total, pages) at kProfReader, the writer's (wait, write, total, items)
# at kProfWriter
FILL_PACK_WORDS = ("wait_in", "init", "triangle_setup", "rows", "drain", "out")
FILL_PACK_WORDS += ("wait_out", "tiles", "triangles", "row_count", "total")
F = {name: word for word, name in enumerate(FILL_PACK_WORDS)}
FR, FW = K["kProfReader"], K["kProfWriter"]
FILL_CPUS = (
    Cpu(
        "pack",
        {n: F[n] for n in ("init", "triangle_setup", "rows", "drain", "out")},
        {"lists": F["wait_in"], "out": F["wait_out"], "landing": K["kProfLanding"]},
        F["total"],
        {"tiles": F["tiles"], "triangles": F["triangles"], "rows": F["row_count"]},
    ),
    Cpu("reader", {"read": FR + 1}, {"room": FR + 0}, FR + 2, {"pages": FR + 3}),
    Cpu("writer", {"write": FW + 1}, {"planes": FW + 0}, FW + 2, {"items": FW + 3}),
)

# SHADE's page (shade.h kShadeProf*): the pack thread's
SHADE_STEPS = ("copy_in", "divide", "record", "scan", "gather", "out")
SHADE_COUNTS = ("tiles", "records", "rows", "passes", "pages", "texels")
SHADE_COUNTS += ("item_pages", "item_passes")
SHADE_CPUS = (
    Cpu(
        "pack",
        named(SH, "kShadeProf", SHADE_STEPS),
        {"in": SH["kShadeProfWaitIn"], "pages": SH["kShadeProfWaitPages"]},
        SH["kShadeProfTotal"],
        named(SH, "kShadeProf", SHADE_COUNTS),
    ),
)

# LIGHT's page (light.h kLightProf*): the pack thread's
LIGHT_STEPS = ("copy_in", "keys", "scan", "gather", "shadow", "specular", "lamps")
LIGHT_STEPS += ("math", "out", "field_keys", "field_scan", "field_gather")
LIGHT_STEPS += ("field_blend",)
LIGHT_COUNTS = ("tiles", "rows", "pages", "passes", "glass_quarters", "field_pages")
LIGHT_COUNTS += ("field_passes", "field_item_pages")
LIGHT_CPUS = (
    Cpu(
        "pack",
        named(LH, "kLightProf", LIGHT_STEPS),
        {
            "in": LH["kLightProfWait"],
            "pages": LH["kLightProfWaitPages"],
            "field_pages": LH["kLightProfFieldWait"],
        },
        LH["kLightProfTotal"],
        named(LH, "kLightProf", LIGHT_COUNTS),
    ),
)

# SHOW's page (show.h kShowProf*): the writer's
SHOW_CPUS = (
    Cpu(
        "writer",
        named(SHOW, "kShowProf", ("convert", "write")),
        {"planes": SHOW["kShowProfWait"]},
        SHOW["kShowProfTotal"],
        named(SHOW, "kShowProf", ("items", "rows")),
    ),
)


def words_of(session, tensor):
    """A profile tensor's pages as int64 words, a core a row."""
    raw = session.read(tensor)[0]
    return raw.view(np.uint32).reshape(raw.shape[0], -1).astype(np.int64)


def decoded(words, cpus, base=0):
    """Each CPU of `cpus` from profile words [cores, words] (its words from `base`):
    {cpu: {"busy": {step: cycles}, "wait": {kind: cycles}, "total": cycles,
    "counts": {name: n}}}, each value an array a core."""
    out = {}
    for cpu in cpus:
        out[cpu.name] = {
            "busy": columns(words, cpu.busy, base),
            "wait": columns(words, cpu.wait, base),
            "total": words[:, base + cpu.total].copy(),
            "counts": columns(words, cpu.counts, base),
        }
    return out


def columns(words, at, base):
    """{name: words[:, base + word]} of `at` ({name: word})."""
    return {name: words[:, base + word].copy() for name, word in at.items()}


def pass_profile(words, name):
    """The raster pass `name`'s CPUs from its layer's passes' page words."""
    base = PASS_STRIDE * (PASS_HANDLER[name] - S["kHandlerCount"])
    return decoded(words, PASS_CPUS[name], base)
