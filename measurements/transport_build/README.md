# The transport's build: dense against block by block

The indirect light's transport built four ways on two scenes, timed by phase, profiled
and judged against the dense build (the method: [transport build](../../docs/internals/reference/transport_build.md)).

- Host: one process a run under `taskset` of 32 CPUs (16 for the rows marked so: two
  runs side by side), tracer threads `PRISM_THREADS` (default 8). Other accounts' jobs
  shared the host; a row's seconds vary by up to about 15 % between runs. The dense
  build was run again on 32 CPUs while other jobs shared them: its SVDs (OpenBLAS on 64
  threads) slowed by 16 times, so that run is not in the table.
- Date: 2026-11-27 (UTC+8). Scenes: Sponza (262 k triangles, its tree read from the
  file) and an artists' scene of 8.8 M triangles with glass (its tree built). 50,000
  elements sampled.
- Each run: `indirect.build.build` or `indirect.blockwise.build.build` (`method`,
  `far_only`, `split`), seconds by phase from the build's own log, peak resident memory,
  a sampling profile of every thread; records in this folder (JSON, not tracked).
- Error: `y = M x` for the scene's own light `x` against the dense build's `y_exact`
  (relative L2 over all elements; elements matched by sample number), and each stored
  block against the dense `F` (relative Frobenius by class). The card's own numbers
  (`y_q8`) are 1.6e-3 (Sponza) and 2.6e-3 (artists') from `y_exact`.

## Versions

Seconds: total (tree / form factors or near + far / SVD / the rest). Rays: any-hit
visibility rays of the transport. Pairs: kernel evaluations. Flops: the compression's
(the dense build's SVDs, the randomized ranges'). Tiles: dense / low rank.

| scene | version | seconds | rays | pairs | flops | peak GB | weights GB | tiles | y error | low-rank blocks | all of M |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| artists' | dense + SVD (16 CPUs) | 986 (118 / 554 / 274 / 40) | 688 M | 1.81e9 | 14.9 T | 16.3 + 7.3 file | 2.00 | 282,322 / 205,856 | 7.7e-5 | 2.31e-2 | 1.03e-3 |
| artists' | block by block, 8 threads | 205 (35 / 28 + 104 / - / 38) | 345 M | 0.89e9 | 0.40 T | 11.4 | 2.11 | 295,070 / 220,406 | 7.4e-5 | 2.15e-2 | 1.05e-3 |
| artists' | block by block, 32 threads | 163 (33 / 18 + 66 / - / 46) | 345 M | 0.89e9 | 0.40 T | 11.6 | 2.11 | same | same | same | same |
| artists' | the same, surface-area tree | 306 (218 / 13 + 43 / - / 32) | 345 M | 0.89e9 | 0.40 T | 11.1 | 2.11 | same | same | same | same |
| artists' | far field only, 32 threads | 124 (41 / 0 + 57 / - / 26) | 261 M | 0.75e9 | 0.40 T | 8.2 | 0.90 | 480 / 220,406 | 0.97 (far part only) | 2.15e-2 | (no near) |
| Sponza | dense + SVD (16 CPUs) | 561 (0.1 / 341 / 189 / 31) | 555 M | 1.54e9 | 12.6 T | 12.3 + 6.1 file | 1.73 | 265,798 / 155,628 | 2.36e-4 | 1.43e-2 | 5.3e-4 |
| Sponza | block by block, 8 threads | 78 (0 / 12 + 36 / - / 29) | 278 M | 0.70e9 | 0.27 T | 8.1 | 1.80 | 279,781 / 160,092 | 1.96e-4 | 1.41e-2 | 5.5e-4 |
| Sponza | block by block, 32 threads | 92 (0 / 14 + 45 / - / 33) | 278 M | 0.70e9 | 0.27 T | 8.3 | 1.80 | same | same | same | same |
| Sponza | cross approximation, 8 threads | 123 (0 / 12 + 86 / - / 25) | 89 M | 0.14e9 + crosses | - | 10.4 | 1.56 | 279,781 / 100,340 | **3.9e-2 (wrong)** | **0.160** | 1.1e-2 |
| Sponza | far field only, 32 threads | 67 (0 / 0 + 33 / - / 34) | 211 M | 0.57e9 | 0.27 T | 4.8 | 0.66 | 0 / 160,092 | 0.94 (far part only) | 1.41e-2 | (no near) |

The block-by-block build keeps the elements that are empty only by visibility (42,215
against 40,440 on the artists' scene, 37,533 against 36,818 on Sponza): its tiles are 4
to 6 % more for that. Its near blocks differ from the dense build's by 2.0e-4 (one ray
a pair of mirrored pairs instead of two rays that disagree at grazing angles).

## The dense build by phase (artists' scene, 16 CPUs)

| phase | work | seconds | where (sampled) |
| --- | --- | ---: | --- |
| tree | 8.8 M triangles, built twice (glass) | 118 | numpy 102, libc 16 (the lexsort a level: 71) |
| form factors | 1.81e9 pairs, 688 M rays | 554 | numpy 249 + libc 100 (gathers of pair arrays), tracer 203 (3.4 M rays/s on 8 threads) |
| order | the 7.3 GB file read in cluster order | 15 | numpy, libc |
| hierarchical | 8,526 full SVDs, 0.85e9 entries, 14.9 TFlop | 274 | LAPACK 257 (58 GFlop/s) |
| rest | sample, probe, transfer, field, checks, write | 25 | numpy |

The interpreter's own time is under 0.2 s in every phase.

## Ray trees (any-hit rays between random element pairs, 4 M rays)

| scene | tree | build s | 8 threads M rays/s | 16 threads M rays/s | hits differ |
| --- | --- | ---: | ---: | ---: | ---: |
| Sponza | median | 0.9 | 2.71 | 5.26 | - |
| Sponza | presorted | 0.6 | 2.71 | 5.30 | 0 |
| artists' | median | 46.3 | 1.95 | 2.57 | - |
| artists' | presorted | 31.6 | 1.92 | 2.57 | 0 |
| artists' | surface area | 207.2 | 6.86 | 7.84 | 0 |

## Block by block: what is left (artists' scene, 32 threads, 163 s)

| phase | seconds | kind |
| --- | ---: | --- |
| tree | 33 | data layout: about ten numpy passes over 8.8 M triangles a level, 24 levels |
| near + far: tracing | 28 | compute (C++; 345 M rays at 11 M rays/s); a better tree halves it |
| near + far: the rest of the main thread | 56 | waiting for the pool, concatenating rays |
| pool (thread-seconds) | 1,150 | waiting for the interpreter's lock 640; numpy 100; BLAS 50 (compute) |
| checks | 13 to 21 | data layout: the card's numbers emulated in numpy |
| order, sample, probe, transfer, field, write | 25 | mixed; write is the files' I/O |

## The batch tracer over the host's own tree

`trace.batch` walking the box tree's nodes (before) against the host's own tree of its
triangles (after: [trace](../../docs/internals/reference/trace.md#the-batch-tracer)).
One process under `taskset` of 10 CPUs, other accounts' jobs on the host. Date
2026-11-27 (UTC+8). The artists' flat (4.8 M triangles, 5.4 M vertices) and an artists'
house (29.8 M triangles, 19.7 M vertices).

Rays a second a thread, millions, 8 threads in one call: the bake's rays (64 cosine
rays a vertex) of 100,000 random vertices, any hit and closest hit; segments between
4 M random pairs of vertices, any hit; the bake's rays of 100,000 consecutive vertices
(the bake's own order):

| scene | bake, any hit | bake, closest hit | random segments | the bake's order |
| --- | --- | --- | --- | --- |
| flat | 0.293 -> 0.566 | 0.147 -> 0.391 | 0.107 -> 0.350 | 0.255 -> 0.411 |
| house | 0.531 -> 0.961 | 0.258 -> 0.697 | 0.147 -> 0.336 | 0.786 -> 1.476 |

The house's whole bake (`visibility._bake_chunk` over every vertex on 10 threads): 241.3
s, 0.524, against 109.9 s, 1.150, the visibility equal.

The steps, on the flat (bake any / bake closest / random segments):

| tree and walk | rays a second a thread | node / triangle tests a bake ray |
| --- | --- | --- |
| the box tree's nodes (median cuts, one triangle a leaf, 32-byte nodes breadth first) | 0.293 / 0.147 / 0.107 | 258 / 9 |
| both children's boxes in one node, depth first, median cuts | 0.352 / 0.201 / 0.126 | |
| surface-area cuts, one triangle a leaf | 0.503 / 0.340 / 0.157 | |
| leaves of at most 4 | 0.586 / 0.400 / 0.190 | 104 / 10 |
| leaves of at most 8 | 0.581 / 0.402 / 0.203 | |
| the children fetched ahead | 0.604 / 0.402 / 0.213 | |
| the rays in the order of their origins' cells | 0.566 / 0.391 / 0.350 | |

The bake's rays shuffled run at 0.307 (any hit) without the cells' order and 0.480 with
it: the walk is bound by fetching nodes and triangles from memory, one thread's rate
the same alone (0.636) as with 8.

The far field as `prism_cli open` builds it (seconds; the transport's steps):

| scene | before | after |
| --- | --- | --- |
| flat | lights 145, transport 156.2 (tree 16.8, near 21.6, far 67.1, transfer 24.2, checks 12.5) | lights 81.3 (bake 60.6), transport 98.8 (tree 17.1, probe 3.6, near 9.5, far 29.6, transfer 13.7, checks 13.3) |
| house | lights 351.0 (bake 255.2), transport 329.8 (tree 121.3, near 26.0, far 118.8, transfer 20.4, checks 17.6) | lights 231.2, transport 241.9 (tree 116.4, probe 15.6, near 12.2, far 45.2, transfer 11.1, checks 17.3) |

On both scenes the visibility file's array and every file of the transport set are equal
byte for byte before and after. Of the flat's 6.4 M closest-hit bake rays 301 differ:
234 at the same `t` on another triangle, 67 at another `t`, rays through an edge or a
vertex shared by triangles; any-hit rays differ in 0 of 6.4 M bake rays and 4 of 4 M
random segments. What is left on the house: the box tree's numpy build (116 s of the
transport, about 70 s of the lights), which the walk no longer reads but whose triangle
order the host's tree is made from, and the host's tree itself (15 to 18 s).

