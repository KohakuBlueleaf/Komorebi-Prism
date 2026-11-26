"""The threads of an assembled program, one a work cluster that has units: the runtime,
the generated sequence and that cluster's units' C, with its layout's regions and
commands, declared on the program."""

import inspect
from pathlib import Path

from prism.core.headers import INCLUDE
from prism.core.resources import function_prefix
from prism.core.unit import FRAMES
from prism.program.director import generate
from prism_common.paths import build_root

RUNTIME = Path(__file__).resolve().parent / "c"
CLUSTER = FRAMES  # the work cluster the frame's thread runs on
DEADLINE = 10.0  # seconds kmx_main may take


def folder_of(implementation):
    """The implementation's folder: its host module's."""
    return Path(inspect.getsourcefile(implementation.host)).resolve().parent


def unit_files(implementation):
    """A unit's sources and include folders as paths; ValueError for a source whose
    name is not prefixed with the implementation's."""
    unit, folder = implementation.thread, folder_of(implementation)
    prefix = function_prefix(implementation.name) + "_"
    sources = [folder / source for source in unit.sources]
    for source in sources:
        if not source.name.startswith(prefix):
            raise ValueError(
                f"{implementation.name}'s thread source {source.name!r} is not "
                f"prefixed {prefix!r}"
            )
    return sources, [folder / include for include in unit.includes]


def program_name(program):
    """The made program's name: its generated thread header's prefix."""
    return program.name


def builders(assembled):
    """{implementation: its handlers' builders' prefix} of each made class: the
    program's name for one class, the class's name (lower case) in a merge."""
    made = assembled.made
    if len(made) == 1:
        return {name: program_name(assembled.program).lower() for name in made}
    return {name: type(one).__name__.lower() for name, one in made.items()}


def declare(assembled, layout):
    """program.thread(...) of the assembled program for `layout`, on its cluster with
    its units; the thread."""
    program = assembled.program
    owners = {owner for owner, _, _ in layout.units}
    with_unit = [i for i in assembled.pipeline.implementations if i.name in owners]
    sources, includes = [], []
    for implementation in with_unit:
        unit_sources, unit_includes = unit_files(implementation)
        sources += unit_sources
        includes += unit_includes
    stems = [source.stem for source in sources]
    if len(set(stems)) != len(stems):
        raise ValueError(f"thread sources with one name: {', '.join(sorted(stems))}")
    name = program_name(program)
    generated = generate.write(
        layout,
        f"{name}_thread.h",
        name.upper(),
        builders(assembled),
        build_root() / "thread" / name,
    )
    return program.thread(
        cluster=layout.cluster,
        sources=[RUNTIME / "director.c", generated / generate.SOURCE, *sources],
        includes=[RUNTIME, generated, INCLUDE, *includes],
        regions=layout.region_values(),
        handlers=layout.handlers(),
        defines=layout.defines,
        deadline=DEADLINE,
    )
