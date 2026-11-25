"""The sun's pass of a pipeline by a Loop: the sun set (the options' `sun`, else the
lights' own), a frame or more, the card's shadow map against the reference's at that
sun (the light stage's sun_check), the passes' codes and times."""

from prism.stages.direct.light.model.expect import sun_check
from prism_reference.direct.lights import sun_angles
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


def sun_map(loop, scene):
    """The card's map now against the reference's at the host's sun: the report."""
    host = loop.loaded.hosts[NAME]
    report = sun_check(
        scene, loop.options["materials"], host.moved(), host.map(loop.loaded)
    )
    return {name: report[name] for name in KEPT}


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
