"""The sun's pass of a pipeline by a Loop: the sun set (the options' `sun`, else the
lights' own), a frame or more, the card's shadow map against the reference's at that
sun (the light stage's sun_check), the passes' codes and times."""

import numpy as np

from prism.stages.direct.light.model.expect import sun_check
from prism.stages.direct.light.model.transmit import blocks_of, transmit_pages
from prism_reference.direct.lights import shadow_side, sun_angles
from prism_reference.direct.transmit import map_kept
from prism_reference.scene.camera import with_size

NAME = "direct.shadow_pcf"
CONTROL = f"{NAME}.sun"
FRAMES = 2  # frames a check runs, unless the options say
KEPT = ("side", "texels_covered", "max_relative", "all", "opaque_layer")
KEPT += ("masked_layer", "empty_in_reference", "by_quadrant")


def sun_of(loop):
    """The sun the check draws: the options', else the lights' own."""
    host = loop.loaded.hosts[NAME]
    return tuple(loop.options.get("sun") or sun_angles(host.lights["sun_direction"]))


def transmit_map(loop, scene, depth):
    """The card's T beside its map `depth` against the reference's kept T over that
    same map: codes apart by more than 1, the largest difference, texels under 255;
    None without T."""
    host = loop.loaded.hosts[NAME]
    first, channels = host.transmit
    if not first:
        return None
    lights = host.moved()
    side = shadow_side(lights)
    count = transmit_pages(side, channels)
    (pages,) = loop.loaded.session.read(host.target, first=first - 1, pages=count)
    got = blocks_of(pages.view(np.uint32).reshape(count, -1), side, channels)
    want = map_kept(scene, lights["shadow_camera"], loop.options["materials"], depth)
    apart = np.abs(got.astype(np.int16) - want["codes"].astype(np.int16))
    return {
        "channels": channels,
        "pages": count,
        "texels": int(apart.shape[0] * apart.shape[1]),
        "card_under_255": int((got < 255).any(axis=2).sum()),
        "reference_under_255": int((want["codes"] < 255).any(axis=2).sum()),
        "apart_over_1": int((apart > 1).any(axis=2).sum()),
        "max_apart": int(apart.max(initial=0)),
    }


def sun_map(loop, scene):
    """The card's map now against the reference's at the host's sun: the report, with
    the map's T (transmit_map) when it has one."""
    host = loop.loaded.hosts[NAME]
    depth = host.map(loop.loaded)
    report = sun_check(scene, loop.options["materials"], host.moved(), depth)
    out = {name: report[name] for name in KEPT}
    through = transmit_map(loop, scene, depth)
    if through is not None:
        out["transmit"] = through
    return out


def check(loop):
    """The sun set, the frames (each a FRAME after the hosts' views), the map against
    the reference's; after the stop the passes and their times."""
    frames = int(loop.options.get("frames", FRAMES))
    scene = with_size(loop.scene, loop.size)
    loop.set(CONTROL, sun_of(loop))
    codes = [loop.frame(scene["camera"]).code for _ in range(frames)]
    report = sun_map(loop, scene)
    loop.stop()
    host = loop.loaded.hosts[NAME]
    return {
        "frames": len(codes),
        "codes": sorted(set(codes)),
        "sun": list(host.sun),
        "passes": host.passes,
        "map": report,
        "times": host.times(loop.loaded),
    }
