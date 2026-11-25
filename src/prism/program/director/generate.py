"""The generated part of a pipeline's thread: pipeline.h (the layout's header, the
program's thread header) and pipeline.c (the units' sequence and the command switch)."""

import hashlib
from pathlib import Path

from prism.core.resources import (
    DIRECTOR,
    FRAME_COMMAND,
    function_prefix,
    macro_prefix,
)

HEADER = "pipeline.h"
SOURCE = "pipeline.c"


def header_text(layout, program_header, program_prefix, builders):
    """pipeline.h: the layout's macros, then the program's generated thread header and
    DR_PLACE(name), a word place of its handlers' commands (<PROGRAM>_<HANDLER>_<NAME>),
    DR_LOAD_WORD(name), a load word: a tensor of the make's address; for each unit with
    a class, DR_<UNIT>_BUILD(name), the builder of its class's handler (`builders`:
    {unit: the builders' prefix}); with one class, DR_BUILD(name), its builder."""
    lines = [
        "",
        "/* The program's thread header: its handlers' builders and word places. */",
        f'#include "{program_header}"',
        f"#define DR_PLACE(name) {program_prefix}_##name",
        f"#define DR_LOAD_WORD(name) {program_prefix.lower()}_word"
        + f"({program_prefix}_WORD_##name)",
    ]
    lines += [
        f"#define {macro_prefix(owner)}_BUILD(name) {prefix}_##name"
        for owner, prefix in builders.items()
    ]
    if len(builders) == 1:
        lines.append(f"#define DR_BUILD(name) {program_prefix.lower()}_##name")
    return layout.header() + "\n".join(lines) + "\n"


def unit_lines(layout):
    """Per unit in the pipeline's order: {role or command: its C function}."""
    return [unit.functions(function_prefix(owner)) for owner, unit, _ in layout.units]


def setup_text(units):
    """dr_units_setup: each unit's setup in order."""
    calls = [
        f"    if (code == 0) {{\n        code = {functions['setup']}(frame);\n    }}"
        for functions in units
        if "setup" in functions
    ]
    return "\n".join(
        [
            "uint32_t dr_units_setup(dr_frame_t* frame) {",
            "    uint32_t code = 0;",
            *calls,
            "    (void)frame;",
            "    return code;",
            "}",
        ]
    )


def view_text(units):
    """dr_view: the result `view` its index; unit by unit, its layer for each layer in
    turn (in a DEPTH view the layers whose depth column is set; the result `layer` the
    last one run), then its frame."""
    body = ["    frame->times[DR_R_VIEW] = view->index;"]
    for functions in units:
        if "layer" in functions:
            body += [
                "    for (layer.index = 0; code == 0 && layer.index < frame->layers;",
                "         layer.index++) {",
                "        layer.words = (const volatile uint32_t*)dr_region(",
                "            DR_REGION_LAYERS,",
                "            4u * DR_LAYER_WORDS * (view->index * DR_LAYERS + layer.index)",
                "        );",
                "        if (view->kind == DR_VIEW_DEPTH && !layer.words[DR_L_DEPTH]) {",
                "            continue;",
                "        }",
                f"        code = {functions['layer']}(frame, view, &layer);",
                "        frame->times[DR_R_LAYER] = layer.index;",
                "    }",
            ]
        if "frame" in functions:
            body += [
                "    if (code == 0) {",
                f"        code = {functions['frame']}(frame, view);",
                "    }",
            ]
    return "\n".join(
        [
            "uint32_t dr_view(dr_frame_t* frame, const dr_view_t* view) {",
            "    dr_layer_t layer;",
            "    uint32_t code = 0;",
            *body,
            "    (void)frame;",
            "    (void)view;",
            "    (void)layer;",
            "    return code;",
            "}",
        ]
    )


def program_text(layout):
    """kmx_program: the FRAME command, then each unit's served commands."""
    cases = []
    for name, (owner, _, _) in layout.commands.items():
        macro = f"{macro_prefix(owner)}_COMMAND_{name.upper()}"
        if name == FRAME_COMMAND and owner == DIRECTOR:
            call = "dr_serve_frame(frame)"
        else:
            call = f"{function_prefix(owner)}_unit_{name}(frame, command)"
        cases += [
            f"        case {macro}:",
            f"            return frame->set_up ? frame->set_up : {call};",
        ]
    return "\n".join(
        [
            "uint32_t kmx_program(const km_command_t* command) {",
            "    dr_frame_t* frame = dr_state();",
            "    switch (kmx_handler(command)) {",
            *cases,
            "    }",
            "    return DR_BAD_ARGS;",
            "}",
        ]
    )


def source_text(layout):
    """pipeline.c: each unit's header, the setups, the view, the command switch."""
    units = unit_lines(layout)
    includes = [
        f'#include "{function_prefix(owner)}_unit.h"' for owner, _, _ in layout.units
    ]
    return (
        "\n\n".join(
            [
                "/* Generated by prism.program.director.generate: the units' sequence. */\n"
                '#include "director.h"\n' + "\n".join(includes),
                setup_text(units),
                view_text(units),
                program_text(layout),
            ]
        )
        + "\n"
    )


def write(layout, program_header, program_prefix, builders, root):
    """pipeline.h and pipeline.c for `layout` into a folder of `root` named by their
    text: the folder."""
    texts = {
        HEADER: header_text(layout, program_header, program_prefix, builders),
        SOURCE: source_text(layout),
    }
    digest = hashlib.sha256("".join(texts.values()).encode()).hexdigest()[:16]
    folder = Path(root) / f"pipeline-{digest}"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        path = folder / name
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
    return folder
