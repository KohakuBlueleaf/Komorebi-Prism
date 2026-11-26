"""SHOW's thread unit: its C, the slot it takes (the frame's directory column), its
regions (the thresholds' table, the push's words), its numbers and times; with the
option light_shows (LIGHT converts for display) no SHOW command."""

from pathlib import Path

from prism.core.headers import defined
from prism.core.unit import Region, Unit
from prism.stages.post.show.model.table import SHOW

THREAD = "thread"
P = defined(Path(__file__).resolve().parent / THREAD / "post_show_unit.h")


def defines(host):
    """POST_SHOW_BY_LIGHT with the option light_shows: a COLOUR view sends no SHOW."""
    return {"POST_SHOW_BY_LIGHT": "1"} if host.light_shows else {}


UNIT = Unit(
    sources=(f"{THREAD}/post_show_unit.c",),
    includes=(THREAD,),
    frame=True,
    takes=("frame.visibility",),
    regions={
        "show_table": Region(SHOW["kShowPageBytes"], lambda host: host.table),
        "show_push": Region(P["SHOW_PUSH_BYTES"], own=False),
    },
    numbers=("show_display", "show_profile", "show_pushes"),
    times=("show", "push"),
    defines=defines,
)
