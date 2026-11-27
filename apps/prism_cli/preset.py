"""A preset of configs/pipeline opened for a scene: its pipeline, its options with the
scene's inputs (its SCENE_INPUTS) and the size, the scene, its reference and its judge;
without the far field when the scene lacks its files; how the preset runner, the command
line and the viewer's server open a preset."""

import runpy
from dataclasses import dataclass, field
from pathlib import Path

from prism.core.implementation import IMPLEMENTATIONS
from prism.core.pipeline import Pipeline
from prism.loop import Loop
from prism_cli import far_field
from prism_common.build import build
from prism_common.paths import data_root
from prism_reference.direct.lights import load as load_lights
from prism_reference.scene.frame import frame_size
from prism_reference.scene.generated import make_preset
from prism_reference.scene.public import files
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.views import make_view

ROOT = Path(__file__).resolve().parents[2]
PRESETS = ROOT / "configs" / "pipeline"
POST = "post"  # the item the display fills: left out without it
INDIRECT = "indirect"  # the item the far field fills, and LIGHT's term of it
FAR_FIELD = ("indirect", "transport")  # a scene's files of the far field (SCENE_FILES)
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


def far_field_lacking(globals_, scene, view):
    """The far field's files the preset reads (its SCENE_FILES) that the public scene
    lacks, by kind; () for a generated scene (no view)."""
    if view is None:
        return ()
    wanted = [kind for kind in globals_.get("SCENE_FILES", ()) if kind in FAR_FIELD]
    return tuple(kind for kind in wanted if not files.present(scene, kind, data_root()))


def without_far_field(pipeline, globals_):
    """`pipeline` without the implementations that fill the far field's item, those
    that fill no item and read what nobody writes any more, each of the preset's
    FAR_FIELD_ABSENT replaced by its choice; the inputs left that one reads."""
    swap = [
        (build(old, IMPLEMENTATIONS), build(new, IMPLEMENTATIONS))
        for old, new in globals_.get("FAR_FIELD_ABSENT", {}).items()
    ]
    kept = [i for i in pipeline.implementations if INDIRECT not in i.fills]
    kept = [next((new for old, new in swap if old is i), i) for i in kept]
    while True:
        given = set(pipeline.inputs).union(*(i.writes for i in kept))
        left = [i for i in kept if i.fills or set(i.reads) <= given]
        if len(left) == len(kept):
            break
        kept = left
    read = set().union(*(i.reads for i in kept))
    inputs = [slot for slot in pipeline.inputs if slot in read]
    return Pipeline(pipeline.name, kept, inputs=inputs)


@dataclass
class Opened:
    """A preset made ready for a scene: what Loop.open takes, and the preset's own
    REFERENCE and JUDGE (each of (loop, scene), None when the preset has none), and
    the far field's files the scene lacks (the preset opened without it when any)."""

    name: str
    pipeline: Pipeline
    options: dict
    scene: dict
    size: tuple
    globals: dict = field(repr=False)
    lacking: tuple = ()
    building: dict | None = None

    @property
    def far_field(self):
        """None when the preset reads no far field; else `present`, or `absent` with
        what the scene lacks."""
        wanted = [k for k in self.globals.get("SCENE_FILES", ()) if k in FAR_FIELD]
        if not wanted:
            return None
        return f"absent: {self.missing}" if self.lacking else "present"

    @property
    def missing(self):
        """What the scene lacks of the far field, as the catalog names it."""
        return "; ".join(files.missing(kind) for kind in self.lacking)

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


def opened(name, scene, view=None, size=None, options=None, display=True, build=False):
    """The preset `name` for the generated scene `scene` or a public scene's `view`, at
    `size` (the view's own when None), its OPTIONS updated by `options`, the scene's
    inputs given; without the far field (its implementations, its term) when the view
    lacks its files, their build started beside the frames when `build`
    (`far_field.start`); without the implementations that fill post when not
    `display`. ValueError with the reason when the preset or the scene cannot be opened.
    """
    globals_ = globals_of(name)
    pipeline = globals_["PIPELINE"]
    out = dict(globals_["OPTIONS"])
    lacking = far_field_lacking(globals_, scene, view)
    if lacking:
        pipeline = without_far_field(pipeline, globals_)
        terms = out.get("terms")
        if terms is not None:
            out["terms"] = tuple(term for term in terms if term != INDIRECT)
    if not display:
        kept = [i.name for i in pipeline.implementations if POST not in i.fills]
        pipeline = Pipeline(pipeline.name, kept, inputs=pipeline.inputs)
    made = scene_of(scene, view)
    size = tuple(int(n) for n in (size or frame_size(made)))
    out |= {"size": size} | scene_inputs(name, globals_, scene, view)
    out |= dict(options or {})
    building = far_field.start(scene, data_root()) if lacking and build else None
    return Opened(name, pipeline, out, made, size, globals_, lacking, building)
