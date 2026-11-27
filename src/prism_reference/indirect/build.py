"""Building a scene's indirect model: elements, the dense form factors, the cluster
order, the hierarchical matrix, transfer rows, the field and the checks, then the files.
"""

import time

import numpy as np

from prism_reference.direct.lights import load
from prism_reference.direct.prepare import scene_tree
from prism_reference.indirect.elements import (
    ELEMENTS,
    PROBE_DEAD,
    padded,
    probe,
    sample_elements,
    subset,
)
from prism_reference.indirect.field.build import build_field, field_counts, sight
from prism_reference.indirect.files import write
from prism_reference.indirect.form_factors import dense_form_factors
from prism_reference.indirect.hmatrix.apply import apply
from prism_reference.indirect.hmatrix.card import card_apply
from prism_reference.indirect.hmatrix.cluster import UNIT, cluster_tree
from prism_reference.indirect.hmatrix.compress import hierarchical, matrix_counts
from prism_reference.indirect.light import element_light
from prism_reference.indirect.sky import transfer
from prism_reference.material.kinds import TRANSPARENT
from prism_reference.scene.public.materials import load_materials
from prism_reference.scene.public.mesh import load_mesh
from prism_reference.scene.public.table import public_dir, table
from prism_reference.scene.public.views import EPS_SCALE
from prism_reference.trace.tree import triangles

F = np.float32


def open_tree(mesh, materials, tree=None):
    """The ray tree with glass open (over the triangles that are not `transparent`,
    leaf_tri naming the scene's triangles); `tree` is kept when there is no glass."""
    glass = materials["kind"][materials["material"]] == TRANSPARENT
    if tree is None or glass.any():
        tree = triangles(mesh, np.nonzero(~glass)[0])
    return {k: np.ascontiguousarray(v) for k, v in tree.items()}


def build(name, data, log=print):
    """Writes <public>/<scene>_indirect.npz and the card's files in <scene>_transport/;
    the dense F is kept in <scene>_indirect_work/ to go on from. Returns the counts."""
    entry = table()[name]["lighting"]
    mesh, _ = load_mesh(name, data)
    materials, _ = load_materials(name, data)
    lights = load(name, data)
    times, counts, clock = {}, {}, [time.perf_counter()]

    def step(label):
        now = time.perf_counter()
        times[label] = round(now - clock[0], 1)
        clock[0] = now
        log(f"{name}: {label} {times[label]} s")

    tree = open_tree(mesh, materials, scene_tree(name, data, mesh))
    p = mesh["positions"].astype(np.float64)
    eps = EPS_SCALE * float(np.linalg.norm(p.max(0) - p.min(0)))
    step("tree")
    sampled, spacing = sample_elements(mesh, materials, entry.get("elements", ELEMENTS))
    step("sample")
    escape, near = probe(tree, sampled, eps)
    live = subset(sampled, escape + near <= PROBE_DEAD)
    counts |= {
        "sampled": len(escape),
        "probe_dead": int((escape + near > PROBE_DEAD).sum()),
    }
    step("probe")
    work = public_dir(data) / f"{name}_indirect_work"
    dense, rays = dense_form_factors(tree, live, eps, work, log)
    counts["form_factor_rays"] = rays
    step("form_factors")
    row_sum = np.concatenate(
        [dense[s : s + 4096].sum(1) for s in range(0, len(dense), 4096)]
    )
    keep = np.nonzero(row_sum > 0)[0]
    counts["empty_rows"] = int(len(row_sum) - len(keep))
    count = -(-len(keep) // UNIT) * UNIT
    elements, real = padded(subset(live, keep), count)
    cluster = cluster_tree(elements["position"])
    perm = cluster["perm"]
    elements, real = subset(elements, perm), real[perm]
    source = np.where(real, keep[np.minimum(perm, len(keep) - 1)], -1)
    matrix = np.zeros((count, count), F)
    columns = np.nonzero(real)[0]
    for s in range(0, count, 2048):
        rows = np.arange(s, min(count, s + 2048))
        rows = rows[real[rows]]
        part = np.asarray(dense[np.sort(source[rows])])
        part = part[np.argsort(np.argsort(source[rows]))]
        matrix[rows[:, None], columns[None, :]] = part[:, source[columns]] * F(np.pi)
    del dense
    counts |= {
        "kept": int(real.sum()),
        "elements": count,
        "spacing": spacing,
        "eps": eps,
    }
    step("order")
    blocks, weights = hierarchical(matrix, cluster, log=log)
    step("hierarchical")
    model = elements | {"real": real, "blocks": blocks, "weights": weights}
    model["transfer"] = np.where(real[:, None], transfer(tree, elements, eps), F(0))
    step("transfer")
    position, normal = elements["position"][real], elements["normal"][real]
    seen = sight(tree, eps, position, normal)
    model |= build_field(position, normal, spacing, seen=seen)
    model["field_columns"] = np.nonzero(real)[0][model["field_columns"]].astype(
        np.int32
    )
    step("field")
    x = element_light(lights, model)["l0"]
    exact = np.concatenate(
        [matrix[s : s + 2048].astype(np.float64) @ x for s in range(0, count, 2048)]
    )
    del matrix
    result = {
        "x": x,
        "y_exact": exact.astype(F),
        "y_float": apply(blocks, weights, x),
        "y_q8": card_apply(blocks, weights, x),
    }
    step("checks")
    counts |= matrix_counts(blocks) | field_counts(model)
    counts["seconds"] = times
    write(name, data, model, result, source, counts, live["sample"])
    step("write")
    counts["seconds"] = times
    return counts
