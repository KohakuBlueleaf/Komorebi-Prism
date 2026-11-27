# The transport's build: dense against block by block

The indirect light's transport set is made on the host once per scene by
`python scripts/data/public_scenes.py indirect NAME` ([scenes](../concepts/scenes.md)), in
one of two ways: the dense build (the default, `--transport dense`) evaluates every pair
of elements into an `N x N` file and takes an SVD of every admissible block; the
block-by-block build (`--transport sketch`) evaluates each block where it lies and
compresses it at once, without the dense matrix. How each works and why is
[the transport's build](../internals/reference/transport_build.md); every number is from
[measurements/transport_build](../../measurements/transport_build/README.md).

Conditions: 2026-11-27 (UTC+8), one process a run under `taskset` of 32 CPUs (16 for the
dense build: two runs side by side), the tracer's threads as marked, other accounts' jobs
on the same host (a row's seconds vary by up to about 15 % between runs). Sponza (262 k
triangles) and an artists' scene of 8.8 million triangles with glass; 50,000 elements
sampled. "y error": `y = M x` for the scene's own light against the dense build's, relative
L2 over all elements; "all of M": each stored block against the dense `F`, relative
Frobenius.

## Seconds and error

| scene | build | seconds | rays | peak memory, GB | weights, GB | y error | all of M |
|---|---|---:|---:|---|---:|---:|---:|
| Sponza | dense + SVD (16 CPUs) | 561 | 555 M | 12.3 + 6.1 file | 1.73 | 2.36e-4 | 5.3e-4 |
| Sponza | block by block, 8 threads | 78 | 278 M | 8.1 | 1.80 | 1.96e-4 | 5.5e-4 |
| Sponza | block by block, 32 threads | 92 | 278 M | 8.3 | 1.80 | same | same |
| artists' | dense + SVD (16 CPUs) | 986 | 688 M | 16.3 + 7.3 file | 2.00 | 7.7e-5 | 1.03e-3 |
| artists' | block by block, 8 threads | 205 | 345 M | 11.4 | 2.11 | 7.4e-5 | 1.05e-3 |
| artists' | block by block, 32 threads | 163 | 345 M | 11.6 | 2.11 | same | same |

The card's own numbers of `y` are 1.6e-3 (Sponza) and 2.6e-3 (artists') from the dense
build's exact `y`: the card's quantization is larger than either build's error.

## What the numbers say

- **The block-by-block build is 4.8 to 7.2 times faster and makes the same transport.**
  Its `y` error and its blocks' error against the dense `F` are those of the dense
  build's own stored blocks, and its near blocks differ by 2.0e-4: it traces one ray a
  pair of mirrored pairs instead of two rays that disagree at grazing angles. It traces half the rays
  (the mirrored pairs once) and its compression costs 0.27 to 0.40 TFlop against the full
  SVDs' 12.6 to 14.9 TFlop.
- **It keeps a few percent more tiles** (4 to 6 %): it keeps the elements that are empty
  only by visibility (37,533 against 36,818 on Sponza, 42,215 against 40,440 on the
  artists' scene), so its weights are 4 to 6 % larger.
- **The dense build's time is not the interpreter** (under 0.2 s in every phase): on the
  artists' scene it is the form factors (554 s, the pair arrays gathered and evaluated in
  one thread), the SVDs (274 s, 58 GFlop/s) and the tree built twice for glass (118 s).
- **More tracer threads help only the large scene** (205 to 163 s on the artists' scene;
  Sponza 78 s on 8, 92 s on 32). Of the 163 s, tracing is 28 s; most of the pool's
  thread-seconds wait for the interpreter's lock between numpy calls.
- **The tracer is twice as fast over the host's own tree**, with the same results: on
  10 CPUs the bake's rays run at 0.41 against 0.26 (an artists' flat) and 1.48 against
  0.79 (an artists' house) million a second a thread, random segments at 0.35 against
  0.11 and 0.34 against 0.15; the far field built at open takes 180 instead of 301 s on
  the flat and 473 instead of 681 s on the house, the visibility and the transport set
  equal byte for byte. On the house the box tree's numpy build is then the largest part.
- **Cross approximation (`--transport cross`) is wrong**: on Sponza its `y` error is
  3.9e-2 and its low-rank blocks' 0.160, because visibility makes far blocks sparse and
  a cross through occluded rows sees nothing. **Far field only (`--far-only`)** is a
  different transport: the near blocks hold almost all of `y`.
