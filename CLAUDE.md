# Komorebi-Prism

A real-time rendering pipeline on Tenstorrent Blackhole cards, built on Komorebi.

## Packages

| package | role | imports |
| --- | --- | --- |
| `prism_common` | registry, build, slot contracts, formats, log, knobs, paths | no Komorebi, no sibling |
| `prism_reference` | the algorithms in numpy: scene, raster, material, direct, indirect, post, trace, native, io | common; numpy only |
| `prism` | core, stages, program, loop, check | common, reference, Komorebi |
| `prism_cli`, `prism_viewer` (under `apps/`) | full-stack interfaces | all |

`prism_common` imports no sibling and not Komorebi. `prism_reference` imports neither
Komorebi nor `prism`. Nothing under `src/` imports `apps/`. Komorebi is a dependency
(`komorebi-tt`): a change the pipeline needs in the framework is made in Komorebi and
released there, never patched here.
`checks/repo_rules.py` verifies direction, file length, ASCII and in-function imports.

## Project structure

```
configs/                 pure-Python configs
  pipeline/              presets: which implementation fills each item of the pipeline
src/
  prism_common/          registry, build, slots, formats, log, knobs, paths
  prism_reference/       the algorithms in numpy, by stage: scene, raster, material, direct,
                         indirect, post; trace/ (the box tree and the batch tracer), native/
                         (compiled helpers), io/
  prism/                 the whole render pipeline on the card
    core/                the pipeline framework: implementation and its host's contract,
                         pipeline, unit (an implementation's part of the thread), resources
                         (the layout that assigns regions, numbers, columns, times; the
                         layers and the views the hosts hold),
                         capacity, headers (numbers read from C headers), compute (the
                         frame program's compute set), fields (the fields several
                         classes share: one definition each, sized by the largest need;
                         the command space, each stage's parts over the same bytes),
                         include/ (device headers every stage shares)
    stages/              <stage>/<implementation>/: raster; material (texture); direct
                         (light, shadow_pcf); indirect (transport, field_update); post (show)
                         an implementation: device.py (its class), kernels/ (its C++, by
                         what it does), thread/ (its unit's C), unit.py, host.py, model/
                         (its data as numpy), check/, README.md
    program/             the selected implementations assembled into one program; director/:
                         the frame's thread (a runtime in C, the sequence generated from
                         the pipeline; a view COLOUR or DEPTH, run unit by unit)
    loop/                a pipeline kept loaded: frames, sizes, recoveries, camera paths
    check/               checks against prism_reference: the harness (a check's record),
                         the frames with the field's update
apps/
  prism_cli/             the command line
  prism_viewer/          server/ and web/ (a Vue 3 + Vite page)
scripts/                 run, data
checks/                  behaviour scripts run by hand (a package a subject, run as
                         `python -m checks.<name>`); repo_rules.py
docs/                    concepts, guides, internals, performance
measurements/            recorded measurements
.internal/  CLAUDE.local.md              local only, gitignored (.internal/plans/: plans)
```

## Code conventions

- Max 600 lines per Python file, hard max 1000. One responsibility per module.
- Code carries only *what*; every *why* and *how* goes to `docs/`. Docstrings 1-3 lines,
  comments one line. No rationale, measurement or history in source.
- No imports inside functions except try-guarded optional dependencies.
- Python 3.13. `list`, `dict`, `X | None`, `match-case`. ASCII-only source and messages.
- `black` and `ruff check` over `src apps checks scripts configs`.
- C and C++ are formatted by `clang-format` with the repository's `.clang-format`
  (Komorebi's style); a kernel file is split by what it does, and shared math is a header.
- A folder is a level of the hierarchy, not a pile: about a dozen source files at most
  directly in one folder; past that it is split by subject.
- The viewer's page follows KohakuTerrarium's design language: the gem accents (sapphire,
  aquamarine, taaffeite, iolite, amber), coral and sage for function, the warm surfaces, its
  size scale and fonts; tokens in one place, a component names a token, never a colour.
- A commit's subject is "Area: what changed" (sentence case, the area the stage, part or
  page it touches); the body gives the problem, then the change.
- No machine names, local paths, credentials or private dataset details in tracked files.
  Local notes go in `CLAUDE.local.md`; plans and private material in `.internal/` (plans in
  `.internal/plans/`); both are gitignored.

## Architectural rules

**Select, don't dispatch.** A config resolves once at build time through
`build(choice, REGISTRY)`; a dotted path works wherever a registry name does. No per-frame
branch on a config value.

**The framework is at the pipeline level.** What plugs in and switches is an
*implementation* of an item of the pipeline: the pipeline's definition, its assembly into a
program, running it, checking it and measuring it are what the framework covers. A pipeline
is a config that names one implementation for each item. An implementation may fill several
consecutive items.

**Inside an implementation: modules, not a framework.** Kernel code is tightly coupled by
nature. An implementation is free inside; it is kept readable by clear files and by sharing
plain headers or tile functions with others. What an implementation shows
the pipeline is its contract: the slots it reads and writes and the resources it asks for.

**One program, written two ways.** The program on the card is in the kernel form as a whole.
A part of it may be hand-written C++ or a class in the DSL compiled to C++ and stored; the
two are combined into one program.

**Implementations ask; the core assigns.** Handler numbers, buffer indices, L1 bytes, thread
regions and thread words are never written by hand in an implementation. It states what it
needs and `prism/core` assigns it, or refuses with the numbers.

**The reference comes first.** Every algorithm has its numpy form in `prism_reference`,
by the same stage names; every implementation on the card is checked against it. A check
runs on its own, without the whole pipeline.

**The thread is the director's; a stage gives a unit.** The frame's X280 thread is a small
runtime plus a sequence generated from the pipeline. An implementation gives a unit: its C,
functions of fixed shapes (`<name>_unit_setup`, `_layer`, `_frame`, a served command), and
what it asks for. Nothing in the director names a stage; a unit knows no other unit. What
one needs from another goes by a slot's name, on the thread (`gives`, `takes`) and on the
host (`slots()`, `connect`).

**One source for a number.** A device layout is a constant of one C header; Python reads it
through `prism.core.headers`, and C that cannot include the header gets it as a define from
that reading. Nothing is written twice.

**Device code binds in three ways.** Resident in the frame program, an overlay loaded at a
stage boundary, or an add-on to a live run. `prism/program` chooses; an implementation does
not.

## Numerics

- The card's formats are defined once, in `prism_common/formats.py`.
- Reduce in fp32. Judge an error relative to the format, not absolutely.

## Checks

No test suite. `checks/` holds behaviour scripts run by hand when the logic they cover
changes; `checks/README.md` says which goes with which. Recorded results go to
`measurements/`, and the pages under `docs/performance/` quote them: a folder's README
holds the table, the raw records (JSON) stay on disk and are never tracked. The only JSON
in the repository is configuration.

## Workflow

1. Implement the whole slice.
2. Audit the diff for clear, integrity and behaviour bugs, and for cost.
3. `black`, `ruff`, `python checks/repo_rules.py`, then the checks the change touches.
