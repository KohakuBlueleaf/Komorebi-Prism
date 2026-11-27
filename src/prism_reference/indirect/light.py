"""The elements' light for the current lights (sources and bounce passes), what the
field holds, and the indirect irradiance a pixel receives."""

import numpy as np

from prism_reference.direct.lamps import lamp_irradiance_at, lamp_shapes
from prism_reference.direct.lights import bounce_count
from prism_reference.direct.shadow import sun_shadow
from prism_reference.indirect.bounces import bounces_of
from prism_reference.indirect.field.pack import pack_field, unpack_field
from prism_reference.indirect.field.values import field_values, lookup
from prism_reference.indirect.files import load_model
from prism_reference.indirect.hmatrix.apply import apply
from prism_reference.indirect.sky import sky_coefficients
from prism_reference.raster.vector import dot3

F = np.float32


def lamp_irradiance(lights, position, normal):
    """The lamps' irradiance (n, 3) float32, without shadows (as a pixel's)."""
    out = np.zeros((len(position), 3), F)
    for k in range(len(lights["lamp_intensity"])):
        e, _ = lamp_irradiance_at(lights, k, position, normal)
        out = out + lights["lamp_colour"][k] * e[:, None]
    return out


def element_light(lights, model, bounces=None, product=apply):
    """Each element's sky irradiance, its direct light (the sun's shadow from the lights'
    map: none from a 1 x 1 stand-in), L0 = emission x scale + albedo / pi direct, and the
    `bounces` passes E1 = M L0, E_k = M (albedo / pi E_(k-1)) by `product(blocks,
    weights, x)`; bounces None: bounces_of the lights and the model."""
    p, n = model["position"], model["normal"]
    sun = sun_shadow(lights, p, n) * np.maximum(
        dot3(n, lights["sun_direction"][None, :]), F(0)
    )
    sky = np.maximum(model["transfer"] @ sky_coefficients(lights), F(0)).astype(F)
    direct = (
        sun[:, None] * lights["sun_irradiance"] + lamp_irradiance(lights, p, n)
    ) + sky
    scale = F(lights["emissive_scale"])
    l0 = model["emission"] * scale + model["albedo"] * F(1 / np.pi) * direct
    l0 = np.where(model["real"][:, None], l0, F(0)).astype(F)
    if bounces is None:
        bounces = bounces_of(lights, model)
    passes = []
    for _ in range(bounce_count(bounces)):
        x = l0 if not passes else model["albedo"] * F(1 / np.pi) * passes[-1]
        passes.append(product(model["blocks"], model["weights"], x))
    return {"sky": sky, "direct": direct, "l0": l0, "passes": passes}


def field_source(light):
    """What the field holds per element for `element_light`'s result: E1 + ... +
    E_bounces + the element's own sky irradiance (with no pass, the sky alone)."""
    if not light["passes"]:
        return light["sky"]
    total = light["passes"][0]
    for e in light["passes"][1:]:
        total = total + e
    return total + light["sky"]


def signature(lights):
    """What the element light depends on: the shadow map (by identity), the sun, the
    turn, the lamps and the emissive scale."""
    small = [lights[k] for k in ("sun_direction", "sun_irradiance", "turn")]
    small += [lights[k] for k in ("lamp_position", "lamp_colour", "lamp_intensity")]
    small += [lamp_shapes(lights)]
    small += [np.float32(lights["emissive_scale"]), lights["shadow_camera"]]
    return b"".join(np.asarray(a, F).tobytes() for a in small)


def field_for(lights):
    """The model and the field's values (nv, 6, 3) for the lights (`lights["indirect"]`
    names the file), remade when the lights or the bounce count change;
    `lights["indirect_packed"]`: as the card holds them."""
    if "indirect" not in lights:
        raise ValueError(
            "the term `indirect` needs the scene's indirect file: write it with "
            "python scripts/data/public_scenes.py indirect <scene> (lights.load "
            "finds it)"
        )
    model = load_model(lights["indirect"])
    bounces = bounces_of(lights, model)
    key = (signature(lights), id(lights["shadow_map"]), id(lights["octahedral"]))
    key += (bounces,)
    cache = model.setdefault("cache", [])
    values = None
    for entry in cache:
        if entry[0] == key and entry[1] is lights["shadow_map"]:
            values = entry[2]
    if values is None:
        light = element_light(lights, model, bounces)
        values = field_values(model, field_source(light))
        cache[:] = cache[-3:] + [(key, lights["shadow_map"], values)]
    if lights.get("indirect_packed"):
        values, _ = unpack_field(*pack_field(values, model["field_has"]))
    return model, values


def irradiance(lights, position, normal):
    """The indirect irradiance (n, 3) float32 a pixel receives (`lookup` of
    `field_for`); where no voxel has data, the lights' `ambient`."""
    model, values = field_for(lights)
    e, found = lookup(model, values, position, normal)
    ambient = np.asarray(lights["ambient"], dtype=F)
    return np.where(found[:, None], e, ambient).astype(F)
