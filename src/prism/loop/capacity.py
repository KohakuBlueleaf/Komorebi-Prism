"""The capacity a loop loads: the hosts' needs for a size, the capacity that holds them,
whether a loaded one covers them, and a refusal with its numbers passed on."""

from prism.core.capacity import Capacity, step_of
from prism.core.implementation import hosted


class CapacityRefused(ValueError):
    """A load for a frame `size` at the capacity `held` refused: the refusal's own
    message, with its numbers, after the size and capacity."""

    def __init__(self, size, held, error):
        width, height = size
        super().__init__(
            f"a load for {width} x {height} at {held.tiles} tiles"
            f"{' (wide)' if held.wide else ''} refused: {error}"
        )
        self.size, self.held, self.error = tuple(size), held, error


def needs(hosts, size):
    """Each host's need (a Capacity) for a frame of `size`, those that have one."""
    out = [hosted(host, "need")(tuple(size)) for host in hosts]
    return [need for need in out if need is not None]


def held_of(asked, at_least=None):
    """The capacity that holds every need of `asked`: their most tiles to its step,
    wide when one is; at least `at_least` (a capacity never shrinks); None for none."""
    if not asked and at_least is None:
        return None
    tiles = step_of(max(need.tiles for need in asked)) if asked else 0
    wide = any(need.wide for need in asked)
    if at_least is not None:
        tiles, wide = max(tiles, at_least.tiles), wide or at_least.wide
    return Capacity(tiles, wide)


def covered(held, asked):
    """True when the capacity `held` holds every need of `asked` (covers' test)."""
    if held is None:
        return not asked
    return all(
        need.tiles <= held.tiles and (held.wide or not need.wide) for need in asked
    )


def reload_to(held, hosts, size):
    """The capacity to load again for a frame of `size`: None when `held` covers the
    hosts' needs, else the one that holds them and `held`."""
    asked = needs(hosts, size)
    return None if covered(held, asked) else held_of(asked, held)
