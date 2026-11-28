"""The lamps' maps of a pipeline by a Loop: frames until every face is drawn (LAMPS
commands before them), each lamp face's map on the card against the reference's at every
texel, its levels against the reference's of the card's map (exact), the LAMPS commands'
codes and each face's time; `failed` on a face apart, a code or a face not drawn. Each
face's reference is kept in the cache by what it is made of (`kept_references`: made with
no card, before the card is held)."""

import json
import os
import time

import numpy as np

from prism.stages.material.texture.model.layers import later_pieces
from prism_common.digest import Digest
from prism_common.paths import cache_root, data_root
from prism_reference.direct import lights as reference_lights
from prism_reference.direct.lamp_maps import face_view, lamp_faces
from prism_reference.direct.shadow_filter import nearest_levels
from prism_reference.raster.frames import rasterize_shaded
from prism_reference.raster.setup import setup
from prism_reference.scene.camera import with_size

NAME = "direct.shadow_pcf"
FRAMES = 2  # frames a check runs, unless the options say
MOST_FRAMES = 256  # frames run at most while lamp faces are not drawn
RELATIVE = 1e-5  # texels further apart than this share differ
FOLDER = "lamp_faces"  # the faces' kept references, under the cache root
VERSION = 1  # of a kept face: raised when its reference's drawing changes


def made_of(scene, materials, lights):
    """The digest of what every face's reference is drawn from: the mesh, the
    materials' arrays, the lights' visibility and VERSION."""
    digest = Digest(f"{VERSION}")
    named = [("positions", scene["positions"]), ("indices", scene["indices"])]
    named += sorted(materials.items()) + [("visibility", lights["visibility"])]
    for name, value in named:
        a = np.ascontiguousarray(value)
        digest.update(f"{name}{a.dtype}{a.shape}".encode())
        digest.update(a)
    return digest.hexdigest()


def face_key(base, face):
    """The key of one face's reference: `base` (made_of), its lamp, face, size and
    camera."""
    digest = Digest(base)
    named = [int(face["lamp"]), face["face"], [int(v) for v in face["size"]]]
    digest.update(json.dumps(named).encode())
    digest.update(np.ascontiguousarray(face["camera"]))
    return digest.hexdigest()[:32]


def drawn(scene, materials, lights, face):
    """A face's reference: rasterize_shaded's 1/z at its camera and size, and the
    later pieces of cut triangles (as the sun's check)."""
    view = face_view(scene, face)
    shaded = rasterize_shaded(view, materials)
    want, tri = shaded["depth"], shaded["tri"]
    later = np.zeros(want.shape, dtype=bool)
    owner = setup(view)["tri"]
    if (owner[1:] == owner[:-1]).any():
        corner = {**materials, "light": lights["visibility"][view["indices"]]}
        later = later_pieces(view, corner, tri)
    return want, later


def kept_face(base, scene, materials, lights, face):
    """drawn() of a face: read when kept under its key, else drawn and kept (a
    temporary name, then renamed)."""
    path = cache_root() / FOLDER / f"{face_key(base, face)}.npz"
    if path.exists():
        with np.load(path) as f:
            return f["depth"], f["later"]
    want, later = drawn(scene, materials, lights, face)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    with open(part, "wb") as handle:
        np.savez(handle, depth=want, later=later)
    part.replace(path)
    return want, later


def kept_references(preset):
    """Every lamp face's reference of an opened preset made and kept, with no card:
    the faces of the preset's lights (else the scene's lights file)."""
    options = preset.options
    lights = options.get("lights") or reference_lights.load(
        options["name"], data_root()
    )
    faces = lamp_faces(lights) if options.get("lamp_maps", True) else []
    scene, materials = preset.scene, options["materials"]
    base = made_of(scene, materials, lights)
    for face in faces:
        kept_face(base, scene, materials, lights, face)
    return len(faces)


def face_report(base, scene, materials, lights, one):
    """One face's map against its kept reference (kept_face): texels covered, over
    RELATIVE apart and empty on one side only (later pieces of cut triangles apart);
    its levels' texels apart."""
    face, got = one["face"], one["map"]
    want, later = kept_face(base, scene, materials, lights, face)
    with np.errstate(all="ignore"):
        relative = np.abs(got.astype(np.float64) - want) / np.abs(
            want.astype(np.float64)
        )
    both = (got != 0) & (want != 0) & ~later
    report = {
        "lamp": int(face["lamp"]),
        "face": face["face"],
        "size": [int(v) for v in face["size"]],
        "texels_covered": int((want != 0).sum()),
        "later_pieces": int(later.sum()),
        "differ": int((both & (relative > RELATIVE)).sum()),
        "one_empty": int((((got == 0) != (want == 0)) & ~later).sum()),
        "max_relative": float(relative[both].max(initial=0)),
    }
    if one.get("levels"):
        wanted = nearest_levels(got)[1:]
        report["levels_apart"] = int(
            sum(
                (a.view(np.uint32) != b.view(np.uint32)).sum()
                for a, b in zip(one["levels"], wanted, strict=True)
            )
        )
    return report


def compared(scene, materials, lights, maps):
    """Every face's report and their sums."""
    base = made_of(scene, materials, lights) if maps else None
    reports = [face_report(base, scene, materials, lights, one) for one in maps]
    return {
        "differ": sum(f["differ"] for f in reports),
        "one_empty": sum(f["one_empty"] for f in reports),
        "levels_apart": sum(f.get("levels_apart", 0) for f in reports),
        "texels_covered": sum(f["texels_covered"] for f in reports),
        "by_face": reports,
    }


def check(loop):
    """The frames (the hosts' views, LAMPS before them while a face is not drawn),
    every lamp face's map against the reference's; after the stop the passes and the
    LAMPS commands' times."""
    frames = int(loop.options.get("frames", FRAMES))
    scene = with_size(loop.scene, loop.size)
    began = time.perf_counter()
    host = loop.loaded.hosts[NAME]
    codes = [loop.frame(scene["camera"]).code for _ in range(frames)]
    while host.faces.left and len(codes) < MOST_FRAMES:
        codes.append(loop.frame(scene["camera"]).code)
    maps = host.lamp_maps(loop.loaded)
    seconds = time.perf_counter() - began
    loop.stop()
    times = host.times(loop.loaded)
    lamps = [row for row in times if row["command"] == "lamps"]
    faces = [t for row in lamps for t in row["quadrants"] if t > 0]
    out = {
        "frames": len(codes),
        "codes": sorted(set(codes)),
        "frames_s": round(seconds, 3),
        "levels": host.levels_state(),
        "faces": len(host.faces.faces),
        "left": len(host.faces.left),
        "commands": [p["lamps"][1] for p in host.passes if "lamps" in p],
        "lamps_s": [p["s"] for p in host.passes if "lamps" in p],
        "face_ms": {
            "mean": round(float(np.mean(faces)) / 1e3, 2) if faces else None,
            "least": round(min(faces) / 1e3, 2) if faces else None,
            "most": round(max(faces) / 1e3, 2) if faces else None,
            "all": round(sum(faces) / 1e3, 1),
        },
        "levels_ms": [round(row["levels"] / 1e3, 2) for row in lamps],
    }
    materials = loop.options["materials"]
    out |= compared(scene, materials, host.lights, maps)
    apart = out["differ"] or out["one_empty"] or out["levels_apart"]
    out["failed"] = bool(apart or any(codes) or out["left"])
    return out
