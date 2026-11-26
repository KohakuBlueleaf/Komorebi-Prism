"""The reference's surface of an artist's scene against the planes Cycles rendered of the
same scene: pictures and compare.json under <data>/artist/<key>/surface/ (no card)."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from prism_common.paths import data_root
from prism_reference.io.pictures import colormap, downscale
from prism_reference.io.png import write_png
from prism_reference.material.surface import MOST_TRIANGLES, surface, visibility
from prism_reference.post.display import to_srgb_standard8
from prism_reference.scene.artist.entry import camera_node
from prism_reference.scene.artist.table import artist_dir
from prism_reference.scene.description.flatten import drawn_triangles, flatten
from prism_reference.scene.importers import gltf

PLANES_FILE = "cycles.npz"  # written by `artist_scenes.py planes`
BACKGROUND_DEPTH = 1e9  # Cycles' depth at or past it: no surface
REGISTERED = 1e-3  # position within this fraction of the diagonal
METALLIC_UNDER = 0.01
FILTERS = ("anisotropic", "trilinear", "nearest")


class Clock:
    """Seconds of each named step."""

    def __init__(self):
        self.seconds, self.last = {}, time.perf_counter()

    def step(self, name):
        """Records the seconds since the last step under `name`."""
        now = time.perf_counter()
        self.seconds[name] = round(now - self.last, 2)
        self.last = now


def unit_picture(v):
    """A (H, W, 3) vector plane in [-1, 1] as RGB bytes."""
    return np.rint(np.clip(v * 0.5 + 0.5, 0, 1) * 255).astype(np.uint8)


def grey(v, low=0.0, high=1.0):
    """A scalar plane as grey bytes between low and high."""
    return np.rint(np.clip((v - low) / (high - low), 0, 1) * 255).astype(np.uint8)


def material_picture(material):
    """A colour per material index; black where not covered."""
    m = material.astype(np.int64) + 2
    rgb = np.stack([(m * 97) % 251, (m * 57) % 241, (m * 31) % 239], -1) + 4
    return np.where((material == -1)[..., None], 0, rgb).astype(np.uint8)


def depth_of(depth, hit):
    """Log depth on the colour map; black where nothing is hit."""
    z = np.log(np.where(hit, np.maximum(depth, 1e-9), 1.0))
    rgb = colormap(z, z[hit].min(), z[hit].max()) if hit.any() else colormap(z)
    rgb[~hit] = 0
    return rgb


def pictures(folder, ref, others, cyc, box, metrics_planes):
    """Every plane of both sides as a PNG, and the difference pictures."""
    lo, hi = box
    span = np.maximum(hi - lo, 1e-9)
    hit = ref["covered"]
    hit_c = cyc["depth"] < BACKGROUND_DEPTH
    out = {
        "ref_base_color": to_srgb_standard8(ref["base_color"]),
        "ref_normal": unit_picture(ref["normal"]),
        "ref_geometric_normal": unit_picture(ref["geometric_normal"]),
        "ref_position": grey((ref["position"] - lo) / span),
        "ref_depth": depth_of(ref["depth"], hit),
        "ref_alpha": grey(ref["alpha"]),
        "ref_metallic": grey(ref["metallic"]),
        "ref_roughness": grey(ref["roughness"]),
        "ref_occlusion": grey(ref["occlusion"]),
        "ref_emissive": to_srgb_standard8(ref["emissive"]),
        "ref_material": material_picture(ref["material"]),
        "ref_uv": grey(np.concatenate([ref["uv"] % 1, ref["uv"][..., :1] * 0], -1)),
        "ref_covered": grey(hit.astype(np.float64)),
        "ref_transparent": grey(ref["transparent"].astype(np.float64)),
        "cycles_combined": to_srgb_standard8(cyc["combined"]),
        "cycles_base_color": to_srgb_standard8(
            cyc["diffuse_color"] + cyc["glossy_color"]
        ),
        "cycles_diffuse_color": to_srgb_standard8(cyc["diffuse_color"]),
        "cycles_glossy_color": to_srgb_standard8(cyc["glossy_color"]),
        "cycles_emit": to_srgb_standard8(cyc["emit"]),
        "cycles_normal": unit_picture(cyc["normal"]),
        "cycles_position": grey((cyc["position"] - lo) / span),
        "cycles_depth": depth_of(cyc["depth"], hit_c),
        "cycles_uv": grey(np.concatenate([cyc["uv"] % 1, cyc["uv"][..., :1] * 0], -1)),
    }
    for name, planes in others.items():
        out[f"ref_base_color_{name}"] = to_srgb_standard8(planes["base_color"])
    angle, distance, base_diff, mask = metrics_planes
    out["diff_normal"] = np.where(mask[..., None], colormap(angle, 0, 30), 0)
    out["diff_position"] = colormap(np.log10(np.maximum(distance, 1e-7)), -6, -1)
    out["diff_base_color"] = np.where(mask[..., None], colormap(base_diff, 0, 0.25), 0)
    for name, image in out.items():
        write_png(folder / f"{name}.png", np.asarray(image, dtype=np.uint8))
    return sorted(out)


def base_numbers(ref_base, cyc_base, mask):
    """Mean absolute difference a channel, PSNR (peak 1) and the pixels compared."""
    d = (ref_base[mask] - cyc_base[mask]).astype(np.float64)
    if not len(d):
        return {"mad": None, "psnr": None, "pixels": 0}
    mse = float(np.mean(d * d))
    psnr = float(10 * np.log10(1.0 / mse)) if mse > 0 else None
    return {"mad": float(np.mean(np.abs(d))), "psnr": psnr, "pixels": int(mask.sum())}


def aliasing(small, large, factor):
    """MAD of the base colour against the `factor` times larger one box-filtered down,
    over pixels covered there and in every sub-pixel."""
    down = downscale(large["base_color"].astype(np.float64), factor)
    full = downscale(large["covered"].astype(np.float64)[..., None], factor)[..., 0]
    mask = small["covered"] & (full == 1.0)
    d = np.abs(small["base_color"][mask] - down[mask])
    return {"mad": float(d.mean()) if len(d) else None, "pixels": int(mask.sum())}


def roll_degrees(scene, node_index):
    """The camera's roll: its up axis's angle off the vertical plane of its view."""
    linear = np.asarray(scene.nodes[node_index].world, dtype=np.float64)[:3, :3]
    forward = linear @ [0.0, 0.0, -1.0]
    up = linear @ [0.0, 1.0, 0.0]
    across = np.cross([0.0, 1.0, 0.0], forward)
    if np.linalg.norm(across) == 0:
        return None
    across, up = across / np.linalg.norm(across), up / np.linalg.norm(up)
    return float(np.degrees(np.arcsin(min(1.0, abs(float(up @ across))))))


def compare(key, data, size, factor):
    """Writes the pictures and compare.json of one scene; returns compare.json's dict."""
    clock = Clock()
    folder = artist_dir(data) / key / "surface"
    folder.mkdir(parents=True, exist_ok=True)
    scene = gltf.load(artist_dir(data) / key / "scene.glb")
    record = {"scene": key, "size": list(size), "factor": factor}
    drawn = drawn_triangles(scene)
    record["triangles"] = {"drawn": drawn, "budget": MOST_TRIANGLES}
    if drawn > MOST_TRIANGLES:
        record["skipped"] = f"{drawn} triangles drawn, over the {MOST_TRIANGLES} budget"
        (folder / "compare.json").write_text(json.dumps(record, indent=1))
        return record
    node = camera_node(scene)
    record["camera"] = {"node": scene.nodes[node].name}
    record["camera"]["roll_degrees"] = roll_degrees(scene, node)
    clock.step("load")
    flat = flatten(scene, MOST_TRIANGLES)
    p = flat["positions"]
    box = (p.min(axis=0).astype(np.float64), p.max(axis=0).astype(np.float64))
    clock.step("flatten")
    seen = visibility(scene, node, size, flat)
    clock.step("visibility")
    cache, report = {}, {}
    ref = surface(scene, node, size, "anisotropic", seen, cache, report)
    clock.step("surface anisotropic")
    others = {}
    for name in FILTERS[1:]:
        others[name] = surface(scene, node, size, name, seen, cache)
        clock.step(f"surface {name}")
    large_size = (size[0] * factor, size[1] * factor)
    large_seen = visibility(scene, node, large_size, flat)
    clock.step(f"visibility x{factor}")
    aliased = {}
    for name in FILTERS:
        large = surface(scene, node, large_size, name, large_seen, cache)
        aliased[name] = aliasing(
            ref if name == FILTERS[0] else others[name], large, factor
        )
        del large
        clock.step(f"surface {name} x{factor}")
    cyc = dict(np.load(artist_dir(data) / key / "surface" / PLANES_FILE))
    diagonal = seen["diagonal"]
    hit, hit_c = ref["covered"], cyc["depth"] < BACKGROUND_DEPTH
    both = hit & hit_c
    distance = np.linalg.norm(ref["position"] - cyc["position"], axis=-1) / diagonal
    distance = np.where(both, distance, 0.0)
    registered = both & (distance <= REGISTERED)
    d = distance[both]
    record["registration"] = {
        "distance_median": float(np.median(d)) if len(d) else None,
        "distance_p99": float(np.percentile(d, 99)) if len(d) else None,
        "one_side_only": float(np.mean(hit != hit_c)),
        "registered": float(registered.sum() / max(both.sum(), 1)),
        "diagonal": diagonal,
    }
    cosine = np.sum(ref["normal"] * cyc["normal"], axis=-1)
    length = np.linalg.norm(cyc["normal"], axis=-1)
    angle = np.degrees(np.arccos(np.clip(cosine / np.maximum(length, 1e-12), -1, 1)))
    a = angle[registered]
    record["normal_degrees"] = {
        f"p{q}": float(np.percentile(a, q)) if len(a) else None for q in (50, 90, 99)
    }
    cyc_base = cyc["diffuse_color"] + cyc["glossy_color"]
    mask = registered & (ref["metallic"] < METALLIC_UNDER)
    record["base_color"] = {
        "anisotropic": base_numbers(ref["base_color"], cyc_base, mask)
    }
    for name, planes in others.items():
        record["base_color"][name] = base_numbers(planes["base_color"], cyc_base, mask)
    record["aliasing"] = aliased
    base_diff = np.abs(ref["base_color"] - cyc_base).mean(axis=-1)
    record["surface"] = {
        "covered": int(hit.sum()),
        "transparent": int(ref["transparent"].sum()),
        "mask_below_cutoff": report.get("mask_below_cutoff", 0),
        "materials": len(np.unique(ref["material"][hit])),
        "textures_decoded": len(cache),
        "tangents": {
            s: sum(v == s for v in report.get("tangents", {}).values())
            for s in sorted(set(report.get("tangents", {}).values()))
        },
    }
    record["tangent_primitives"] = report.get("tangents", {})
    record["pictures"] = pictures(
        folder, ref, others, cyc, box, (angle, distance, base_diff, mask)
    )
    clock.step("compare")
    record["seconds"] = clock.seconds
    (folder / "compare.json").write_text(json.dumps(record, indent=1))
    return record


def main():
    """Compares each named scene; one JSON line a scene."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("scenes", nargs="+")
    parser.add_argument("--data", type=Path, default=None)
    parser.add_argument("--size", type=int, nargs=2, default=(1280, 720))
    parser.add_argument("--factor", type=int, default=4, help="the aliasing's scale")
    args = parser.parse_args()
    data = args.data or data_root()
    for key in args.scenes:
        record = compare(key, data, tuple(args.size), args.factor)
        line = {
            k: v
            for k, v in record.items()
            if k not in ("pictures", "tangent_primitives")
        }
        print(json.dumps(line), flush=True)


if __name__ == "__main__":
    main()
