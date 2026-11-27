"""SHOW's thread unit: its C, the slot it takes (the frame's directory column), its
regions (the thresholds' table with the view's words after it, the push's words), its
numbers and times; with the option light_shows (LIGHT converts for display) no SHOW
command."""

from pathlib import Path

from prism.core.headers import defined
from prism.core.unit import Region, Unit
from prism.stages.post.show.model.table import SHOW
from prism.stages.post.show.model.view import VIEW

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
        "show_table": Region(
            SHOW["kShowPageBytes"] + VIEW["kViewRegionBytes"],
            lambda host: host.table_words(),
        ),
        "show_push": Region(P["SHOW_PUSH_BYTES"], own=False),
    },
    numbers=("show_display", "show_profile", "show_pushes"),
    times=("show", "push"),
    defines=defines,
)
