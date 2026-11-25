"""A material's kind of shader and its texture slots, by code."""

# The kinds' codes (scene.public.materials KINDS) and the texture slots.
FLAT, TEXTURED, MASKED, LIT, EMISSIVE, TRANSPARENT = range(6)
ALBEDO, MASK, NORMAL, SPECULAR = range(4)
OPAQUE_BYTE = 128  # a masked pixel whose alpha byte is under this is a hole
