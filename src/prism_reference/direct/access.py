"""The light pages LIGHT reads over a frame: per pixel the pages of its shadow map's four
taps (an empty pixel: the background's three channels) and of its field's eight corners,
numbered in one page space from a layout of first pages."""

import numpy as np

from prism_reference.direct.frame import light_layer
from prism_reference.direct.sky import octahedral_texel
from prism_reference.raster.frames import fill_layers, nearer_layer, shade_setup
from prism_reference.raster.setup import world_points

F = np.float32
PAGE = 32  # a light page: 32 x 32 texels of a map
TAPS, CORNERS = 4, 8
NONE = -1  # no page


def light_surface(scene, materials, lights, glass=True):
    """The surface LIGHT lights (H, W) of the padded frame: the masked layer where it is
    nearer and not a hole, else the opaque one; "covered", "position", "normal", and
    the layers (`glass`: with the glass one) and per-triangle setup it was made from."""
    layers = fill_layers(scene, materials, glass)
    corner = {**materials, "light": lights["visibility"][scene["indices"]]}
    prepared = shade_setup(scene, corner)
    variant = {"terms": set(), "smooth": None, "pcf": True}
    opaque, masked = layers[0], layers[1]
    _, _, opaque_parts = light_layer(scene, corner, prepared, opaque, lights, variant)
    _, hole, masked_parts = light_layer(
        scene, corner, prepared, masked, lights, variant
    )
    take = nearer_layer(masked, opaque) & ~hole
    tri = np.where(take, masked["tri"], opaque["tri"])
    depth = np.where(take, masked["depth"], opaque["depth"])
    normal = np.where(take[..., None], masked_parts["normal"], opaque_parts["normal"])
    ys, xs = np.nonzero(tri >= 0)
    px, py = xs.astype(F) + F(0.5), ys.astype(F) + F(0.5)
    position = np.zeros(tri.shape + (3,), dtype=F)
    position[ys, xs] = world_points(scene["camera"], px, py, depth[ys, xs])
    return {
        "covered": tri >= 0,
        "position": position,
        "normal": normal.astype(F),
        "layers": {"opaque": layers[0], "masked": layers[1], "glass": layers[2]},
        "prepared": prepared,
    }


def tap_texels(lights, points, normals):
    """Column and row (n, 4, 2) of the shadow map's 2 x 2 taps at points moved one
    shadow texel along their normals (sun_shadow's filter); NONE outside the map."""
    cam = lights["shadow_camera"]
    side = int(lights["shadow_map"].shape[0])
    q = points + normals * lights["shadow_texel"]
    d = q - cam[0:3]
    xc = (d[:, 0] * cam[3] + d[:, 1] * cam[4]) + d[:, 2] * cam[5]
    yc = (d[:, 0] * cam[6] + d[:, 1] * cam[7]) + d[:, 2] * cam[8]
    zc = (d[:, 0] * cam[9] + d[:, 1] * cam[10]) + d[:, 2] * cam[11]
    w = F(1) / zc
    sx = cam[13] + cam[12] * (xc * w)
    sy = cam[14] - cam[12] * (yc * w)
    x0 = np.floor(sx - F(0.5)).astype(np.int64)
    y0 = np.floor(sy - F(0.5)).astype(np.int64)
    out = np.full((len(points), TAPS, 2), NONE, dtype=np.int64)
    for tap in range(TAPS):
        x, y = x0 + (tap & 1), y0 + (tap >> 1)
        inside = (x >= 0) & (x < side) & (y >= 0) & (y < side)
        out[inside, tap] = np.stack([x[inside], y[inside]], 1)
    return out


def tap_pages(lights, taps, first):
    """Pages (n, 4) of taps (tap_texels), from page `first`, the map in 32 x 32 pages
    row by row; NONE outside the map."""
    across = int(lights["shadow_map"].shape[0]) // PAGE
    page = first + (taps[..., 1] // PAGE) * across + taps[..., 0] // PAGE
    return np.where(taps[..., 0] >= 0, page, NONE)


def background_pages(scene, lights, ys, xs, first):
    """Pages (n, 3) of the background's octahedral texel at pixels (ys, xs), a channel's
    map after the other's, from page `first` (environment_radiance's texel)."""
    cam = scene["camera"]
    sx = (xs.astype(F) + F(0.5) - cam[13]) / cam[12]
    sy = (ys.astype(F) + F(0.5) - cam[14]) / cam[12]
    d = (cam[9:12] + cam[3:6] * sx[:, None]) - cam[6:9] * sy[:, None]
    angle = np.radians(-float(lights["turn"]))
    c, s = F(np.cos(angle)), F(np.sin(angle))
    x, z = d[:, 0], d[:, 2]
    d = np.stack([c * x + s * z, d[:, 1], c * z - s * x], -1)
    side = int(lights["octahedral"].shape[0])
    row, column = octahedral_texel(d, side)
    across = side // PAGE
    page = first + (row // PAGE) * across + column // PAGE
    return page[:, None] + across * across * np.arange(3)[None, :]


def field_cells(model, points, normals):
    """The field lookup's cell (n, 3) of each point: the floor of its grid point at
    P + n h / 2 (lookup's), x, y, z."""
    h, origin = model["field_spacing"], model["field_origin"]
    g = ((points.astype(F) + normals.astype(F) * (F(0.5) * h)) - origin) / h - F(0.5)
    return np.floor(g).astype(np.int64)


def field_corner_voxels(model, points, normals):
    """Voxels (n, 8, 3) around each point's field lookup (the corners of field_cells),
    x, y, z; NONE off the grid."""
    dims = np.asarray(model["field_dims"], dtype=np.int64)
    base = field_cells(model, points, normals)
    out = np.full((len(points), CORNERS, 3), NONE, dtype=np.int64)
    for corner in range(CORNERS):
        voxel = base + np.array([corner & 1, corner >> 1 & 1, corner >> 2])
        inside = ((voxel >= 0) & (voxel < dims)).all(axis=1)
        out[inside, corner] = voxel[inside]
    return out


def field_corner_pages(model, voxels, first, block):
    """Pages (n, 8) of corner voxels (field_corner_voxels), the field in pages of `block`
    (x, y, z) voxels, blocks in x, then z, then y, from page `first`; NONE off the grid.
    """
    dims = np.asarray(model["field_dims"], dtype=np.int64)
    block = np.asarray(block, dtype=np.int64)
    blocks = -(-dims // block)
    b = voxels // block
    page = first + (b[..., 1] * blocks[2] + b[..., 2]) * blocks[0] + b[..., 0]
    return np.where(voxels[..., 0] >= 0, page, NONE)


def light_pages(scene, lights, surface, layout, field_model=None):
    """Per pixel of the padded frame the pages LIGHT reads: "shadow" (H, W, 4) the taps'
    (an empty pixel: the background's three) and "taps" (H, W, 4, 2) their texels;
    with `field_model` "field" (H, W, 8), "voxels" (H, W, 8, 3) and "cells" (H, W, 1,
    3: a cell with a corner on the grid, else NONE). layout: first pages
    "shadow", "octahedral", "field"; "block" the field's."""
    covered = surface["covered"]
    shape = covered.shape
    ys, xs = np.nonzero(covered)
    points, normals = surface["position"][ys, xs], surface["normal"][ys, xs]
    taps = np.full(shape + (TAPS, 2), NONE, dtype=np.int32)
    texels = tap_texels(lights, points, normals)
    taps[ys, xs] = texels
    shadow = np.full(shape + (TAPS,), NONE, dtype=np.int64)
    shadow[ys, xs] = tap_pages(lights, texels, layout["shadow"])
    empty_y, empty_x = np.nonzero(~covered)
    shadow[empty_y, empty_x, :3] = background_pages(
        scene, lights, empty_y, empty_x, layout["octahedral"]
    )
    out = {"shadow": shadow, "taps": taps}
    if field_model is not None:
        voxels = np.full(shape + (CORNERS, 3), NONE, dtype=np.int32)
        corners = field_corner_voxels(field_model, points, normals)
        voxels[ys, xs] = corners
        field = np.full(shape + (CORNERS,), NONE, dtype=np.int64)
        field[ys, xs] = field_corner_pages(
            field_model, corners, layout["field"], layout["block"]
        )
        cells = np.full(shape + (1, 3), NONE, dtype=np.int32)
        reads = (corners[..., 0] >= 0).any(axis=1)
        cells[ys[reads], xs[reads], 0] = field_cells(field_model, points, normals)[
            reads
        ]
        out |= {"field": field, "voxels": voxels, "cells": cells}
    return out
