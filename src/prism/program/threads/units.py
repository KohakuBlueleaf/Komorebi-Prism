"""The threads' form's units of the frame's thread: what each stage gives the view's
pulls (its numbers, its layer columns, its regions) without a role of its own, under
its stage-wise name, whose macros the steps' frame words read."""

from dataclasses import replace
from pathlib import Path

from prism.core.unit import Unit
from prism.stages.direct.light import thread_unit as light
from prism.stages.material.texture.unit import UNIT as TEXTURE
from prism.stages.post.show.unit import UNIT as SHOW

STAGES = Path(__file__).resolve().parents[2] / "stages"


def thread_folder(stage):
    """A stage's thread folder (its unit header, `<name>_unit.h`) as an absolute path,
    for a unit whose host lives outside the stage."""
    return str(STAGES / stage / "thread")


# SHADE's layer columns, read by the material step's frame words; its table shared
# as slot mesh.attributes; no layer of its own (the tile thread's steps shade)
MATERIAL = Unit(
    includes=(thread_folder("material/texture"),),
    columns=TEXTURE.columns,
    shares=dict(TEXTURE.shares),
)

# the light step's numbers and the shadow map's column it takes; its frame words
# are the dispatcher's (the steps' C), so the unit names no source
LIGHT = replace(light.UNIT, sources=(), includes=(thread_folder("direct/light"),))
LIGHT_FIELD = replace(
    light.FIELD_UNIT, sources=(), includes=(thread_folder("direct/light"),)
)

# the thresholds' region and the display's numbers, read by the post step's frame
# words; no SHOW or PUSH command (the post step converts on the cores)
POST = Unit(
    includes=(thread_folder("post/show"),),
    regions={"show_table": SHOW.regions["show_table"]},
    numbers=SHOW.numbers,
)
