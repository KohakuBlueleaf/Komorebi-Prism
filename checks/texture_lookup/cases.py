"""The cases of the texture lookups: the present lookup against `fetch`, constants,
texel centres, levels, stripes under an anisotropic footprint, wrapping, weights, the
derivatives of planes and the pages of taps."""

import numpy as np

from checks.surface.record import same
from prism_reference.material import lookup
from prism_reference.material.access import PAGE, texture_firsts
from prism_reference.material.texture import TEXEL_UNIT, fetch, mip_level
from prism_reference.scene.public.textures import halve

ALL = ("nearest", "bilinear", "trilinear", "anisotropic")


def textures(images):
    """The card's texture data (`texels`, `mip`, `levels`) of RGBA8 images, each with
    its chain of 2 x 2 boxes down to 1 x 1."""
    blocks, rows, levels, offset = [], [], [], 0
    for image in images:
        chain = [np.asarray(image, np.uint8)]
        while max(chain[-1].shape[:2]) > 1:
            chain.append(halve(chain[-1]))
        entry = np.zeros((11, 3), np.int64)
        for level, part in enumerate(chain):
            entry[level] = offset, part.shape[1], part.shape[0]
            blocks.append(part.reshape(-1))
            offset += part.size
        rows.append(entry)
        levels.append(len(chain))
    return {
        "texels": np.concatenate(blocks),
        "mip": np.stack(rows),
        "levels": np.array(levels, np.int32),
    }


def grey(values):
    """RGBA8 (H, W, 4) of grey bytes (H, W), alpha 255."""
    g = np.asarray(values, np.uint8)
    return np.stack([g, g, g, np.full_like(g, 255)], -1)


def footprints(rng, count, spread=(-4, 1)):
    """Random uv derivatives (count, 2) along x and y over several magnitudes."""
    scale = 10 ** rng.uniform(*spread, size=(count, 1))
    return rng.normal(size=(count, 2)) * scale, rng.normal(size=(count, 2)) * scale


def present_case(rng):
    """The "triangle" mode is `texture.fetch` at the given level, byte for byte."""
    images = [
        rng.integers(0, 256, (h, w, 4)) for h, w in ((37, 53), (64, 64), (5, 300))
    ]
    data = textures(images)
    count = 4096
    tex = rng.integers(0, 3, count)
    level = rng.integers(0, data["levels"][tex])
    u = rng.uniform(-3, 3, count).astype(np.float32)
    v = rng.uniform(-3, 3, count).astype(np.float32)
    dx, dy = footprints(rng, count)
    found = lookup.taps(data, tex, u, v, dx, dy, "triangle", level)
    got = lookup.gather(data, tex, found, TEXEL_UNIT)
    want = fetch(data, tex, level, u, v).astype(np.float32) / 255
    same("present equals fetch", got, want, 1e-6)


def constant_case(rng):
    """A constant texture gives the constant by every mode at every footprint."""
    data = textures([grey(np.full((37, 53), 200))])
    count = 1024
    tex = np.zeros(count, np.int64)
    uv = rng.uniform(-3, 3, (count, 2))
    dx, dy = footprints(rng, count)
    for mode in ALL:
        got = lookup.lookup(
            data, tex, uv[:, 0], uv[:, 1], dx, dy, mode, None, TEXEL_UNIT
        )
        same(f"constant {mode}", got[:, 0], np.full(count, 200 / 255), 1e-6)


def centre_case(rng):
    """At a texel's centre with a footprint of one texel, bilinear, trilinear and
    anisotropic give that texel of level 0."""
    image = rng.integers(0, 256, (16, 32))
    data = textures([grey(image)])
    y, x = np.meshgrid(np.arange(16), np.arange(32), indexing="ij")
    x, y = x.ravel(), y.ravel()
    u, v = (x + 0.5) / 32, 1 - (y + 0.5) / 16
    tex = np.zeros(len(x), np.int64)
    dx = np.tile([[1 / 32, 0.0]], (len(x), 1))
    dy = np.tile([[0.0, 1 / 16]], (len(x), 1))
    for mode in ("bilinear", "trilinear", "anisotropic"):
        got = lookup.lookup(data, tex, u, v, dx, dy, mode, None, TEXEL_UNIT)[:, 0]
        same(f"texel centre {mode}", got, image[y, x] / 255, 1e-6)


def level_case(rng):
    """Trilinear at an integer lod is bilinear at that level; halfway it is the mean
    of the two levels' bilinear values."""
    data = textures([grey(rng.integers(0, 256, (64, 64)))])
    count = 512
    tex = np.zeros(count, np.int64)
    u, v = rng.uniform(0, 1, count), rng.uniform(0, 1, count)
    for k in range(5):
        level = np.full(count, k)
        one = lookup.gather(data, tex, lookup.bilinear_taps(data, tex, level, u, v))
        two = lookup.gather(data, tex, lookup.bilinear_taps(data, tex, level + 1, u, v))
        at = lookup.gather(data, tex, lookup.trilinear_taps(data, tex, level, u, v))
        mid = lookup.trilinear_taps(data, tex, level + 0.5, u, v)
        same(f"trilinear lod {k}", at, one, 1e-6)
        same(
            f"trilinear lod {k}.5", lookup.gather(data, tex, mid), (one + two) / 2, 1e-5
        )


def stripes_case():
    """Rows alternating 0 and 255 under a footprint of 8 texels across the rows' run
    and 1 down: anisotropic keeps each row (8 lookups, each on a texel's centre),
    trilinear (lod 3) gives their mean."""
    rows = np.where(np.arange(64) % 2 == 0, 0, 255)
    data = textures([grey(np.repeat(rows[:, None], 64, 1))])
    y = np.arange(64)
    tex = np.zeros(64, np.int64)
    u, v = np.full(64, 0.5), 1 - (y + 0.5) / 64
    dx = np.tile([[8 / 64, 0.0]], (64, 1))
    dy = np.tile([[0.0, 1 / 64]], (64, 1))
    aniso = lookup.lookup(data, tex, u, v, dx, dy, "anisotropic", None, TEXEL_UNIT)
    same("stripes anisotropic keeps rows", aniso[:, 0], rows / 255, 1e-6)
    tri = lookup.lookup(data, tex, u, v, dx, dy, "trilinear", None, TEXEL_UNIT)
    same("stripes trilinear mean", tri[:, 0], np.full(64, 0.5), 1 / 255)
    found = lookup.taps(data, tex, u, v, dx, dy, "anisotropic")
    same("stripes anisotropic taps", found[3].shape[1], 8 * lookup.MOST_TAPS)
    same("stripes anisotropic reads", lookup.reads(found), np.full(64, 8))


def wrap_case():
    """Bilinear at u = 0 on a texel row's centre blends its last and first texel."""
    data = textures([grey([[10, 20, 30, 40]])])
    tex = np.zeros(1, np.int64)
    found = lookup.bilinear_taps(data, tex, np.zeros(1, np.int64), [0.0], [0.5])
    same("wrap", lookup.gather(data, tex, found, TEXEL_UNIT)[:, 0], [25 / 255], 1e-6)


def weights_case(rng):
    """Every mode's weights are at least 0 and sum to 1."""
    data = textures([grey(rng.integers(0, 256, (40, 70)))])
    count = 2048
    tex = np.zeros(count, np.int64)
    uv = rng.uniform(-2, 2, (count, 2))
    dx, dy = footprints(rng, count, (-4, 0))
    for mode in ALL:
        weight = lookup.taps(data, tex, uv[:, 0], uv[:, 1], dx, dy, mode)[3]
        same(f"weights {mode}", weight.sum(1), np.ones(count), 1e-9)
        same(f"weights {mode} positive", (weight >= 0).all(), True)


def derivative_case(rng):
    """`plane_derivatives` against central differences of value / (1/z) planes."""
    count = 256
    planes = rng.normal(size=(count, 3, 2))
    w_plane = np.stack([rng.normal(0, 1e-3, count), rng.normal(0, 1e-3, count)], 1)
    w_plane = np.concatenate([w_plane, rng.uniform(0.5, 2, (count, 1))], 1)
    px, py = rng.uniform(0, 100, count), rng.uniform(0, 100, count)
    value, dx, dy = lookup.plane_derivatives(planes, w_plane, px, py)
    step = 1e-4

    def at(x, y):
        return lookup.plane_derivatives(planes, w_plane, x, y)[0]

    same("value", value, at(px, py), 0)
    same("d/dx", dx, (at(px + step, py) - at(px - step, py)) / (2 * step), 1e-6)
    same("d/dy", dy, (at(px, py + step) - at(px, py - step)) / (2 * step), 1e-6)


def pages_case(rng):
    """A tap's page is its level's first page plus its 32 x 32 block; `triangle_level`
    is `mip_level` of the area in level-0 texels."""
    data = textures([grey(rng.integers(0, 256, (100, 70))), grey(np.zeros((8, 8)))])
    firsts = texture_firsts(data)
    count = 512
    tex = rng.integers(0, 2, count)
    level = rng.integers(0, data["levels"][tex])
    u, v = rng.uniform(0, 1, count), rng.uniform(0, 1, count)
    found = lookup.bilinear_taps(data, tex, level, u, v)
    page = lookup.pages(tex, found, firsts)
    _, x, y, _ = found
    first, across = firsts[tex, level, 0][:, None], firsts[tex, level, 1][:, None]
    same("pages", page, first + (y // PAGE) * across + x // PAGE)
    uv_area, screen = rng.uniform(0, 1, count), rng.uniform(0.1, 100, count)
    width, height = data["mip"][tex, 0, 1], data["mip"][tex, 0, 2]
    texels = (uv_area.astype(np.float32) * (width * height).astype(np.float32)).astype(
        np.float32
    )
    want = mip_level(texels, screen.astype(np.float32), data["levels"][tex])
    same("triangle level", lookup.triangle_level(data, tex, uv_area, screen), want)


def lookup_cases():
    """Every case."""
    rng = np.random.default_rng(7)
    present_case(rng)
    constant_case(rng)
    centre_case(rng)
    level_case(rng)
    stripes_case()
    wrap_case()
    weights_case(rng)
    derivative_case(rng)
    pages_case(rng)
