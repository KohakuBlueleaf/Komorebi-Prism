"""A mesh's products kept in the cache by what they are made of: the digest of its
positions and indices, the product's name and its version; a kept file of another key is
never read."""

import os

import numpy as np

from prism_common.digest import Digest
from prism_common.paths import cache_root

FOLDER = "mesh"  # under the cache root
KEY_HEX = 32  # hex digits of the mesh's digest in a file's name
REMEMBERED = 8  # meshes whose digest is remembered by their arrays

_DIGESTS = []  # (positions, indices, digest) of the meshes digested last


def mesh_digest(positions, indices):
    """The digest of a mesh's positions and indices (their dtype, shape and bytes),
    remembered for the same two arrays."""
    for p, i, digest in _DIGESTS:
        if p is positions and i is indices:
            return digest
    digest = Digest()
    for name, value in (("positions", positions), ("indices", indices)):
        a = np.ascontiguousarray(value)
        digest.update(f"{name}{a.dtype}{a.shape}".encode())
        digest.update(a.reshape(-1).view(np.uint8))
    out = digest.hexdigest()[:KEY_HEX]
    _DIGESTS[:] = _DIGESTS[-(REMEMBERED - 1) :] + [(positions, indices, out)]
    return out


def kept(positions, indices, product, version, make):
    """The array `make()` gives for the mesh: read when kept under the mesh's digest,
    `product` and `version`, else made and kept (a temporary name, then renamed)."""
    key = mesh_digest(positions, indices)
    path = cache_root() / FOLDER / f"{key}_{product}_v{version}.npy"
    if path.exists():
        return np.load(path)
    out = make()
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    with open(part, "wb") as handle:
        np.save(handle, out)
    part.replace(path)
    return out
