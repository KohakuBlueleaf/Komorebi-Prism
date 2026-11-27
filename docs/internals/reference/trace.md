# Trace: the box tree, the walk and the batch tracer

`prism_reference.trace`: `tree` (the box tree, its cut into treelets, its files),
`tracer` (the numpy walk and the reference ray tracer's frame) and `batch` (many rays at
once in the native library `native/trace/trace_batch.cpp`, threaded, at most 8 threads
or `PRISM_THREADS`, over the host's own tree of the box tree's triangles,
`native/trace/host_tree.hpp`, with the triangle test of
`native/trace/raytrace_core.hpp`). The scenes are the generated ones
([the scenes page](../../concepts/scenes.md)).

## The algorithm

1024 x 1024 pixels, one primary ray through each pixel centre, opaque triangles seen
from both sides, float32 arithmetic in the order written in `trace.tracer`, no fused
multiply-add. Per pixel, up to four traces:

1. a **primary ray** (closest hit);
2. from its hit point, a **shadow ray** to the one light (any hit with `tmax = 1` on the
   un-normalised direction `light - origin`; the origin is the hit point moved by `eps`
   along the normal that faces the ray);
3. a **diffuse bounce** ray along `normal + random unit vector` (closest hit); the random
   vector is `sum of four uniforms - 2` per component from a hash of the pixel number
   (seed 7, `scene.generated.uniform`), so the numbers depend on the pixel alone;
4. a **shadow ray** from the bounce hit, shaded like the first hit.

Colour: `albedo * (0.1 + direct + 0.5 * radiance)`, where `direct` is the clamped cosine
to the light (0 in shadow) and `radiance` is the sky gradient (horizon to zenith by the
height of the direction) for a missed bounce and `albedo1 * (0.1 + direct1)` at a bounce
hit. A missed primary ray gives the sky. The albedo is the vertex colour interpolated
with the barycentric coordinates of the hit.

## The tree

`trace.tree`: a binary box tree, top-down, **one triangle per leaf**, split at the median
of the triangle centroids along the longest axis of the centroid box (stable sort, the
left half rounded up). The builder is deliberately plain (no surface-area heuristic), so
it is easy to state and to reproduce; its cost is a taller walk than a good builder gives.
Nodes are numbered breadth first and the two children of a node have consecutive
numbers. A node is **8 words (32 bytes)**: box min x y z, box max x y z (float32 bits),
child 0, child 1; for a leaf both child words are `0x80000000 | leaf number`. The
triangle records (`v0`, `e1 = v1 - v0`, `e2 = v2 - v0`, 9 floats, 36 bytes) are stored in
leaf order, with `leaf_tri` giving the scene's triangle index of each leaf.

| scene | triangles | nodes | depth | tree and triangles (MB) |
|---|---|---|---|---|
| `tiny` | 398 | 795 | 9 | 0.04 |
| `s10k` | 11,994 | 23,987 | 14 | 1.2 |
| `s100k` | 102,308 | 204,615 | 17 | 10.2 |
| `s1m` | 997,806 | 1,995,611 | 20 | 99.8 |

Nodes and depth are `tree.build(scene)`'s `meta` (node count, triangles, depth); the size
is 32 bytes a node and 36 a triangle record.

## The walk, and the child order

One ray at a time with a stack (numpy does many rays at once, with the same per-ray
steps). Pop a node; skip it if its entry distance is larger than the best hit so far; a
leaf: Moeller-Trumbore test of its triangle (both sides), a hit closer than the best
(or equally close with a lower triangle index) replaces it; an internal node: test both
child boxes (slab test, the box scaled by 1.0000004 so a ray along a face is not lost),
push the ones that are hit with the **nearer on top** and, when the entry distances are
equal, **child 0 first**. A shadow ray stops at its first hit. The stack has 64 entries.

Child order matters for the work (nodes visited), not for the result: with a closest-hit
walk and the tie rule above, any order gives the same nearest hit. Without the tie rule
it would decide which of two exactly equal hits is found first, which is why equal
distances go to the lower triangle index.

## Treelets and the top tree

`tree.cut_treelets(tree, max_bytes)` cuts the tree top-down into **treelets** of at most
`max_bytes` (32 bytes per node and 36 per leaf triangle): each treelet is a subtree
with its own node numbering and its triangles, and a **top tree** over the treelets
holds the nodes above them, whose child words are either top node numbers or
`0x40000000 | treelet number`. It returns the arrays `treelet_root`, `node_treelet`
(the treelet of every node of the flat tree, -1 for top nodes), `treelet_node_off`,
`treelet_leaf_first`, `treelet_leaf_off`, `treelet_nodes`, `treelet_tris`, `top_nodes`,
`top_root`. The top tree and the treelets are the flat tree renumbered: mapping every top
node and every treelet node back to its node of the flat tree gives the same box, the
same children and the same leaf, and each treelet's triangle records are the flat tree's
records of its leaves, in order (on the four generated scenes, at 128 KiB and 1 MiB).

| scene | treelets at 128 KiB (top tree nodes) | treelets at 1 MiB (top tree nodes) |
|---|---|---|
| `tiny` | 1 (0) | 1 (0) |
| `s10k` | 16 (15) | 2 (1) |
| `s100k` | 128 (127) | 16 (15) |
| `s1m` | 1,024 (1,023) | 128 (127) |

The counts are the lengths of `cut_treelets(tree, max_bytes)`'s `treelet_root` and
`top_nodes`.

`tree.build(scene, split="sah")` cuts each segment by the surface-area heuristic instead
(16 bins per axis over the segment's centroid bounds, the plane of least `count_left x
area(left) + count_right x area(right)` with triangles on both sides); from level 40 on
every cut is the median cut, so the depth stays inside the walk's stack of 64.

`tree.build(scene, split="presorted")` makes the median tree's cuts without a sort a
level: the centroids are sorted once along each axis, and each level splits the three
sorted orders stably by the cut (a running count a segment), O(n) a level instead of the
median build's lexsort of every triangle a level. Centroids equal along the cut's axis
keep the first sort's order (the median build: the previous level's), so the two trees
can place such triangles differently; both are valid trees of the same cuts and give
the same hits (any-hit visibility of 4 M rays equal on both scenes measured in
[transport build](transport_build.md)).

## The batch tracer

`trace.batch.trace(tree, origin, direction, tmax, any_hit=False)` returns the hits of
`trace.tracer.trace` for the same rays: on 10,000 primary rays (`tracer.camera_rays`)
through distinct random pixels of `s10k` the closest hits have the same `t`, triangle,
`u` and `v` bit patterns, and the any-hit rays are blocked or free alike (an any-hit
ray's triangle is the first one its walk meets, which the two walks meet in another
order). It is the tracer of the indirect light ([indirect](indirect.md)) and of the
visibility bake ([direct light](direct.md)).

It does not walk `tree`'s nodes, and its callers give it none: the bake
(`direct.prepare.scene_tree`) and both builds of the transport (`indirect.build.open_tree`,
`indirect.blockwise.build.ray_tree`) pass `trace.tree.triangles(scene, keep)`, the
triangles in the scene's order with their scene numbers. The box tree's nodes are read
by the numpy walk (`trace.tracer`) and by its cut into treelets. The first call with a
tree makes the host's tree of its triangles (`trace.batch.host_tree`, kept until the triangles' array is freed; the
library's `host_tree_make`), on the CPUs the process may use:

- **Cuts by the surface-area heuristic**, binned: per node, the triangles' box centres in
  16 bins on each axis, the plane of least `n_left area_left + n_right area_right`; a
  node of at most `LEAF_MOST` (4) triangles stays a leaf when testing them costs no more
  than the cut (a node's test and a triangle's counted alike). The top levels are built
  on threads.
- **A node holds both children's boxes** (64 bytes, one cache line): a step tests the two
  boxes of one node fetched once, and a leaf is a range of triangles named in its
  parent, not a node of its own.
- **Depth first**: a node's first child follows it in memory.
- The triangles copied in the tree's order (`v0`, `e1`, `e2`, as the box tree stores
  them), each with its leaf in `tree` (what the call returns) and its scene triangle
  (the tie rule).

The walk (`host::trace`) goes to the nearer hit child and keeps the farther one on a
stack with its entry distance, dropping it when a closer hit is found first; it fetches
ahead the children it will visit; an any-hit ray stops at its first hit. Closest hits
take `raytrace_core.hpp`'s triangle test and its tie rule (the smaller scene triangle at
an equal `t`), so the hits are the reference's except where a ray passes through an edge
or a vertex shared by triangles. A batch is walked in the order of its rays' origins'
cells (`host::by_cell`: 64 cells a side of the tree's box, Morton order, stable inside a
cell), so rays walked one after another fetch the same nodes; the results are written in
the rays' own order.
