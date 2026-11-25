"""A preset of configs/pipeline opened for a scene: its pipeline, its options with the
scene's inputs (its SCENE_INPUTS) and the size, the scene, its reference and its judge;
how the preset runner, the command line and the viewer's server open a preset."""

import runpy
from dataclasses import dataclass, field
from pathlib import Path

from prism.core.pipeline import Pipeline
from prism.loop import Loop
from prism_common.paths import data_root
from prism_reference.direct.lights import load as load_lights
from prism_reference.scene.frame import frame_size
from prism_reference.scene.generated import make_preset
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.views import make_view

ROOT = Path(__file__).resolve().parents[2]
PRESETS = ROOT / "configs" / "pipeline"
POST = "post"  # the item the display fills: left out without it
# what a preset's SCENE_INPUTS name, from a public scene's view
INPUTS = {
    "materials": lambda view: load_materials(view, data_root())[0],
    "name": lambda view: view,
    "lights": lambda view: load_lights(view, data_root()),
}


def names():
    """The presets of configs/pipeline, by name."""
    return sorted(file.stem for file in PRESETS.glob("*.py"))


def globals_of(name):
    """The preset `name`'s globals (PIPELINE, OPTIONS, SCENE_INPUTS, REFERENCE, JUDGE);
    ValueError naming the presets when none."""
    file = PRESETS / f"{name}.py"
    if not file.is_file():
        raise ValueError(f"no preset {name!r}; the presets: {', '.join(names())}")
    return runpy.run_path(str(file))


def view_name(scene, view):
    """A public scene's view as the data root names it."""
    return f"{scene}_{view}"


def scene_of(scene, view):
    """A generated scene, or a public scene's view (its WIDTH x HEIGHT camera)."""
    if view is None:
        return make_preset(scene)
    return make_view(view_name(scene, view), data_root())


def scene_inputs(name, globals_, scene, view):
    """The options the preset takes from the scene's files (its SCENE_INPUTS);
    ValueError without a view when it takes some."""
    wanted = globals_.get("SCENE_INPUTS", ())
    if wanted and view is None:
        raise ValueError(f"preset {name!r} takes {', '.join(wanted)}: a scene's view")
    return {one: INPUTS[one](view_name(scene, view)) for one in wanted}


@dataclass
class Opened:
    """A preset made ready for a scene: what Loop.open takes, and the preset's own
    REFERENCE and JUDGE (each of (loop, scene), None when the preset has none)."""

    name: str
    pipeline: Pipeline
    options: dict
    scene: dict
    size: tuple
    globals: dict = field(repr=False)

    def open(self, session):
        """The Loop of the preset on `session`, its first load done."""
        return Loop.open(self.pipeline, session, self.scene, self.size, self.options)

    def reference(self, loop, scene):
        """The picture a frame of `scene` (a view at its size) on `loop` is compared
        with, at the loop's settings; None without a REFERENCE."""
        made = self.globals.get("REFERENCE")
        return None if made is None else made(loop, scene)

    def judge(self, loop, scene):
        """The preset's judge of a frame's picture of `scene` on `loop`: a function of
        the picture giving its numbers; None without a JUDGE."""
        made = self.globals.get("JUDGE")
        return None if made is None else made(loop, scene)


def opened(name, scene, view=None, size=None, options=None, display=True):
    """The preset `name` for the generated scene `scene` or a public scene's `view`, at
    `size` (the view's own when None), its OPTIONS updated by `options`, the scene's
    inputs given; without the implementations that fill post when not `display`.
    ValueError with the reason when the preset or the scene cannot be opened."""
    globals_ = globals_of(name)
    pipeline = globals_["PIPELINE"]
    if not display:
        kept = [i.name for i in pipeline.implementations if POST not in i.fills]
        pipeline = Pipeline(pipeline.name, kept, inputs=pipeline.inputs)
    made = scene_of(scene, view)
    size = tuple(int(n) for n in (size or frame_size(made)))
    out = dict(globals_["OPTIONS"]) | {"size": size}
    out |= scene_inputs(name, globals_, scene, view) | dict(options or {})
    return Opened(name, pipeline, out, made, size, globals_)
