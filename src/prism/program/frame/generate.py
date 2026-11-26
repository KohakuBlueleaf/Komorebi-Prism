"""The handler `work`'s program composed from a pipeline's tile thread and the kinds of
thread beside it: the steps' words, the planes, the kept state and the rings assigned,
the list stream of each view, the output pairs; the generated program's text and file.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from prism.core import fields
from prism.core.headers import INCLUDE, defined
from prism.core.thread.module import ListPass
from prism_common.formats import format_of

HERE = Path(__file__).resolve().parent
KERNELS = HERE / "kernels"
SOURCE = HERE.parents[1]  # a step's or a kind's header is named from here
PROGRAM = "work.hpp"
TF = defined(INCLUDE / "thread" / "frame.h")
TR = defined(INCLUDE / "thread" / "record.h")
TA = defined(INCLUDE / "thread" / "answer.h")
FRAME = defined(KERNELS / "frame.h")
TF_STEP_AT = TF["TF_LAYER_AT"] + TR["TR_LAYERS"] * TF["TF_LAYER_WORDS"]
PULLS = {TA["TP_COUNT"]: "count", TA["TP_PLACE"]: "place"}
ALIGN = FRAME["FM_ALIGN"]
WORD = 4
MEMORY, OWNER = "frame_memory", "frame"  # the command space's part, its user
# the handler's own rings: name, (pages, page bytes, pushing CPU) by the composition
FIXED = ("page", "jobs", "jobs_b", "list_a", "list_b", "asks_a", "asks_b")


def camel(name):
    """`snake_name` as the class header spells a field: SnakeName."""
    return "".join(part[:1].upper() + part[1:] for part in name.split("_"))


def identifier(name):
    """A plane's or kept state's name as a C name: each character that is no letter,
    digit or underscore an underscore."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)


def aligned(value, align=ALIGN):
    """`value` rounded up to a multiple of `align`."""
    return -(-value // align) * align


def sized(value, held):
    """A kept size: an int, or a function of the capacity `held`."""
    return int(value(held) if callable(value) else value)


@dataclass(frozen=True)
class Composition:
    """A tile thread and the kinds beside it, composed for the frame's layers: the
    steps' words {define: word}, the planes {name: (byte, bytes)}, the kept state
    {(owner, name): (byte, bytes)}, each step's passes (layer indices), each view's list
    stream, the outputs (step, Output), the rings {field: (pages, page bytes, pusher)},
    the lists' geometry (records a page, a page's bytes, pages a block), the handler's
    memory bytes."""

    thread: object
    kinds: tuple
    layers: tuple
    words: dict
    planes: dict
    kept: dict
    passes: dict
    streams: dict
    outputs: tuple
    rings: dict
    geometry: tuple
    planes_at: int
    memory_bytes: int

    def held_codes(self):
        """The codes the program holds, a bit a code: the resident one and every
        step's variants."""
        codes = {0} | {code for step in self.thread.steps for code in step.codes}
        return sum(1 << code for code in codes if 0 <= code < 32)

    def common(self):
        """The common fields (prism.core.fields) the steps and kinds name, in order."""
        names = [fields.SPACE]
        for owner in (*self.thread.steps, *self.kinds):
            names += [n for n in owner.fields if n not in names]
        return tuple(names)


def plane_places(planes):
    """{name: (byte, bytes)} of the working planes, each on ALIGN bytes."""
    places, at = {}, 0
    for plane in planes:
        bytes_ = format_of(plane.format).tile_bytes * plane.tiles
        places[plane.name] = (at, bytes_)
        at = aligned(at + bytes_)
    return places, at


def kept_places(owners, held, places=None):
    """{(owner, name): (byte, bytes)} of the owners' kept state end to end from byte 0
    (added to `places`), and the bytes they take."""
    places = {} if places is None else places
    at = 0
    for owner in owners:
        for name, value in owner.keeps.items():
            bytes_ = sized(value, held)
            places[owner.name, name] = (at, bytes_)
            at = aligned(at + bytes_)
    return places, at


def memory_of(thread, kinds, held):
    """The handler's memory past its shared line: the tile thread's part (the steps'
    kept state, then the planes) and each kind's kept state over the same bytes. The
    kept state {(owner, name): (byte, bytes)}, the planes' first byte, the bytes of
    the largest part."""
    kept, steps_bytes = kept_places(thread.steps, held)
    _, planes_bytes = plane_places(thread.planes)
    largest = steps_bytes + planes_bytes
    for kind in kinds:
        largest = max(largest, kept_places((kind,), held, kept)[1])
    return kept, steps_bytes, largest


def pass_layers(steps, layers):
    """{step: (layer indices a pass)} of every step's list passes for the frame's
    layers (their names); refused for an index that is no layer of a record."""
    out = {}
    for step in steps:
        out[step.name] = []
        for one in step.passes:
            indices = tuple(int(i) for i in one.layers(layers))
            for index in indices:
                if not 0 <= index < min(len(layers), TR["TR_LAYERS"]):
                    raise ValueError(
                        f"frame program: step {step.name!r} passes layer {index}, "
                        f"not one of the frame's {len(layers)} ({TR['TR_LAYERS']} at "
                        f"most a record)"
                    )
            out[step.name].append(indices)
        out[step.name] = tuple(out[step.name])
    return out


def lists_geometry(steps):
    """(records a page, a page's bytes, pages a block) of the lists, one for every
    list pass (module.py ListPass; its defaults when no step passes a list)."""
    shapes = {
        (one.record_bytes, one.page_records, one.block_records)
        for step in steps
        for one in step.passes
    }
    if not shapes:
        plain = ListPass(None)
        shapes = {(plain.record_bytes, plain.page_records, plain.block_records)}
    record_bytes, page_records, block_records = next(iter(shapes))
    if len(shapes) > 1 or page_records <= 0 or block_records % page_records:
        raise ValueError(
            f"frame program: list passes of (record bytes, records a page, records a "
            f"block) {sorted(shapes)}; the passes share one, a block whole pages"
        )
    return page_records, record_bytes * page_records, block_records // page_records


def kind_field(kinds, kind, name):
    """The field of `kind`'s ring `name`: kind_<name>, one for every kind declaring
    the ring with the same shape and pusher, when another does; else <kind>_<name>."""
    shape = kind.buffers[name]
    alike = [other for other in kinds if other.buffers.get(name) == shape]
    return f"kind_{name}" if len(alike) > 1 else f"{kind.name}_{name}"


def rings_of(thread, kinds, outputs, geometry):
    """{field: (pages, page bytes, pusher)} of the handler's rings, each output's
    pair, each step's own rings, each kind's (one field for a ring kinds share)."""
    _, page_bytes, block_pages = geometry
    rings = {
        "frame_page": (2, TF["TF_WORDS"] * WORD, "mover_a"),
        "frame_jobs": (FRAME["FD_PAGES"], FRAME["FD_WORDS"] * WORD, "mover_a"),
        "frame_jobs_b": (FRAME["FD_PAGES"], FRAME["FD_WORDS"] * WORD, "mover_a"),
        "frame_list_a": (
            FRAME["FL_HALF_BLOCKS"] * block_pages,
            page_bytes,
            "mover_a",
        ),
        "frame_list_b": (
            FRAME["FL_HALF_BLOCKS"] * block_pages,
            page_bytes,
            "mover_b",
        ),
        "frame_asks_a": (FRAME["FA_PAGES"], FRAME["FA_BYTES"], "pack"),
        "frame_asks_b": (FRAME["FA_PAGES"], FRAME["FA_BYTES"], "pack"),
        "frame_dones_a": (FRAME["FN_PAGES"], FRAME["FN_BYTES"], "mover_a"),
        "frame_dones_b": (FRAME["FN_PAGES"], FRAME["FN_BYTES"], "mover_b"),
    }
    for _, output in outputs:
        if output.block_bytes <= FRAME["FO_HEADER_BYTES"] or output.block_bytes % 16:
            raise ValueError(
                f"frame program: output {output.name!r} of {output.block_bytes} bytes "
                f"a block; its header takes {FRAME['FO_HEADER_BYTES']}, 16s"
            )
        for half in ("a", "b"):
            rings[f"frame_out_{output.name}_{half}"] = (
                output.blocks,
                output.block_bytes,
                "pack",
            )
    shared = set()
    for owner in (*thread.steps, *kinds):
        for name, (pages, page_bytes, pusher) in owner.buffers.items():
            field = f"{owner.name}_{name}"
            if owner in kinds:
                field = kind_field(kinds, owner, name)
            if field in shared:
                continue
            if field in rings:
                raise ValueError(f"frame program: ring {field!r} declared twice")
            rings[field] = (int(pages), int(page_bytes), pusher)
            if owner in kinds and field == f"kind_{name}":
                shared.add(field)
    return rings


def compose(thread, kinds, layers, held=None):
    """The Composition of the tile thread `thread` (module.py TileThread) and `kinds`
    (module.py Kind) for the frame's `layers` (names, in order) at the capacity `held`;
    refused with the names for a thread, kind, word, plane or ring that does not fit."""
    thread.check()
    kinds = tuple(kinds)
    pulls = [kind.pull for kind in kinds]
    for kind in kinds:
        if kind.pull not in PULLS or pulls.count(kind.pull) > 1:
            raise ValueError(
                f"frame program: kind {kind.name!r} of pull {kind.pull}; one kind a "
                f"pull of {sorted(PULLS)}"
            )
    names = [owner.name for owner in (*thread.steps, *kinds)]
    for name in names:
        if names.count(name) > 1:
            raise ValueError(f"frame program: {name!r} is a step's and a kind's name")
    outputs = tuple((step, out) for step in thread.steps for out in step.outputs)
    out_names = [out.name for _, out in outputs]
    if len(set(out_names)) != len(out_names):
        raise ValueError(f"frame program: an output named twice ({out_names})")
    words = thread.words(TF_STEP_AT, TF["TF_WORDS"])
    planes, _ = plane_places(thread.planes)
    kept, steps_bytes, largest = memory_of(thread, kinds, held)
    passes = pass_layers(thread.steps, tuple(layers))
    streams = {
        TF["TV_COLOUR"]: sum((sum(passes[s.name], ()) for s in thread.colour()), ()),
        TF["TV_DEPTH"]: sum((sum(passes[s.name], ()) for s in thread.depth()), ()),
    }
    geometry = lists_geometry(thread.steps)
    memory = aligned(FRAME["FM_SHARED_BYTES"] + largest)
    rings = rings_of(thread, kinds, outputs, geometry)
    fields.need(MEMORY, OWNER, lambda held, bytes_=memory: bytes_)
    return Composition(
        thread,
        kinds,
        tuple(layers),
        words,
        planes,
        kept,
        passes,
        streams,
        outputs,
        rings,
        geometry,
        aligned(FRAME["FM_SHARED_BYTES"] + steps_bytes),
        memory,
    )


def kept_at(composition):
    """The kept state's first byte in the handler's memory."""
    return FRAME["FM_SHARED_BYTES"]


def planes_at(composition):
    """The working planes' first byte in the handler's memory."""
    return composition.planes_at


def array(name, values):
    """A constexpr array of uint32_t (one 0 when empty) and its count."""
    body = ", ".join(str(v) for v in values) or "0"
    return [
        f"    constexpr uint32_t {name}[] = {{{body}}};",
        f"    constexpr uint32_t {name}Count = {len(values)};",
    ]


def local(lines):
    """Constant arrays as statics of a function's body."""
    return ["    " + line.replace("constexpr", "static constexpr", 1) for line in lines]


def constants_text(composition):
    """The program's constants: the lists' geometry, the memory's places, the codes
    held, the outputs' pairs, the kept state's places, each step's passes, the planes.
    """
    pairs = [
        f"{{kFieldFrameOut{camel(out.name)}A, kFieldFrameOut{camel(out.name)}B}}"
        for _, out in composition.outputs
    ] or ["{0, 0}"]
    page_records, page_bytes, block_pages = composition.geometry
    lines = [
        f"constexpr uint32_t kFrameSlotsPerPage = {page_records};",
        f"constexpr uint32_t kFrameListPageBytes = {page_bytes};",
        f"constexpr uint32_t kFrameBlockPages = {block_pages};",
        f"constexpr uint32_t kFrameKeptAt = {kept_at(composition)};",
        f"constexpr uint32_t kFramePlanesAt = {planes_at(composition)};",
        f"constexpr uint32_t kFrameMemoryBytes = {composition.memory_bytes};",
        f"constexpr uint32_t kFrameHeldCodes = {composition.held_codes()}u;",
        f"constexpr uint32_t kFrameOutputs = {len(composition.outputs)};",
        f"constexpr km::BufferPair kFrameOutPairs[] = {{{', '.join(pairs)}}};",
        "",
        "namespace prism_frame {",
    ]
    for (owner, name), (at, bytes_) in composition.kept.items():
        stem = f"kKept{camel(owner)}{camel(identifier(name))}"
        lines += [
            f"    constexpr uint32_t {stem} = {at};",
            f"    constexpr uint32_t {stem}Bytes = {bytes_};",
        ]
    for index, (_, out) in enumerate(composition.outputs):
        lines += [f"    constexpr uint32_t kFrameOut{camel(out.name)} = {index};"]
    for step, passes in composition.passes.items():
        for index, layers in enumerate(passes):
            lines += array(f"k{camel(step)}Pass{index}Layers", layers)
    lines += ["", "    // The working planes' L1 addresses.", "    struct Planes {"]
    lines += [f"        uint32_t {identifier(name)};" for name in composition.planes]
    lines += ["    };", "", "    inline Planes planes_of(uint32_t base) {"]
    places = [f"base + {at}" for at, _ in composition.planes.values()]
    lines += [
        f"        return {{{', '.join(places)}}};" if places else "        return {};"
    ]
    lines += ["    }", "}  // namespace prism_frame"]
    return lines


def step_calls(steps, indent):
    """Each step's compute call, by the tile pull's code its variant's; false ends the
    tile thread."""
    pad = " " * indent
    lines = []
    for step in steps:
        call = "(ctx, tile, planes)"
        if not step.codes:
            lines += [f"{pad}if (!{step.name}_compute{call}) {{"]
            lines += [f"{pad}    return false;", f"{pad}}}"]
            continue
        lines.append(f"{pad}switch (TA_CODE(tile.word)) {{")
        for code, function in sorted(step.codes.items()):
            lines += [
                f"{pad}    case {code}:",
                f"{pad}        if (!{function}{call}) {{",
            ]
            lines += [f"{pad}            return false;", f"{pad}        }}"]
            lines.append(f"{pad}        break;")
        lines += [
            f"{pad}    default:",
            f"{pad}        if (!{step.name}_compute{call}) {{",
        ]
        lines += [f"{pad}            return false;", f"{pad}        }}"]
        lines += [f"{pad}        break;", f"{pad}}}"]
    return lines


def buffers_text(composition):
    """A struct a kind of its rings' field indices, named as the kind declares them."""
    lines = []
    for kind in composition.kinds:
        lines += [f"    struct {camel(kind.name)}Buffers {{"]
        lines += [
            f"        static constexpr uint32_t {identifier(name)} = "
            f"kField{camel(identifier(kind_field(composition.kinds, kind, name)))};"
            for name in kind.buffers
        ]
        lines += ["    };", ""]
    return lines


def kind_call(kind, call, back):
    """A kind's call on its KindContext; on the compute CPUs the pack's turns copied
    back."""
    lines = [
        "            {",
        f"                KindContext<{camel(kind.name)}Buffers> one{{ctx}};",
        f"                const bool ok = {kind.name}_{call};",
    ]
    if back:
        lines += [
            "                ctx.ask_turn = one.ask_turn;",
            "                for (uint32_t i = 0; i <= kFrameOutputs; i++) {",
            "                    ctx.out_turn[i] = one.out_turn[i];",
            "                }",
            "                ctx.out_blocks[0] = one.out_blocks[0];",
            "                ctx.out_blocks[1] = one.out_blocks[1];",
        ]
    return lines + ["                return ok;", "            }"]


def compute_text(composition):
    """The compute CPUs' parts: the tile thread by the view, a kind's range, its end."""
    thread = composition.thread
    lines = [
        "    bool tile_compute(ComputeContext& ctx, const Tile& tile) {",
        "        Planes planes = planes_of(ctx.planes());",
        "        if (view_kind(ctx.page) == TV_DEPTH) {",
        *step_calls(thread.depth(), 12),
        "        } else {",
        *step_calls(thread.colour(), 12),
        "        }",
        "        static_cast<void>(planes);",
        "        static_cast<void>(tile);",
        "        return true;",
        "    }",
        "",
        "    bool kind_compute(ComputeContext& ctx, uint32_t kind, const Range& range) {",
        "        switch (kind) {",
    ]
    for kind in composition.kinds:
        lines += [f"            case {kind.pull}:"]
        lines += kind_call(kind, "compute(one, range)", True)
    lines += [
        "            default:",
        "                static_cast<void>(ctx);",
        "                static_cast<void>(range);",
        "                return true;",
        "        }",
        "    }",
        "",
        "    bool kind_end_compute(ComputeContext& ctx, uint32_t kind) {",
        "        switch (kind) {",
    ]
    for kind in composition.kinds:
        lines += [f"            case {kind.pull}:"]
        lines += kind_call(kind, "end(one)", True)
    lines += ["            default:", "                static_cast<void>(ctx);"]
    lines += ["                return true;", "        }", "    }"]
    return lines


def begin_text(composition):
    """The steps' begin, once a command on mover A before its first thread."""
    lines = ["    bool steps_begin(MoverContext& ctx) {"]
    for step in composition.thread.steps:
        if step.begin:
            lines += [f"        if (!{step.name}_begin(ctx)) {{"]
            lines += ["            return false;", "        }"]
    return lines + [
        "        static_cast<void>(ctx);",
        "        return true;",
        "    }",
        "",
    ]


def mover_text(composition):
    """The movers' parts: the steps' begin, each view's list stream, a kind's range and
    its end, the output halves drained (each through its step's convert)."""
    colour = composition.streams[TF["TV_COLOUR"]]
    depth = composition.streams[TF["TV_DEPTH"]]
    lines = [
        *begin_text(composition),
        "    const uint32_t* stream_layers(uint32_t view, uint32_t& count) {",
        *local(array("kColour", colour)),
        *local(array("kDepth", depth)),
        "        count = view == TV_DEPTH ? kDepthCount : kColourCount;",
        "        return view == TV_DEPTH ? kDepth : kColour;",
        "    }",
        "",
        "    bool kind_movers(MoverContext& ctx, uint32_t kind, const Range& range) {",
        "        switch (kind) {",
    ]
    for kind in composition.kinds:
        lines += [f"            case {kind.pull}:"]
        lines += kind_call(kind, "movers(one, range)", False)
    lines += [
        "            default:",
        "                static_cast<void>(range);",
        "                return ctx.gave_up(km::kGaveBadItem, FW_BAD);",
        "        }",
        "    }",
        "",
        "    bool kind_end_movers(MoverContext& ctx, uint32_t kind) {",
        "        switch (kind) {",
    ]
    for kind in composition.kinds:
        lines += [f"            case {kind.pull}:"]
        lines += kind_call(kind, "end(one)", False)
    lines += [
        "            default:",
        "                static_cast<void>(ctx);",
        "                return true;",
        "        }",
        "    }",
        "",
        "    int serve_outputs(MoverContext& ctx, MoverState& state) {",
        "        int moved = 0;",
    ]
    for index, (_, out) in enumerate(composition.outputs):
        convert = out.convert or "as_it_is"
        lines += [
            "        {",
            "            const int one = drain_output(",
            f"                ctx, state, kFrameOutPairs[{index}].half(km::kMover),",
            "                [](MoverContext& c, uint32_t payload, uint32_t bytes) {",
            f"                    return {convert}(c, payload, bytes);",
            "                }",
            "            );",
            "            if (one < 0) {",
            "                return -1;",
            "            }",
            "            moved += one;",
            "        }",
        ]
    lines += [
        "        static_cast<void>(ctx);",
        "        static_cast<void>(state);",
        "        return moved;",
        "    }",
    ]
    return lines


def headers_of(composition):
    """Every step's and kind's header, once, in order, as an absolute path."""
    owners = (*composition.thread.steps, *composition.kinds)
    return list(dict.fromkeys(str(SOURCE / owner.header) for owner in owners))


def text(composition):
    """The generated program: its constants, the loop's kernels, the steps' and kinds'
    headers, then the parts they give, on the movers and on the compute CPUs."""
    lines = [
        "// Generated by prism.program.frame.generate: the handler work's program.",
        "#pragma once",
        "",
        "#include <stdint.h>",
        "",
        '#include "komorebi/device/movement/km_movement.hpp"',
        f'#include "{KERNELS / "frame.h"}"',
        "",
        *constants_text(composition),
        "",
        "#if defined(COMPILE_FOR_TRISC)",
        f'#include "{KERNELS / "compute.hpp"}"',
        "#else",
        f'#include "{KERNELS / "movement.hpp"}"',
        "#endif",
        "",
        *(f'#include "{header}"' for header in headers_of(composition)),
        "",
        "namespace prism_frame {",
        *buffers_text(composition),
        "#if defined(COMPILE_FOR_TRISC)",
        *compute_text(composition),
        "#else",
        *mover_text(composition),
        "#endif",
        "}  // namespace prism_frame",
    ]
    return "\n".join(lines) + "\n"


def write(composition, folder):
    """The generated program written under `folder`, in a folder named by its text's
    digest: its path."""
    body = text(composition)
    digest = hashlib.sha256(body.encode()).hexdigest()[:16]
    target = Path(folder) / f"work-{digest}"
    target.mkdir(parents=True, exist_ok=True)
    path = target / PROGRAM
    if not path.exists() or path.read_text() != body:
        path.write_text(body)
    return path
