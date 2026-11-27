"""A scene with no valid field at load (its sun map the card draws) waits for its first
update before any frame, so the update a check judges is driven as the second one: the
field made first at another sun with one frame drawn, then the sun asked set."""

from prism.check.field_frames import CONTROL, UPDATE

TURN = 60.0  # degrees of azimuth from the asked sun to the first one


def first_sun(sun):
    """The sun the first field is made at: `sun` (azimuth, elevation) turned by TURN."""
    azimuth, elevation = (float(angle) for angle in sun)
    return ((azimuth + TURN) % 360.0, elevation)


def second(loop, camera, sun):
    """When `loop` (loaded at the sun options `sun`) has no valid field: its sun set to
    first_sun, one frame drawn (its update waited), its sun set back; then
    {first_sun, code}, else None."""
    if "sun" not in sun or loop.loaded.hosts[UPDATE].made is not None:
        return None
    turned = first_sun(sun["sun"])
    loop.set(CONTROL, turned)
    code = loop.frame(camera).code
    loop.set(CONTROL, tuple(float(angle) for angle in sun["sun"]))
    return {"first_sun": list(turned), "code": code}
