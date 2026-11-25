"""What can be chosen: the presets of configs/pipeline that render a view (given the
slot view.camera), the generated scenes and the public scenes of the data root with
their views; a choice checked against them."""

from prism_cli import preset

from prism_common.paths import data_root
from prism_common.slots import SLOTS
from prism_reference.scene.generated import PRESETS as GENERATED
from prism_reference.scene.public.table import public_dir, table

VIEW_SLOT = "view.camera"  # a pipeline given it renders a view


def described(name, globals_):
    """A preset as the page shows it: its name, its line, its implementations, the
    slots they write with what each holds, and what it takes from a scene's view."""
    pipeline = globals_["PIPELINE"]
    doc = (globals_.get("__doc__") or "").strip()
    return {
        "name": name,
        "about": " ".join(doc.split()),
        "implementations": pipeline.names(),
        "inputs": list(globals_.get("SCENE_INPUTS", ())),
        "writes": [
            {"slot": slot, "what": SLOTS.get(slot).what}
            for implementation in pipeline.implementations
            for slot in implementation.writes
        ],
    }


def pipelines():
    """The presets that render a view, described, by name."""
    out = {}
    for name in preset.names():
        globals_ = preset.globals_of(name)
        pipeline = globals_.get("PIPELINE")
        if pipeline is not None and VIEW_SLOT in pipeline.inputs:
            out[name] = described(name, globals_)
    return out


def scenes():
    """The scenes by name: the generated ones (no views) and the public ones whose
    mesh is in the data root (their views)."""
    out = {name: {"name": name, "views": [], "generated": True} for name in GENERATED}
    folder = public_dir(data_root())
    for name, entry in table().items():
        if (folder / f"{name}.npz").is_file():
            views = list(entry["views"])
            out[name] = {"name": name, "views": views, "generated": False}
    return out


def catalog():
    """What the page may choose: pipelines and scenes."""
    return {"pipelines": list(pipelines().values()), "scenes": list(scenes().values())}


def checked(choice, known):
    """A choice (pipeline, scene, view) of the catalog `known`; ValueError otherwise."""
    pipeline, scene, view = choice
    by_pipeline = {one["name"]: one for one in known["pipelines"]}
    if pipeline not in by_pipeline:
        raise ValueError(f"no pipeline {pipeline!r} that renders a view")
    by_name = {one["name"]: one for one in known["scenes"]}
    if scene not in by_name:
        raise ValueError(f"no scene {scene!r}")
    views = by_name[scene]["views"]
    if views and view not in views:
        raise ValueError(f"scene {scene!r} has the views {', '.join(views)}")
    if not views and view is not None:
        raise ValueError(f"scene {scene!r} has no views")
    inputs = by_pipeline[pipeline]["inputs"]
    if inputs and view is None:
        raise ValueError(
            f"pipeline {pipeline!r} takes {', '.join(inputs)} from a scene's view"
        )
    return pipeline, scene, view
