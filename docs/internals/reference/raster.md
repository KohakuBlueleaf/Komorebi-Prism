# Raster: setup, fill and SHADE

`prism_reference.raster`: `setup` (projection, the clip, the records), `fill` (binning
and the fill of a tile), `frames` (the plain frame, the FILL layers and SHADE); `vector`
holds the float32 vector arithmetic the frames and the lights share. The C++ version
(`native/raster/raster_cpu.cpp`, built and run by `native.raster_cpu`) shares the setup and
the pixel test in `native/raster/fill.hpp` and SHADE in `native/raster/shade.hpp`, so
they cannot drift apart; numpy is written separately.

## The algorithm

Opaque triangles, depth-tested, 1024 x 1024 pixels, tiles of 32 x 32 pixels (a 32 x 32
grid of tiles), float32 arithmetic in the order written in `prism_reference.raster`, no fused
multiply-add.

1. **Setup**, one triangle at a time (no triangle depends on another). The three
   vertices are taken into camera space (`x`, `y`, `z` along right, up, forward). A
   triangle with no vertex beyond the near distance `n` (`z > n`) is dropped; one with
   all three beyond is kept whole; any other is **clipped** at the plane `z = n`: its
   edges are walked in order (0-1, 1-2, 2-0), each vertex beyond the plane is kept and
   each edge that crosses the plane adds the point where it crosses, computed from the
   vertex beyond (`a`) toward the other (`b`) as `s = (n - z_a) / (z_b - z_a)`,
   `x = x_a + s (x_b - x_a)`, `y` likewise, `z = n`, colour `c_a + s (c_b - c_a)`
   (float32, in this order). The 3 or 4 points give one triangle or two (0, 1, 2 and
   0, 2, 3), each with the original triangle's index; they go through the rest of the
   setup like whole triangles, so up to two records come from one triangle. Every
   point is then projected (`1/z`, screen `x` and `y`). Each triangle is turned to
   positive orientation by swapping two vertices, a zero-area triangle is dropped, and
   the record is built: three edge functions `a x + b y + c`, the planes of `1/z` and of the
   three colour channels (linear in screen space, no perspective correction), the box of
   pixel centres it can cover (empty box: dropped), and which edges are top or left.
2. **Binning.** A triangle goes to every tile its pixel box touches, in triangle order.
   The sizes of the tile lists are an output.
3. **Fill**, one tile at a time. A pixel centre `(x + 0.5, y + 0.5)` is inside when
   all three edge values are `> 0`, or `== 0` on a top or left edge (the top-left fill
   rule: the edge of a shared diagonal belongs to exactly one of its two triangles). The
   fragment with the larger `1/z` wins; an exact tie goes to the lower triangle index, so
   the result does not depend on the order of the list. Empty pixels keep the background
   colour and depth 0.

Outputs of both versions (the arrays a comparison reads): `colour`
(1024, 1024, 3) float32, `depth` (the stored `1/z`; 0 where empty) (1024, 1024) float32,
`tri` (the index of the visible triangle, -1 where empty) (1024, 1024) int32 and
`tile_counts` (the list sizes) (32, 32) int32.

## Agreement

The numpy and the C++ versions produce the same arrays bit for bit on the four generated
scenes ([the scenes page](../../concepts/scenes.md)), including the tile list sizes:

| scene | triangles | differing pixels (`tri`, `depth`, `colour`) | tile list sizes |
|---|---|---|---|
| `tiny` | 398 | 0 / 0 / 0 | equal |
| `s10k` | 11,994 | 0 / 0 / 0 | equal |
| `s100k` | 102,308 | 0 / 0 / 0 | equal |
| `s1m` | 997,806 | 0 / 0 / 0 | equal |

To compare them: `native.raster_cpu.run_cpu(name, threads, out)` renders the scene
`<data>/<name>.npz` with the C++ version into the folder `out` (generating it first when it
is missing; `load_outputs(out)` reads the four arrays back), and `raster.frames.rasterize`
renders the same scene (`scene.files.load_scene`) with numpy; compare the arrays' bit
patterns. The table is such a run with 16 threads.

Why exact: every operation is a float32 add, subtract, multiply, divide or compare in a
fixed order (no fused multiply-add: `native.build` compiles with `-ffp-contract=off`),
all IEEE-exact, and the winner of a pixel does not depend on the order fragments arrive in.

A card implementation will not be bit-exact if it uses another order of operations;
compare coverage and depth per pixel and count the differing pixels, which sit on
triangle edges.

## Scenes and the work they make

| scene | triangles | after setup | list entries | largest list | non-empty tiles of 1024 | covered pixels |
|---|---|---|---|---|---|---|
| `tiny` | 398 | 289 | 4,047 | 28 | 664 | 62.8 % |
| `s10k` | 11,994 | 7,534 | 17,121 | 232 | 672 | 63.8 % |
| `s100k` | 102,308 | 67,219 | 92,778 | 1,302 | 709 | 66.9 % |
| `s1m` | 997,806 | 549,342 | 626,034 | 8,780 | 754 | 71.2 % |

"After setup" is the number of records `raster.setup.setup` gives (a clipped triangle
may give two), the list columns come from the tile counts of `raster.fill.bin_triangles`
(also `rasterize`'s `tile_counts`), and the covered pixels are those whose `tri` is not -1.

About a third of the screen is empty sky (empty tiles), a few large near spheres give
tiles with thousands of small triangles, and the ground gives a gradient of
triangle size with distance.

## Shading: materials and textures (SHADE)

On the scenes with a materials file (Sponza and the two Bistro scenes,
[the scenes page](../../concepts/scenes.md)) the frame is coloured from each pixel's
material instead of the vertex colours: a stage SHADE after FILL, defined by
`raster.frames.rasterize_shaded` and matched by the C++ version (`raster_cpu
--materials DIR`, `native/raster/shade.hpp`).

1. **Two FILLs.** FILL runs once over the triangles whose material is not `masked` and
   once over those that are (the other set's triangles are collapsed to a point, so
   setup drops them and the rest keep their numbers), into two sets of planes. A pixel
   takes the masked layer where its fragment is nearer (the fill's own rule: larger
   1/z, a tie to the lower triangle number) and not a hole, otherwise the other
   layer. There is one masked layer: a hole shows the nearest surface that is not
   masked, never a second masked one behind it.
2. **Setup, per triangle.** Its first piece that setup keeps (the clip of the fill's
   setup, with the corners' u, v and light term cut along with the colour) gives the
   planes of u/z, v/z and light/z over the screen, built from the record's edge
   functions like the colour planes. For each of the material's textures one mip
   level: with the piece's doubled area `A` in pixels and `T` in level-0 texels,
   the number of `k = 1 .. levels - 1` with `T > A 2^(2k - 1)` (the level at which a
   pixel is nearest to one texel). For `lit`, one tangent frame: the normal of its
   positions turned toward the eye, the tangent along +u from its positions and
   coordinates (made orthogonal to the normal), the bitangent their cross product,
   turned toward +v.
3. **Per pixel**, from the winner's triangle number and the 1/z FILL wrote: u, v and
   the light term are the planes divided by that 1/z (perspective-correct); the texel
   is the nearest one, coordinates wrapping, row 0 at v = 1. An albedo byte becomes
   linear colour by the pictures' 2.2 gamma; the other textures' bytes are read as
   `b / 255` (normals `2 b / 255 - 1`).

| kind | colour of a pixel |
|---|---|
| `flat` | FILL's vertex colour |
| `textured` | albedo x base colour x light term |
| `masked` | as `textured`; a hole where the mask's alpha byte (or the albedo's) is under 128 |
| `lit` | albedo x base colour x (0.25 + 0.75 max(0, n . l)) + specular colour x (specular texel) x max(0, n . h)^exponent, n the normal map's normal in the frame, l toward the scene's point light, h the half vector |
| `emissive` | albedo x base colour, unlit |
| `transparent` | a third layer over the others ([direct light](direct.md), "Glass"): `tau C + (1 - max tau)` x albedo x base colour x light term, `C` the colour behind, `tau` the transmission |

Everything is float32 in the order written (the power by squaring, low bit first),
so the two versions agree bit for bit where no glass is in front (below). Not part of it:
bilinear filtering, a level per pixel and shadows. The C++ version has no `transparent`
kind: it fills transparent triangles into its first layer as an opaque surface. With one
level a triangle and a box-filtered mask, leaves far from the camera fall below the
threshold at the coarser levels and thin out.

What SHADE needs beyond the fill's 128-byte record, per triangle: the three planes
of u/z, v/z and light/z (nine floats), a level per texture, the material number and,
for `lit`, the frame (nine floats). The reference computes them from the scene and the
materials file; the record is unchanged.

The SHADE outputs of the two versions, on the six material views (Sponza, Bistro interior
and Bistro exterior, each `overview` and `close`): on both Sponza views 0 differing pixels
in `tri`, `depth` and `colour`; on the four Bistro views the pixels that differ are exactly
those with glass in front (`rasterize_shaded`'s `front`: 5,907, 15,398, 30,535 and 23,525
pixels in the interior's overview and close and the exterior's overview and close), 0
elsewhere; the tile list sizes are equal on all six. To compare them:
`run_cpu(view, threads, out, materials=True)` against `rasterize_shaded` of the view's
scene and `scene.public.materials.load_materials` of its scene.

`material.access` gives the texture pages lit SHADE reads
([material](material.md)).
