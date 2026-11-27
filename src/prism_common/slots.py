"""Named slots and contracts: what a stage or a model part reads and writes."""

from dataclasses import dataclass

from prism_common.formats import FORMATS
from prism_common.registry import Registry

UNITS = ("tile", "element", "page")


@dataclass(frozen=True)
class Slot:
    """A named value the pipeline passes between implementations: its format, its unit,
    what it holds in one line."""

    name: str
    format: str
    unit: str
    what: str

    def __post_init__(self):
        if self.format not in FORMATS:
            raise ValueError(
                f"slot {self.name!r}: format {self.format!r} is none of "
                f"{', '.join(FORMATS)}"
            )
        if self.unit not in UNITS:
            raise ValueError(
                f"slot {self.name!r}: unit {self.unit!r} is none of {', '.join(UNITS)}"
            )


SLOTS = Registry("slot")


def slot(name, format, unit, what):
    """A slot made and registered under its name."""
    return SLOTS.register(name, Slot(name, format, unit, what))


slot(
    "elements.radiance",
    "bf16",
    "tile",
    "every element's outgoing light: a row of tiles, the colours rows 0 to 2",
)
slot(
    "elements.irradiance",
    "fp32",
    "tile",
    "the light every element receives: a row of tiles, the colours rows 0 to 2",
)
slot(
    "scene.mesh",
    "u32",
    "page",
    "the scene's triangles as blocks of 32: corners' positions, then their colours",
)
slot(
    "mesh.attributes",
    "u32",
    "page",
    "each layer's shade blocks by its name: per block of 32 triangles their albedo "
    "texel areas, material words, normal's and specular's",
)
slot(
    "view.camera",
    "fp32",
    "page",
    "a view's camera: its 16 numbers and the frame's grid of tiles",
)
slot(
    "view.depth",
    "fp32",
    "page",
    "a host's DEPTH views: their view indices, each one's camera, a view's frame size",
)
slot(
    "frame.visibility",
    "fp32",
    "page",
    "per tile the five planes: depth (1/z), red, green, blue, the triangle's word "
    "(the float of bits 0x3F800000 + n; -1 where empty)",
)
slot(
    "frame.lists",
    "u32",
    "page",
    "each layer's directory and lists by its name: the items FILL wrote, their records",
)
slot(
    "frame.surface",
    "u32",
    "page",
    "each layer's lit surface by its name: a directory of two frames of albedo, "
    "normal, visibility, specular, LIGHT's table, its profile and pages",
)
slot(
    "light.shadow_map",
    "fp32",
    "page",
    "the sun's shadow map: 1/z, in light pages of 32 x 32, pages row by row",
)
slot(
    "light.shadow_maps",
    "u32",
    "page",
    "the page of maps: 1 + the half of its records the frames read (the whole map's, "
    "then each fitted map's: camera, pages, side, texel, bias, levels)",
)
slot(
    "light.lamp_faces",
    "u32",
    "page",
    "each lamp's faces in the page of maps, in lamp_faces' order: its first face "
    "record and its faces (0, 0 without faces)",
)
slot(
    "light.field",
    "u32",
    "page",
    "the indirect field as LIGHT reads it: a block of voxels a light page, texels of "
    "a has-data bit and three square-root codes",
)
slot(
    "light.field_scale",
    "fp32",
    "page",
    "the field's scale as its last update left it: the updates made and the float32 "
    "every channel's code decodes by",
)
slot(
    "display.picture",
    "u32",
    "page",
    "the frame for display: a page a tile, 32 x 32 pixels of R, G, B, 255 bytes",
)


@dataclass(frozen=True)
class Contract:
    """What a pipeline is given (`reads`) and must give (`writes`), by slot name."""

    reads: tuple = ()
    writes: tuple = ()

    def check(self, pipeline):
        """Each implementation's slots registered, its reads given or written by an
        earlier one, and every slot of `writes` written; errors name both."""
        known = set(self.reads)
        for name in (*self.reads, *self.writes):
            SLOTS.get(name)
        for implementation in pipeline.implementations:
            for name in (*implementation.reads, *implementation.writes):
                if name not in SLOTS:
                    raise ValueError(
                        f"pipeline {pipeline.name!r}: {implementation.name} names "
                        f"slot {name!r}, which is not registered"
                    )
            for name in implementation.reads:
                if name not in known:
                    raise ValueError(
                        f"pipeline {pipeline.name!r}: {implementation.name} reads "
                        f"slot {name!r}, which no earlier implementation writes and "
                        f"the pipeline is not given"
                    )
            known.update(implementation.writes)
        for name in self.writes:
            if name not in known:
                raise ValueError(
                    f"pipeline {pipeline.name!r}: slot {name!r} is written by no "
                    f"implementation"
                )
