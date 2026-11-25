"""The indirect model's files: the elements' file, the card's matrix folder and its
README, written and read."""

import json
from pathlib import Path

import numpy as np

from prism_reference.indirect.hmatrix.cluster import UNIT
from prism_reference.scene.public.table import is_view, public_dir, views

F = np.float32
_MODELS = {}


def model_path(name, data):
    """<public>/<scene>_indirect.npz (a view's: its scene's)."""
    if is_view(name):
        name = views()[name][0]
    return public_dir(data) / f"{name}_indirect.npz"


def transport_dir(name, data):
    """<public>/<scene>_transport/, the card's matrix files."""
    return public_dir(data) / f"{name}_transport"


def load_model(path):
    """The elements, transfer rows and field of an indirect file and its matrix files
    (weights read from the file), kept per path."""
    path = str(path)
    if path not in _MODELS:
        with np.load(path) as f:
            model = {k: f[k] for k in f.files}
        folder = Path(path).with_name(
            Path(path).name.replace("_indirect.npz", "_transport")
        )
        with np.load(folder / "blocks.npz") as f:
            model["blocks"] = {k: f[k] for k in f.files}
        model["weights"] = np.fromfile(folder / "weights.f32", dtype=F)
        _MODELS[path] = model
    return _MODELS[path]


def write(name, data, model, result, source, counts, samples):
    """The files: the indirect file (elements in the matrix's order, transfer rows,
    field) and the card's folder (blocks.npz, weights.f32, x, y_*, perm.npy, README)."""
    folder = transport_dir(name, data)
    folder.mkdir(parents=True, exist_ok=True)
    blocks, weights = model["blocks"], model["weights"]
    np.savez(folder / "blocks.npz", **blocks)
    weights.tofile(folder / "weights.f32")
    for key, value in result.items():
        np.save(folder / f"{key}.npy", value.astype(F))
    perm = np.where(source >= 0, samples[np.maximum(source, 0)], -1).astype(np.int32)
    np.save(folder / "perm.npy", perm)
    (folder / "README.md").write_text(transport_readme(name, counts, len(weights)))
    keep = {k: v for k, v in model.items() if k not in ("blocks", "weights", "cache")}
    out = model_path(name, data)
    np.savez(out, **keep, counts=json.dumps(counts))
    sizes = {p.name: p.stat().st_size for p in sorted(folder.iterdir())}
    counts["bytes"] = {out.name: out.stat().st_size} | sizes
    np.savez(out, **keep, counts=json.dumps(counts))


def transport_readme(name, counts, numbers):
    """The card folder's README: what the files hold and the apply that reproduces
    y_float.npy."""
    return TRANSPORT_README.format(
        name=name,
        elements=counts["elements"],
        units=counts["elements"] // UNIT,
        kept=counts["kept"],
        blocks=counts["blocks"],
        low_rank=counts["blocks_low_rank"],
        dense=counts["blocks"] - counts["blocks_low_rank"],
        numbers=numbers,
        tiles=counts["tiles"],
        tiles_dense=counts["tiles_dense"],
        tiles_low_rank=counts["tiles_low_rank"],
    )


TRANSPORT_README = """# {name}: the light-transport matrix in the card's layout

Written by `python scripts/data/public_scenes.py indirect {name}`
(prism_reference.indirect; the definition: docs/internals/reference/indirect.md). The
card computes
`y = M x`: `M = pi F`, F the elements' form factor with visibility and the near-field
clamp, so `y` is each element's bounced irradiance for the outgoing light `x`.
Tolerance 1e-2 (of each block's largest singular value), admissibility separation >= 1,
no scaling (every `scale` is 1.0).

## Elements

- N = {elements:,} = {units:,} units of 32: the {kept:,} kept elements and zero-area
  copies (their rows and columns of M are 0, their x is 0). Order: the cluster tree,
  every cluster whole 32-element units, leaves of at most 256 elements; the same order
  as the elements of `{name}_indirect.npz`.
- `perm.npy` (N,) int32: each position's sample number k (element k of the area
  sampling); -1 for a copy.
- `x.npy` (N, 3) float32: L0 of the scene's own lights, RGB. `y_exact.npy`: the dense
  apply (every entry of M, float64 sums). `y_float.npy`: the apply below from these
  files, float32, bit for bit. `y_q8.npy`: the card's numbers emulated: every stored
  number bfp8_b (host encode: one exponent for each 16 consecutive numbers of a stored
  row), x's and t's rows bfloat16 as the LEFT operand at HiFi4, float32 sums.

## Stored TRANSPOSED: the card's product is y_row = x_row @ W

- dense block of M rows `row0:row1` (receivers, m = row1 - row0) and columns `col0:col1`
  (sources, n = col1 - col0): stored as `Wt` = n x m, row-major, at `offset_a`.
- low-rank block `M_block = U V^T`: `V` (n x kp) row-major at `offset_a`, then `U^T`
  (kp x m) at `offset_b = offset_a + n * kp`; kp = 32 ceil(k / 32), zero padded; each
  carries sigma^(1/2) of the block's SVD.
- m, n and kp are multiples of 32: every stored matrix is whole 32 x 32 tiles, plain
  row-major in the file; every block starts at a multiple of 32 numbers.

## blocks.npz ({blocks:,} blocks: {low_rank:,} low rank, {dense:,} dense)

| key | type | meaning |
| --- | --- | --- |
| `row0`, `row1` | int32 | rows of M (receivers), multiples of 32 |
| `col0`, `col1` | int32 | columns of M (sources), multiples of 32 |
| `kind` | int8 | 0 dense, 1 low rank |
| `rank` | int32 | low rank: k (0 for dense) |
| `rank_padded` | int32 | low rank: kp (0 for dense) |
| `offset_a` | int64 | in float32 numbers into `weights.f32`: the dense `Wt`, or `V` |
| `offset_b` | int64 | low rank: `U^T` (dense: the end of its block, unused) |
| `scale` | float32 | multiply the block's product by it (all 1.0) |
| `near` | bool | a leaf x leaf near block (dense) |

## weights.f32 ({numbers:,} float32, little endian, no header)

Blocks in the order of `blocks.npz`. Tiles in all: {tiles:,} (dense {tiles_dense:,}; low
rank {tiles_low_rank:,}).

## Apply (reproduces y_float.npy exactly)

```python
import numpy as np
b = np.load("blocks.npz")
W = np.fromfile("weights.f32", np.float32)
x = np.load("x.npy")
y = np.zeros_like(x)
keys = ("row0", "row1", "col0", "col1", "kind", "rank_padded", "offset_a", "offset_b")
for r0, r1, c0, c1, kd, kp, oa, ob, s in zip(*(b[k] for k in keys + ("scale",))):
    m, n, xr = r1 - r0, c1 - c0, x[c0:c1].T
    if kd == 0:
        y[r0:r1] += ((xr @ W[oa : oa + n * m].reshape(n, m)) * s).T
    else:
        t = xr @ W[oa : oa + n * kp].reshape(n, kp)
        y[r0:r1] += ((t @ W[ob : ob + kp * m].reshape(kp, m)) * s).T
print("max |y - y_float| =", np.abs(y - np.load("y_float.npy")).max())
```
"""
