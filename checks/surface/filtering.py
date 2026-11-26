"""The cases of the texture filter: constants, a checker, an anisotropic ramp, the wrap
modes and the sRGB transfer of level 0."""

import numpy as np

from checks.surface.record import same
from prism_reference.material.filter import (
    COLOUR,
    DATA,
    Texture,
    nearest,
    sample,
    trilinear,
)
from prism_reference.scene.description.types import Sampler

FILTERS = {"nearest": nearest, "trilinear": trilinear, "anisotropic": sample}


def pixels(values):
    """uint8 (H, W, 4) from grey bytes (H, W), alpha 255."""
    grey = np.asarray(values, dtype=np.uint8)
    return np.stack([grey, grey, grey, np.full_like(grey, 255)], axis=-1)


def srgb_decoded(byte):
    """The standard sRGB transfer undone, written out here."""
    c = byte / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def constant_case(rng):
    """A constant texture samples constant at every footprint, by every filter."""
    texture = Texture(pixels(np.full((37, 53), 200)), DATA)
    count = 512
    uv = rng.uniform(-3, 3, size=(count, 2))
    dx = rng.normal(size=(count, 2)) * 10 ** rng.uniform(-4, 1, size=(count, 1))
    dy = rng.normal(size=(count, 2)) * 10 ** rng.uniform(-4, 1, size=(count, 1))
    for name, f in FILTERS.items():
        got = f(texture, None, uv, dx, dy)[:, 0]
        same(f"constant {name}", got, np.full(count, 200 / 255), 1e-6)


def checker_case():
    """A 2 x 2 checker: a footprint of one texel at a texel's centre is the texel; one of
    the whole texture is the mean."""
    texture = Texture(pixels([[0, 255], [255, 0]]), DATA)
    centre = np.array([[0.25, 0.25], [0.75, 0.25]])
    texel = (np.array([[0.5, 0.0]] * 2), np.array([[0.0, 0.5]] * 2))
    whole = (np.array([[1.0, 0.0]] * 2), np.array([[0.0, 1.0]] * 2))
    for name in ("trilinear", "anisotropic"):
        f = FILTERS[name]
        same(
            f"checker one texel {name}", f(texture, None, centre, *texel)[:, 0], [0, 1]
        )
        same(f"checker whole {name}", f(texture, None, centre, *whole)[:, 0], [0.5] * 2)


def ramp_case():
    """A horizontal ramp under a footprint of 8 texels along x and 1 along y: the
    anisotropic value is the ramp's mean over the footprint within 1 / 255."""
    width, height = 256, 64
    ramp = np.tile(np.arange(width, dtype=np.uint8), (height, 1))
    texture = Texture(pixels(ramp), DATA)
    centres = np.array([40.0, 100.0, 171.5, 220.25])
    uv = np.stack([centres / width, np.full(4, 0.5)], axis=1)
    dx = np.tile([8.0 / width, 0.0], (4, 1))
    dy = np.tile([0.0, 1.0 / height], (4, 1))
    got = sample(texture, None, uv, dx, dy)[:, 0]
    x = centres[:, None] + np.linspace(-4, 4, 4001)[None, :]
    want = np.interp(x - 0.5, np.arange(width), np.arange(width) / 255.0).mean(axis=1)
    same("ramp anisotropic ratio 8", got, want, 1 / 255)


def wrap_case():
    """A 4 x 1 texture sampled past both edges by each wrap mode."""
    values = np.array([0, 85, 170, 255])
    texture = Texture(pixels([values]), DATA)
    t = values / 255.0
    uv = np.array([[-0.05, 0.5], [1.05, 0.5]])
    small = np.array([[1e-4, 0.0]] * 2), np.array([[0.0, 1e-4]] * 2)
    # x = u 4 - 0.5: -0.7 and 3.7; the bilinear pair and the weight of the second.
    want = {
        "REPEAT": ([0.7 * t[3] + 0.3 * t[0], 0.3 * t[3] + 0.7 * t[0]], [t[3], t[0]]),
        "CLAMP": ([t[0], t[3]], [t[0], t[3]]),
        "MIRROR": ([t[0], t[3]], [t[0], t[3]]),
    }
    for mode, (linear, near) in want.items():
        sampler = Sampler(wrap_s=mode, wrap_t=mode)
        got = trilinear(texture, sampler, uv, *small)[:, 0]
        same(f"wrap {mode} trilinear", got, linear, 1e-6)
        same(f"wrap {mode} nearest", nearest(texture, sampler, uv)[:, 0], near, 1e-6)


def srgb_case():
    """Level 0 of a colour texture is the sRGB transfer undone; alpha stays bytes / 255."""
    every = np.arange(256, dtype=np.uint8).reshape(16, 16)
    texture = Texture(pixels(every), COLOUR)
    same("srgb level 0", texture.levels[0][:, :, 0], srgb_decoded(every), 1e-6)
    same("srgb alpha", texture.levels[0][:, :, 3], np.ones((16, 16)), 1e-6)
    same("srgb levels", len(texture.levels), 5)


def filter_cases():
    """Every case of the filter."""
    constant_case(np.random.default_rng(3))
    checker_case()
    ramp_case()
    wrap_case()
    srgb_case()
