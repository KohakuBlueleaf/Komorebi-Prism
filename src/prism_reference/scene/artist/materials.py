"""A glTF material of the scene description mapped onto the reference's six kinds, and its
textures decoded and packed as the public scenes' materials file packs them."""

import concurrent.futures
from pathlib import Path

import numpy as np

from prism_reference.post.display import (
    SRGB_GAMMA,
    SRGB_KNEE,
    SRGB_OFFSET,
    SRGB_SCALE,
    SRGB_SLOPE,
)
from prism_reference.scene.public.materials import EMISSIVE_MIN, EXPONENT_RANGE, KINDS
from prism_reference.scene.public.textures import (
    MIP_LEVELS,
    decode_image,
    texture_levels,
)

TRANSMISSION = "KHR_materials_transmission"
DIELECTRIC = 0.04  # the specular colour of a non-metal
WHITE = np.full((1, 1, 4), 255, dtype=np.uint8)  # the texture of a scene without any
OTHER_TEXTURES = (
    "metallic_roughness_texture",
    "normal_texture",
    "occlusion_texture",
    "emissive_texture",
)


def srgb_to_linear(values):
    """Bytes (any shape) through the standard sRGB transfer to linear values in 0..1."""
    c = np.asarray(values, dtype=np.float64) / 255.0
    curve = ((c + SRGB_OFFSET) / SRGB_SCALE) ** SRGB_GAMMA
    return np.where(c <= SRGB_KNEE * SRGB_SLOPE, c / SRGB_SLOPE, curve)


def image_of(scene, use):
    """The image index a TextureUse samples, or None (no use, or a texture without one)."""
    if use is None:
        return None
    image = scene.textures[use.texture].image
    return image if image >= 0 else None


def image_bytes(image):
    """The bytes of a description Image: its `data`, else the file at its `uri`."""
    if image.data is not None:
        return bytes(image.data)
    if image.uri is not None:
        return Path(image.uri).read_bytes()
    raise ValueError(f"image {image.name!r}: neither bytes nor a file")


def exponent_of(roughness):
    """round(2 / a^2 - 2) with a = roughness^2, clipped to EXPONENT_RANGE."""
    a = float(roughness) ** 2
    value = 2.0 / (a * a) - 2.0 if a > 0 else np.inf
    return int(np.clip(np.rint(value), *EXPONENT_RANGE))


def specular_of(material):
    """0.04 (1 - metallic) + base rgb x metallic, (3,)."""
    metallic = float(material.metallic)
    return DIELECTRIC * (1.0 - metallic) + material.base_color[:3] * metallic


def transmission_factor(material):
    """KHR_materials_transmission's `transmissionFactor`, or None without the extension."""
    found = material.carried.get(TRANSMISSION)
    return None if found is None else float(found.get("transmissionFactor", 0.0))


def is_identity(use):
    """True when a TextureUse's transform is offset 0, rotation 0, scale 1."""
    return not np.any(use.offset) and use.rotation == 0.0 and np.all(use.scale == 1.0)


def dropped_of(material, kind, scene):
    """What the mapping of `material` as `kind` does not draw, as short names."""
    albedo = image_of(scene, material.base_color_texture)
    out = []
    if material.metallic_roughness_texture is not None:
        out.append("metallic-roughness texture")
    if material.occlusion_texture is not None:
        out.append("occlusion texture")
    if kind == "emissive" and albedo is not None:
        out.append("emissive-with-base texture")
    if material.normal_texture is not None and kind != "lit":
        out.append("normal texture of a kind without one")
    if kind == "lit" and material.normal_scale != 1.0:
        out.append("normal scale")
    uses = [material.base_color_texture] + [
        getattr(material, n) for n in OTHER_TEXTURES
    ]
    if any(use is not None and use.uv != 0 for use in uses):
        out.append("second UV set")
    if any(use is not None and not is_identity(use) for use in uses[1:]):
        out.append("texture transform not on the base colour")
    if material.double_sided:
        out.append("double_sided")
    if material.unlit:
        out.append("unlit")
    out.extend(name for name in material.carried if name != TRANSMISSION)
    return out


def map_material(material, scene, texture_number, has_uv=True):
    """(kind code, base (3,), slots [4], exponent, specular (3,), transmission (3,)) and
    the dropped names of one material; texture_number(image, role) numbers textures."""
    base_rgb = np.asarray(material.base_color[:3], dtype=np.float64)
    albedo = image_of(scene, material.base_color_texture)
    glowing = image_of(scene, material.emissive_texture)
    normal = image_of(scene, material.normal_texture)
    glow = np.asarray(material.emissive, np.float64) * material.emissive_strength
    factor = transmission_factor(material)
    slots, base, tau = [-1, -1, -1, -1], base_rgb.copy(), np.zeros(3)
    if glowing is not None or glow.max() >= EMISSIVE_MIN:
        kind = "emissive"
        if glowing is not None:
            slots[0], base = texture_number(glowing, "colour"), np.ones(3)
        else:
            base = np.clip(glow, 0.0, 1.0)
    elif material.alpha_mode == "BLEND" or (factor is not None and factor > 0):
        kind = "transparent"
        if factor is not None:
            tau = factor * base_rgb
        else:
            tau = np.full(3, 1.0 - float(material.base_color[3]))
        if albedo is not None:
            slots[0] = texture_number(albedo, "colour")
    elif albedo is None or not has_uv:
        kind = "flat"
    else:
        slots[0] = texture_number(albedo, "colour")
        if material.alpha_mode == "MASK":
            kind = "masked"
        elif normal is not None:
            kind = "lit"
            slots[2] = texture_number(normal, "normal")
        else:
            kind = "textured"
    record = (
        KINDS.index(kind),
        base,
        slots,
        exponent_of(material.roughness),
        specular_of(material),
        tau,
    )
    return record, dropped_of(material, kind, scene)


class Textures:
    """The textures of a conversion: numbered once per (image, role) on first use,
    decoded once, packed into `texels`, `mip`, `levels`."""

    def __init__(self, scene):
        self.scene = scene
        self.jobs, self.numbers, self.chains = [], {}, {}

    def number(self, image, role):
        """The texture number of (image, role), given on its first use."""
        key = (image, role)
        if key not in self.numbers:
            self.numbers[key] = len(self.jobs)
            self.jobs.append(key)
        return self.numbers[key]

    def decode(self, extra, workers=4):
        """Decodes every numbered job and the (image, role) keys of `extra` once."""
        keys = list(dict.fromkeys(self.jobs + list(extra)))
        keys = [k for k in keys if k not in self.chains]

        def one(key):
            image, role = key
            pixels = decode_image(image_bytes(self.scene.images[image]))
            return texture_levels(pixels, role)

        if workers > 1 and len(keys) > 1:
            with concurrent.futures.ThreadPoolExecutor(workers) as pool:
                chains = list(pool.map(one, keys))
        else:
            chains = [one(key) for key in keys]
        self.chains.update(zip(keys, chains, strict=True))

    def mean(self, image):
        """The linear mean colour (3,) of an image: its 1 x 1 level in the colour role."""
        last = self.chains[(image, "colour")][-1]
        return srgb_to_linear(last[0, 0, :3])

    def chain_list(self):
        """The mip chain of each texture; without any, the one WHITE texel."""
        return [self.chains[key] for key in self.jobs] or [[WHITE]]

    def pack(self):
        """(texels uint8, mip (N, MIP_LEVELS, 3) int64, levels (N,) int32) of the jobs."""
        chains = self.chain_list()
        mip = np.zeros((len(chains), MIP_LEVELS, 3), dtype=np.int64)
        levels = np.zeros(len(chains), dtype=np.int32)
        offset, blocks = 0, []
        for t, chain in enumerate(chains):
            levels[t] = len(chain)
            for level, image in enumerate(chain):
                mip[t, level] = offset, image.shape[1], image.shape[0]
                blocks.append(image.reshape(-1))
                offset += image.size
        return np.concatenate(blocks), mip, levels

    def names(self):
        """A name per texture: `<image name or number> (<role>)`."""
        names = [f"{self.scene.images[i].name or i} ({role})" for i, role in self.jobs]
        return names or ["(white)"]
