"""What can be chosen: the presets of configs/pipeline that render a view (given the
slot view.camera), the generated scenes and the public scenes of the data root with
their views and what their files say of them; a choice checked against them."""

from pathlib import PurePath

from prism_cli import preset

from prism_common.paths import data_root
from prism_common.slots import SLOTS
from prism_reference.scene.generated import PRESETS as GENERATED
from prism_reference.scene.generated import make_preset
from prism_reference.scene.public import files
from prism_reference.scene.public.table import table

VIEW_SLOT = "view.camera"  # a pipeline given it renders a view
MIB = 1 << 20
# a public scene's own mesh format, by the suffix of its table's mesh member
MESH_FORMATS = {".obj": "OBJ", ".json": "Tungsten"}
OPENED, CONVERTED, GENERATED_FORMAT = "glTF opened", "glTF converted", "generated"
NO_VIEW = "a generated scene has no view to take {} from"
LAYERS = ("opaque", "masked", "glass")
LAYER_KINDS = {  # the material kinds whose triangles make each layer
    "opaque": ("flat", "textured", "lit", "emissive"),
    "masked": ("masked",),
    "glass": ("transparent",),
}


def described(name, globals_):
    """A preset as the page shows it: its name, its line, its implementations, the
    slots they write with what each holds, what it takes from a scene's view and the
    scene's files it reads beside the mesh."""
    pipeline = globals_["PIPELINE"]
    doc = (globals_.get("__doc__") or "").strip()
    return {
        "name": name,
        "about": " ".join(doc.split()),
        "implementations": pipeline.names(),
        "inputs": list(globals_.get("SCENE_INPUTS", ())),
        "files": list(globals_.get("SCENE_FILES", ())),
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


def short(path):
    """A file named by its folder and its name, no more of its path."""
    path = PurePath(path)
    return f"{path.parent.name}/{path.name}" if path.parent.name else path.name


def source_of(entry):
    """(format, source) of a public scene's entry: an opened or converted glTF file
    (its record `source` when kept), else the table's own mesh file."""
    kept = entry.get("source")
    if "opened" in entry or kept is not None:
        form = OPENED if "opened" in entry else CONVERTED
        if kept is None:
            return form, {"file": entry["opened"]["file"]}
        out = {"file": short(kept["file"]), "format": kept["format"]}
        return form, out | {"mib": round(kept["bytes"] / MIB, 1)}
    meshes = entry.get("meshes") or []
    if not meshes:
        return CONVERTED, None
    member = meshes[0].get("member") or meshes[0]["file"]
    form = MESH_FORMATS.get(PurePath(member).suffix.lower(), PurePath(member).suffix)
    return form, {"file": f"{meshes[0]['file']}: {member}"}


def layers_of(by_kind):
    """The layers a scene's triangles by material kind make; None when unknown."""
    if by_kind is None:
        return None
    return [
        layer
        for layer in LAYERS
        if any(by_kind.get(kind, 0) for kind in LAYER_KINDS[layer])
    ]


def lighting_of(name, data):
    """The lighting file's sky visibility (`baked`, `open`); None without the file."""
    found = files.counts(name, "lighting", data)
    return None if found is None else found.get("visibility", "baked")


def facts(name, entry, data):
    """What a public scene's files and records say of it; a number it lacks is None."""
    form, source = source_of(entry)
    kept = entry.get("source") or {}
    mesh = files.counts(name, "mesh", data) or {}
    materials = files.counts(name, "materials", data) or {}
    texel_bytes = materials.get("texel_bytes")
    return {
        "format": form,
        "source": source,
        "triangles": mesh.get("triangles_total"),
        "stored": kept.get("stored_triangles"),
        "objects": kept.get("objects"),
        "instances": kept.get("instances"),
        "materials": materials.get("materials"),
        "textures": materials.get("textures"),
        "texel_mib": None if texel_bytes is None else round(texel_bytes / MIB, 1),
        "layers": layers_of(materials.get("triangles_by_kind")),
        "lighting": lighting_of(name, data),
        "present": [kind for kind in files.FILES if files.present(name, kind, data)],
    }


def generated_facts(name):
    """What a generated scene holds: its triangles, made as the reference makes it."""
    triangles = len(make_preset(name)["indices"])
    keys = ("source", "stored", "objects", "instances", "materials", "textures")
    out = dict.fromkeys(keys) | {"texel_mib": None, "layers": None, "lighting": None}
    return out | {"format": GENERATED_FORMAT, "triangles": triangles, "present": []}


def refusal(described_, scene):
    """Why the preset `described_` cannot run on `scene` (as `scenes` gives it); None
    when it can."""
    if scene["generated"]:
        inputs = described_["inputs"]
        return NO_VIEW.format(", ".join(inputs)) if inputs else None
    lacking = [kind for kind in described_["files"] if kind not in scene["present"]]
    return "; ".join(files.missing(kind) for kind in lacking) or None


def scenes(known_pipelines):
    """The scenes by name: the generated ones (no views) and the public ones whose
    mesh is in the data root (their views), each with its facts and, for every preset,
    the reason it cannot run on it (None when it can)."""
    out = {}
    for name in GENERATED:
        out[name] = {"name": name, "views": [], "generated": True}
        out[name] |= generated_facts(name)
    data = data_root()
    for name, entry in table().items():
        if files.present(name, "mesh", data):
            views = list(entry["views"])
            out[name] = {"name": name, "views": views, "generated": False}
            out[name] |= facts(name, entry, data)
    for scene in out.values():
        scene["refusals"] = {
            preset_name: refusal(described_, scene)
            for preset_name, described_ in known_pipelines.items()
        }
    return out


def catalog(offer=None):
    """What the page may choose: pipelines and scenes; with `offer` (preset names) only
    those presets and the scenes one of them can run on. ValueError naming a preset of
    `offer` that does not render a view."""
    known = pipelines()
    if offer:
        unknown = [name for name in offer if name not in known]
        if unknown:
            raise ValueError(
                f"no preset {', '.join(unknown)} that renders a view; "
                f"the presets: {', '.join(known)}"
            )
        known = {name: known[name] for name in dict.fromkeys(offer)}
    found = scenes(known).values()
    if offer:
        found = [one for one in found if None in one["refusals"].values()]
    return {"pipelines": list(known.values()), "scenes": list(found)}


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
    refused = by_name[scene].get("refusals", {}).get(pipeline)
    if refused is not None:
        raise ValueError(f"pipeline {pipeline!r} cannot run on {scene!r}: {refused}")
    return pipeline, scene, view
