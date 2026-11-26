"""The metallic-roughness model as functions of float64 arrays: Lambert diffuse, GGX
distribution, height-correlated Smith visibility, Schlick Fresnel."""

import numpy as np

DIELECTRIC_F0 = 0.04
LEAST_A = 1e-3**2  # the floor on a = roughness^2 in D and V


def f0(base, metallic):
    """The specular colour at normal incidence: 0.04 (1 - metallic) + base metallic."""
    metallic = np.asarray(metallic, dtype=np.float64)[..., None]
    return DIELECTRIC_F0 * (1.0 - metallic) + np.asarray(base, np.float64) * metallic


def diffuse(base, metallic):
    """The diffuse lobe: base (1 - metallic) / pi."""
    metallic = np.asarray(metallic, dtype=np.float64)[..., None]
    return np.asarray(base, np.float64) * (1.0 - metallic) / np.pi


def d_ggx(n_h, a):
    """The GGX distribution of half vectors at cos n_h, width a = roughness^2."""
    a2 = np.maximum(a, LEAST_A) ** 2
    k = n_h * n_h * (a2 - 1.0) + 1.0
    return a2 / (np.pi * k * k)


def v_smith(n_l, n_v, a):
    """The height-correlated Smith visibility G / (4 n_l n_v)."""
    a2 = np.maximum(a, LEAST_A) ** 2
    lam_v = n_l * np.sqrt(n_v * n_v * (1.0 - a2) + a2)
    lam_l = n_v * np.sqrt(n_l * n_l * (1.0 - a2) + a2)
    return 0.5 / (lam_v + lam_l)


def fresnel(f0_colour, v_h):
    """Schlick's Fresnel: f0 + (1 - f0) (1 - v_h)^5, per colour channel."""
    x = (1.0 - np.asarray(v_h, dtype=np.float64)) ** 5
    return f0_colour + (1.0 - f0_colour) * x[..., None]


def dot(a, b):
    """The dot product over the last axis."""
    return np.sum(a * b, axis=-1)


def brdf(base, metallic, roughness, n, v, l):
    """diffuse (1 - F) + D V F for unit n, v (to the eye) and l (to the light), (..., 3);
    0 where n_l or n_v is not above 0."""
    n_l, n_v = dot(n, l), dot(n, v)
    half = v + l
    half = half / np.linalg.norm(half, axis=-1, keepdims=True)
    n_h, v_h = dot(n, half), dot(v, half)
    a = np.asarray(roughness, dtype=np.float64) ** 2
    front = (n_l > 0) & (n_v > 0)
    nl, nv = np.where(front, n_l, 1.0), np.where(front, n_v, 1.0)
    f = fresnel(f0(base, metallic), v_h)
    specular = (d_ggx(n_h, a) * v_smith(nl, nv, a))[..., None] * f
    value = diffuse(base, metallic) * (1.0 - f) + specular
    return np.where(front[..., None], value, 0.0)
