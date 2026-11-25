"""The frame capacity a load is sized for: the tiles every per-tile table holds, in steps."""

from typing import NamedTuple

from prism.core.headers import INCLUDE, constexpr
from prism_reference.scene.frame import HEIGHT, WIDTH, frame_grid

GRID = constexpr(INCLUDE / "grid.h")
TILE_ROWS = 32  # a capacity is a whole number of these tiles
# the capacity's steps (step_of) start from the default grid's tiles
STEP_BASE = GRID["kGridDefault"] ** 2


class Capacity(NamedTuple):
    """What a load sizes tables, tensors and regions from: `tiles` (TILE_ROWS each);
    `wide`, 32-bit box words past the narrow grid; `recount`, the heavy tiles'
    histograms counted again; `cores`, the fill cores (None: host-stepped)."""

    tiles: int
    wide: bool
    recount: bool = False
    cores: int | None = None


def narrow(grid):
    """True when the grid (TX, TY) fits the narrow words."""
    across, down = grid
    return across <= GRID["kNarrowAcross"] and down <= GRID["kNarrowDown"]


def step_of(tiles):
    """The least step of at least `tiles`: STEP_BASE times 1, 1.5, 2, 3, 4, 6, 8, ...
    (2^k and 1.5 x 2^k)."""
    step = STEP_BASE
    while step < tiles:
        if 3 * step // 2 >= tiles:
            return 3 * step // 2
        step *= 2
    return step


def need(sizes, lit=False):
    """The tiles a load must hold to render every frame size (W, H) of `sizes`: their
    most tiles (lit: at least the sun's quadrant of the default grid) rounded up to
    TILE_ROWS."""
    tiles = max(across * down for across, down in map(frame_grid, sizes))
    if lit:
        tiles = max(tiles, GRID["kGridDefault"] ** 2)
    return -(-tiles // TILE_ROWS) * TILE_ROWS


def capacity(sizes, lit=False, at_least=None):
    """The capacity that renders every frame size (W, H) of `sizes`: their need
    rounded up to its step; wide when one's grid passes the narrow words; at least
    `at_least` (a Capacity) when given: a capacity never shrinks."""
    tiles = step_of(need(sizes, lit))
    wide = not all(narrow(frame_grid(size)) for size in sizes)
    if at_least is not None:
        tiles, wide = max(tiles, at_least.tiles), wide or at_least.wide
        return Capacity(tiles, wide, at_least.recount, at_least.cores)
    return Capacity(tiles, wide)


def covers(held, size, lit=False):
    """True when the capacity `held` renders a frame of size (W, H): its need, not its
    step."""
    wide = not narrow(frame_grid(size))
    return need([size], lit) <= held.tiles and (held.wide or not wide)


def default_capacity():
    """The default frame's capacity (WIDTH x HEIGHT)."""
    return capacity([(WIDTH, HEIGHT)])
