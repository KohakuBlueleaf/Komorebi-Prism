"""The job thread's part of the frame's thread: a unit serving `job_wants` (the cores a
job wants, the field it made), its words, and the owner name its C is prefixed by."""

from pathlib import Path

from prism.core.headers import defined
from prism.core.unit import Unit

OWNER = "jobs"  # its functions are jobs_unit_*, its header jobs_unit.h
FOLDER = Path(__file__).resolve().parent
COMMAND = "job_wants"
W = defined(FOLDER / "c" / "jobs_unit.h")
WORDS = ("cores", "field", "half", "scale")  # job_wants's a0 to a3
PLACES = {name: W[f"JOBS_WANTS_{name.upper()}"] for name in WORDS}

FRAME_UNIT = Unit(
    sources=("c/jobs_unit.c",),
    includes=("c",),
    serves=(COMMAND,),
)


def wants_args(cores, field=0, half=0, scale=0):
    """job_wants's words in their places."""
    given = {"cores": cores, "field": field, "half": half, "scale": scale}
    args = [0] * len(WORDS)
    for name, value in given.items():
        args[PLACES[name]] = value
    return args
