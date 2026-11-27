"""The option naming a threads' preset's tile thread, and what that tile thread does
that a host may ask about without assembling the program."""

from prism_common.build import located

TILE_THREAD = "tile_thread"  # the option naming the tile thread: a dotted path


def depth_levels(options):
    """Whether the tile thread the options name (TILE_THREAD) writes a DEPTH view's
    levels: one of its DEPTH steps has the word `levels`; False without one."""
    if TILE_THREAD not in options:
        return False
    steps = located(options[TILE_THREAD]).depth()
    return any("levels" in step.words for step in steps)
