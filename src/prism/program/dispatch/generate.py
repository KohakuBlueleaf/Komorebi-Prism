"""The pulls' form of the frame thread's generated part: pipeline.h with the director's
layout, the dispatcher's names (DP_*), the builders of the work and sums commands and the
steps' words; pipeline.c with the setups, the steps' frame words and each view as
pulls."""

import hashlib
from pathlib import Path

from prism.core.resources import function_prefix, macro_prefix
from prism.program.director import generate as director

NAME = "dp"  # the dispatcher's owner name in the thread's layout
PREFIX = "dispatch_"  # its numbers', columns', regions', times' and results' names
HEADER, SOURCE = director.HEADER, director.SOURCE
FRAME_WORDS = "dr_frame_t* frame, const dr_view_t* view, uint32_t* page"


def short(name):
    """A dispatcher name without its prefix, upper-cased: `dispatch_near` as NEAR."""
    return name.removeprefix(PREFIX).upper()


def aliases(layout):
    """DP_N_*, DP_L_*, DP_T_*, DP_R_* and DP_REGION_* (with _AT, _BYTES) for the
    dispatcher's places and regions, each the layout's macro."""
    owner = macro_prefix(NAME)
    lines = []
    kinds = (
        (layout.numbers, "N"),
        (layout.columns, "L"),
        (layout.times, "T"),
        (layout.results, "R"),
    )
    for table, letter in kinds:
        for name, place in table.items():
            if place.owner == NAME:
                lines.append(
                    f"#define DP_{letter}_{short(name)} {owner}_{letter}_{name.upper()}"
                )
    for name, (region_owner, *_) in layout.regions.items():
        if region_owner != NAME:
            continue
        for end in ("", "_AT", "_BYTES"):
            lines.append(
                f"#define DP_REGION_{short(name)}{end} "
                f"{owner}_REGION_{name.upper()}{end}"
            )
    return lines


def header_text(layout, program_header, program_prefix, builders, calls, words):
    """The director's pipeline.h, the dispatcher's names, DP_BUILD_WORK and
    DP_BUILD_SUMS (`calls`: {"work", "sums": the C builder}), DP_STEP_WORDS and each
    step's word place (`words`: {define: word})."""
    text = director.header_text(layout, program_header, program_prefix, builders)
    lines = [
        "",
        "/* The dispatcher's places and regions, the builders of its commands and the",
        " * steps' words of the frame's page. */",
        *aliases(layout),
        f"#define DP_BUILD_WORK {calls['work']}",
        f"#define DP_BUILD_SUMS {calls['sums']}",
        f"#define DP_STEP_WORDS {len(words)}u",
        *(f"#define {define} {word}u" for define, word in words.items()),
    ]
    return text + "\n".join(lines) + "\n"


def calls(functions, arguments):
    """C lines calling each of `functions` in order with `arguments`, each guarded by
    its condition ({C function: condition or None}); the first code not 0 ends them."""
    out = []
    for function, condition in functions.items():
        guard = f"code == 0 && {condition}" if condition else "code == 0"
        out.append(
            f"    if ({guard}) {{\n        code = {function}({arguments});\n    }}"
        )
    return out


def frame_words_text(steps):
    """dp_frame_words: each step's `<step>_frame_words` in the steps' order (`steps`:
    (C function, depth)); a step without depth is not called for a DEPTH view."""
    functions = {f: None if depth else "!depth" for f, depth in steps}
    return "\n".join(
        [
            *(f"uint32_t {f}({FRAME_WORDS});" for f in functions),
            f"uint32_t dp_frame_words({FRAME_WORDS}) {{",
            "    uint32_t code = 0;",
            "    const uint32_t depth = view->kind == DR_VIEW_DEPTH;",
            *calls(functions, "frame, view, page"),
            "    (void)frame;",
            "    (void)page;",
            "    (void)depth;",
            "    return code;",
            "}",
        ]
    )


def setup_text(units):
    """dr_units_setup: the dispatcher's setup, then each unit's in order."""
    functions = {"dp_setup": None}
    functions |= {f["setup"]: None for f in units if "setup" in f}
    return "\n".join(
        [
            "uint32_t dr_units_setup(dr_frame_t* frame) {",
            "    uint32_t code = 0;",
            *calls(functions, "frame"),
            "    return code;",
            "}",
        ]
    )


def view_text(layout):
    """dr_view: the dispatcher's view (dp_view), then each unit's frame in the
    pipeline's order; ValueError for a unit with a layer (its layers are the pulls')."""
    functions = {"dp_view": None}
    for (owner, _, _), named in zip(layout.units, director.unit_lines(layout)):
        if "layer" in named:
            raise ValueError(
                f"dispatcher: {owner}'s unit runs a layer, which the view's pulls hold"
            )
        if "frame" in named:
            functions[named["frame"]] = None
    return "\n".join(
        [
            "uint32_t dr_view(dr_frame_t* frame, const dr_view_t* view) {",
            "    uint32_t code = 0;",
            *calls(functions, "frame, view"),
            "    return code;",
            "}",
        ]
    )


def source_text(layout, steps):
    """pipeline.c: each unit's header, the setups, the steps' frame words, the view,
    the command switch."""
    includes = [
        f'#include "{function_prefix(owner)}_unit.h"'
        for owner, _, _ in layout.units
        if owner != NAME
    ]
    head = (
        "/* Generated by prism.program.dispatch.generate: the setups, the steps' frame "
        "words, the views as pulls. */\n"
        '#include "dispatch.h"\n' + "\n".join(includes)
    )
    parts = [
        head,
        setup_text(director.unit_lines(layout)),
        frame_words_text(steps),
        view_text(layout),
        director.program_text(layout),
    ]
    return "\n\n".join(parts) + "\n"


def write(layout, program_header, program_prefix, builders, built, words, steps, root):
    """pipeline.h and pipeline.c of the pulls' form into a folder of `root` named by
    their text (`built`: {"work", "sums": C builder}; `words`: {define: word};
    `steps`: (frame words function, depth)): the folder."""
    texts = {
        HEADER: header_text(
            layout, program_header, program_prefix, builders, built, words
        ),
        SOURCE: source_text(layout, steps),
    }
    digest = hashlib.sha256("".join(texts.values()).encode()).hexdigest()[:16]
    folder = Path(root) / f"dispatch-{digest}"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        path = folder / name
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
    return folder
