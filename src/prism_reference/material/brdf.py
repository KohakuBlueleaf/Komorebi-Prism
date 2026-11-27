"""The metallic-roughness model as functions of float64 arrays: Lambert diffuse, GGX
distribution, height-correlated Smith visibility, Schlick Fresnel; the dielectric f0 of
ior and specular colour, the lobe's albedo, multiple scattering, the valid normal; the
sheen's Charlie distribution, its visibility and albedo scaling."""

import numpy as np

DIELECTRIC_F0 = 0.04
LEAST_A = 1e-3**2  # the floor on a = roughness^2 in D and V
ALBEDO_CELLS = 32  # the albedo tables' cells along cos n_v and along roughness
ALBEDO_SAMPLES = 64  # the stratified samples a side of each cell's integral
LEAST_SHEEN = 0.07**2  # the floor on r = sheen roughness^2 in the Charlie distribution


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


def dielectric_f0(ior, colour=1.0):
    """KHR_materials_ior and _specular: ((ior - 1) / (ior + 1))^2 times the specular
    colour, at most 1."""
    r = (np.asarray(ior, np.float64) - 1.0) / (np.asarray(ior, np.float64) + 1.0)
    return np.minimum((r * r)[..., None] * np.asarray(colour, np.float64), 1.0)


def albedo_tables(cells=ALBEDO_CELLS, samples=ALBEDO_SAMPLES):
    """The single-scattering GGX lobe's directional albedo split by Schlick's terms,
    (A, B) over (cos n_v, roughness) cell centres: albedo = f0 A + f90 B. Fixed
    stratified samples of the distribution of half vectors (deterministic)."""
    mu = (np.arange(cells) + 0.5) / cells
    rough = (np.arange(cells) + 0.5) / cells
    u = (np.arange(samples) + 0.5) / samples
    u1, u2 = (g.ravel() for g in np.meshgrid(u, u, indexing="ij"))
    a = np.maximum(rough**2, np.sqrt(LEAST_A))[None, :, None]
    cos_h = np.sqrt((1.0 - u1) / (1.0 + (a * a - 1.0) * u1))
    sin_h = np.sqrt(np.maximum(1.0 - cos_h * cos_h, 0.0))
    phi = 2.0 * np.pi * u2
    hx, hz = sin_h * np.cos(phi), cos_h
    n_v = mu[:, None, None]
    vx = np.sqrt(1.0 - n_v * n_v)
    v_h = vx * hx + n_v * hz
    n_l = 2.0 * v_h * hz - n_v
    keep = (n_l > 0) & (v_h > 0)
    nl = np.where(keep, n_l, 1.0)
    weight = 4.0 * v_smith(nl, n_v, a) * nl * v_h / hz
    weight = np.where(keep, weight, 0.0)
    schlick = (1.0 - np.clip(v_h, 0.0, 1.0)) ** 5
    total = weight.mean(axis=-1)
    edge = (weight * schlick).mean(axis=-1)
    return total - edge, edge


def table_at(table, n_v, roughness):
    """A table of `albedo_tables` at (cos n_v, roughness), bilinear between cell
    centres, clamped at the edges."""
    cells = table.shape[0]
    x = np.clip(np.asarray(n_v, np.float64) * cells - 0.5, 0.0, cells - 1.0)
    y = np.clip(np.asarray(roughness, np.float64) * cells - 0.5, 0.0, cells - 1.0)
    x0, y0 = np.minimum(x.astype(np.int64), cells - 2), np.minimum(
        y.astype(np.int64), cells - 2
    )
    fx, fy = x - x0, y - y0
    top = table[x0, y0] * (1 - fy) + table[x0, y0 + 1] * fy
    low = table[x0 + 1, y0] * (1 - fy) + table[x0 + 1, y0 + 1] * fy
    return top * (1 - fx) + low * fx


def lobe_albedo(f0_colour, f90, n_v, roughness):
    """The single-scattering lobe's directional albedo f0 A + f90 B, (..., 3)."""
    a, b = ALBEDO
    f90 = np.asarray(f90, np.float64)[..., None]
    return (
        f0_colour * table_at(a, n_v, roughness)[..., None]
        + f90 * table_at(b, n_v, roughness)[..., None]
    )


def multiple_scattering(f0_colour, n_v, roughness):
    """The factor on the single-scattering lobe for the energy its bounces between
    microfacets give back: 1 + f0 (1 - E) / E, E the albedo with F = 1."""
    a, b = ALBEDO
    e = np.maximum(table_at(a + b, n_v, roughness), 1e-6)[..., None]
    return 1.0 + f0_colour * (1.0 - e) / e


def valid_normal(n, ng, v):
    """The shading normal bent toward the geometric one where its mirror direction of
    v would fall under the surface (Cycles' ensure_valid_specular_reflection); rows."""
    r = 2.0 * dot(n, v)[..., None] * n - v
    iz = dot(v, ng)
    threshold = np.minimum(0.9 * iz, 0.01)
    bad = dot(ng, r) < threshold
    if not np.any(bad):
        return n
    x = n - dot(n, ng)[..., None] * ng
    x = x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-300)
    ix = dot(v, x)
    a = np.maximum(ix * ix + iz * iz, 1e-300)
    b = 2.0 * (a + iz * threshold)
    c = (threshold + iz) ** 2
    root = np.sqrt(np.maximum(b * b - 4.0 * a * c, 0.0))
    nz2 = 0.25 * np.where(ix < 0, b + root, b - root) / a
    nz2 = np.clip(nz2, 0.0, 1.0)
    bent = np.sqrt(1.0 - nz2)[..., None] * x + np.sqrt(nz2)[..., None] * ng
    return np.where(bad[..., None], bent, n)


def d_charlie(n_h, roughness):
    """KHR_materials_sheen's Charlie distribution of half vectors, r = roughness^2:
    (2 + 1 / r) sin^(1 / r) / (2 pi)."""
    r = np.maximum(np.asarray(roughness, np.float64) ** 2, LEAST_SHEEN)
    sin2 = np.maximum(1.0 - n_h * n_h, 0.0)
    return (2.0 + 1.0 / r) * sin2 ** (0.5 / r) / (2.0 * np.pi)


def v_neubelt(n_l, n_v):
    """The sheen's visibility 1 / (4 (n_l + n_v - n_l n_v))."""
    return 1.0 / (4.0 * (n_l + n_v - n_l * n_v))


def sheen_table(cells=ALBEDO_CELLS, samples=ALBEDO_SAMPLES):
    """The sheen lobe's directional albedo (white sheen colour) over (cos n_v,
    sheen roughness) cell centres: fixed cosine-weighted directions (deterministic)."""
    mu = (np.arange(cells) + 0.5) / cells
    rough = (np.arange(cells) + 0.5) / cells
    u = (np.arange(samples) + 0.5) / samples
    u1, u2 = (g.ravel() for g in np.meshgrid(u, u, indexing="ij"))
    n_l = np.sqrt(1.0 - u1)
    lx = np.sqrt(u1) * np.cos(2.0 * np.pi * u2)
    n_v = mu[:, None]
    vx = np.sqrt(1.0 - n_v * n_v)
    h_len = np.sqrt(np.maximum(2.0 + 2.0 * (vx * lx + n_v * n_l), 1e-300))
    n_h = (n_v + n_l) / h_len
    value = v_neubelt(n_l, n_v)[:, None, :] * d_charlie(
        n_h[:, None, :], rough[None, :, None]
    )
    return np.pi * value.mean(axis=-1)


def sheen_scale(colour, n_v, n_l, roughness):
    """The layers under the sheen scaled by min(1 - max(colour) E(n_v), 1 - max(colour)
    E(n_l)), E the sheen's albedo (KHR_materials_sheen's albedo scaling)."""
    top = np.max(colour, axis=-1)
    e = np.maximum(table_at(SHEEN, n_v, roughness), table_at(SHEEN, n_l, roughness))
    return 1.0 - top * e


ALBEDO = albedo_tables()
SHEEN = sheen_table()
