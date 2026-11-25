"""The texture stage's thread unit: SHADE a layer, its words the layer's columns (the
texture host's; SHADE's table shared with slot mesh.attributes; in a DEPTH view the
view's own directory and lists, taken from slot frame.lists), its time once a layer."""

from prism.core.unit import Unit

UNIT = Unit(
    sources=("thread/material_texture_unit.c",),
    includes=("thread",),
    layer=True,
    columns=(
        "shade_directory",
        "shade_lists",
        "textures",
        "shade_table",
        "shade_profile",
        "opaque",
        "mode",
        "shade_surface",
    ),
    shares={"mesh.attributes": ("shade_table",)},
    takes=("frame.lists",),
    times=("shade",),
)
