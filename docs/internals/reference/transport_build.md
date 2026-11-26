# Transport build

How the indirect light's transport (`M = pi F` in the card's hierarchical layout,
[indirect](indirect.md) item 2) is built, what each way of building it costs and why.
The numbers are in [measurements/transport_build](../../../measurements/transport_build/README.md).

```bash
python scripts/data/public_scenes.py indirect sponza                      # dense (the control)
python scripts/data/public_scenes.py indirect sponza --transport sketch   # block by block
python scripts/data/public_scenes.py indirect sponza --transport cross    # cross approximation
python scripts/data/public_scenes.py indirect sponza --transport sketch --far-only
```

## The dense build and where its time goes

`indirect.build.build` evaluates every pair (`N^2`, 1.8e9 at 42,581 live elements) in
strips of 128 rows into a memory-mapped `N x N` file, reorders it into the cluster order,
then takes a full SVD of every admissible block. Profiled by sampling (the interpreter,
numpy's loops, LAPACK, the C++ tracer and libc apart), its time is never the interpreter
(under 0.2 s in every phase); it is three wastes of the CPU:

- **The kernel's data layout.** Each strip gathers `(5.4 M, 3)` float64 arrays by fancy
  indexing (`p[j] - p[i]`, `n[i]`, `n[j]`) and evaluates the kernel over them in one
  thread: about 0.16 GFlop/s. On Sponza the kernel takes 306 s of the 341 s; the 555 M
  rays take 37 s.
- **Work thrown away.** A full SVD of every admissible block (12.6 to 14.9 TFlop, blocks
  up to 2,528 x 2,528) keeps a median rank of 14. Glass in a scene builds the median
  tree twice (the scene's tree, then the one with glass open). The `N x N` file is
  written, then read again in another order.
- **The BLAS threads.** OpenBLAS starts its own maximum of threads (64), not the CPUs
  the process may use, so its threads outnumber the cores under `taskset`.

## Block by block (`indirect.blockwise`, `--transport sketch`)

The same files, built without the dense matrix:

1. **The ray tree once**, with glass open (`blockwise.build.ray_tree`), by the
   `presorted` median build ([trace](trace.md)).
2. **Empty rows** are found by the kernel's sign test alone (`pairs.facing_any`: two
   products of rank 3 a chunk): an element no other element faces is dropped. Rows that
   are empty only by visibility are kept (zero rows of `M`), so a few percent more
   elements are kept than by the dense build.
3. **Every block is evaluated where it lies** (`values.evaluate`): rows and columns of a
   block are ranges of the cluster order, so the kernel is a broadcast over two slices,
   with no gather; one any-hit ray a pair of positive kernel, the rays of many blocks
   traced in one call. The kernel is symmetric when all real elements have the same area
   (the area sampling gives every element `A / N`): block `(b, a)` is then the transpose
   of `(a, b)` and only `a <= b` is evaluated. The visibility ray is the same segment in
   both directions, so this halves the rays by construction.
4. **Near blocks** are stored dense from their own pairs. **Admissible blocks** are
   compressed as soon as they are evaluated by a randomized range
   (`compress.sketch_factors`): the range grows one tile (32 columns) at a time, each
   with one power step and only its numerically new directions, until the new
   directions' largest singular value is at most the tolerance (1e-2) times the
   largest; the singular values above the tolerance come from the small factor's Gram
   matrix. A block whose range would pass `m n / (m + n)` columns (a low-rank form would
   not be smaller) takes the full SVD (`exact_factors`). Same truncation rule, same
   dense rule as the dense build; the flops are those of a few products of the block
   with 32 columns instead of a full SVD.
5. The blocks' kernels and compressions run on a pool of `trace.batch.threads()` threads
   with BLAS on one thread each (`native.blas.blas_threads`, OpenBLAS' own calls), while
   the main thread traces the next batch's rays.

No `y_exact` is written (there is no dense matrix to apply); `y_float` and `y_q8` are.

## Cross approximation (`--transport cross`)

`blockwise.far.cross_blocks`: adaptive cross approximation with partial pivoting, every
admissible block advancing one cross a step, all blocks at once over flat rows and
columns: a row of the residual, its largest entry's column, the column's residual; the
pivot rows chosen by the kernel's facing counts; a block stops when the new cross is at
most the tolerance of the running Frobenius estimate and the residual at 32 random facing
entries is too. It traces about a tenth of the far rays, and it is wrong: visibility
makes far blocks sparse (in a 192 x 192 block often 6 to 800 nonzeros of 36,864), a
cross through rows that happen to be occluded sees nothing, and the stopping test samples
too few entries to find what is left. Block errors are 10 to 72 % of the truth by size
class (256 samples a block: 10 to 43 %); at a tighter tolerance it does not finish.

## Far field only (`--far-only`)

The same build with no near block stored. It is a different transport, not an
approximation of the full one: the near blocks hold 99.8 % of `|M|^2` and almost all of
`y`, so `y` of the far field alone is a few percent of the full `y`.

## What is left, and of which kind

Of the block-by-block build's time (measured with 32 threads): the tracer (C++, compute:
the same in any language with this tree; a surface-area tree traces 2 to 3.5 times
faster on the artists' scene, but its numpy build costs 218 s instead of 34 s); the
tree's build (numpy over all triangles a level, about ten passes a level: data layout,
not compute); the kernels (numpy temporaries of `(m, n, 3)` float64, and with 32 pool
threads most of a worker's time is spent waiting for the interpreter's lock between
numpy calls: interpreter); the compressions (BLAS products, compute); the card's numbers
emulated in the checks (`card_apply`, numpy, layout).
