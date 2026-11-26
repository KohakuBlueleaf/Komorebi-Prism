"""The names of the codes a frame of the threads' form leaves: a view's and a unit's
result codes, the X280 thread's progress marks, and the places of the cores' give-ups
(the loop's FW_*, the steps' and the kinds' own kWhere*)."""

import re
from functools import cache
from pathlib import Path

from prism.core.headers import constexpr, defined
from prism.program.director.thread import RUNTIME as DIRECTOR
from prism.program.dispatch.thread import RUNTIME as DISPATCH

PRISM = Path(__file__).resolve().parents[2]  # src/prism/
FRAME_H = PRISM / "program" / "frame" / "kernels" / "frame.h"
UNIT_CODE = re.compile(
    r"^#define\s+(\w+)\s+\(DR_UNIT_CODES\s*\+\s*(0x[0-9A-Fa-f]+|\d+)u?\)", re.MULTILINE
)
# the folders whose headers hold the steps' and the kinds' give-up places
WHERE_FOLDERS = ("steps", "threads")
RESULT_CODES = ("DR_BAD_ARGS", "DR_RING", "DR_COMMAND", "DR_PARALLEL")


def joined(table, value, name):
    """`name` added to `table`'s names of `value` (two names of one value: a|b)."""
    have = table.get(value)
    table[value] = name if have is None or name in have.split("|") else f"{have}|{name}"


@cache
def result_names():
    """{code: name} of a thread command's result: the director's codes and every
    `#define NAME (DR_UNIT_CODES + n)` of a header under src/prism/."""
    director = defined(DIRECTOR / "director.h")
    out = {}
    for name in RESULT_CODES:
        joined(out, director[name], name)
    base = director["DR_UNIT_CODES"]
    for header in sorted(PRISM.rglob("*.h")):
        for name, offset in UNIT_CODE.findall(header.read_text()):
            joined(out, base + int(offset, 0), name)
    return out


@cache
def progress_names():
    """{mark: name} of the X280 thread's progress marks before a view's waits."""
    marks = defined(DISPATCH / "dispatch.h")
    return {v: n for n, v in marks.items() if n.startswith("DP_WHERE_")}


@cache
def where_names():
    """{where: name} of a give-up's place: the loop's FW_* (frame.h), then each
    step's and kind's kWhere* (constexpr in their headers)."""
    out = {}
    for name, value in defined(FRAME_H).items():
        if name.startswith("FW_") and name != "FW_WAIT_CYCLES":
            joined(out, value, name)
    for header in sorted((PRISM / "stages").rglob("*.h*")):
        if not set(WHERE_FOLDERS) & set(header.parts):
            continue
        for name, value in constexpr(header).items():
            if name.startswith("kWhere"):
                joined(out, value, name)
    return out


def result_name(code):
    """A result code by name: 0 'ok', a known code's name, else its number."""
    if code == 0:
        return "ok"
    return result_names().get(int(code), f"code {int(code)}")


def progress_name(mark):
    """A progress mark by name, else its number."""
    return progress_names().get(int(mark), f"mark {int(mark):#x}")


def where_name(where):
    """A give-up's place: Komorebi's name as it decoded it, ours for a number."""
    if isinstance(where, str):
        return where
    return where_names().get(int(where), f"where {int(where)}")
