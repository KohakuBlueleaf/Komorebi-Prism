"""The threads' form's program: the handler `work` composed from a preset's tile thread
and the geometry's kinds at the frame's capacity, the sums' class, the other classes,
merged; the X280 ports on the frame's cluster; the frame's thread and the job thread."""

import komorebi as km

from prism.core.resources import Layout
from prism.core.unit import FRAMES
from prism.program.director import thread as director
from prism.program.dispatch import thread as dispatch
from prism.program.frame import device, generate
from prism.program.frame import host as frame_host
from prism.program.jobs import frame as jobs_frame
from prism.program.jobs import thread as jobs_thread
from prism.stages.raster import capacity
from prism.stages.raster.threads import kinds, sums
from prism_common.build import located

WORK, SUMS = "frame", "sums"  # the owners of the handlers work and sums
X280_CORES = 4  # an X280 thread's cores


def composed(host, tile_thread):
    """The Composition of `tile_thread` and the kinds count and place at the frame
    host's capacity, for its layers in order."""
    cap = host.capacity
    count, place = kinds.kinds(
        tiles=host.held.tiles, slices=cap.slices, slice_records=cap.slice_records
    )
    layers, account = tuple(host.layers), bool(getattr(host, "account", 0))
    return generate.compose(tile_thread, (count, place), layers, host.held, account)


def defines(host):
    """The work class's build defines beside the steps' words: the dispatcher's
    capacity's, the raster capacity's, the account's, then each of the option
    frame_defines's."""
    out = dispatch.defines(host.capacity) | capacity.capacity_defines(host.held)
    if getattr(host, "account", 0):
        out |= {"PRISM_FRAME_ACCOUNT": "1"}
    for path in host.options.get(frame_host.DEFINES, ()):
        out |= located(path)(host.held)
    return out


def classes(host, composition, others, session):
    """{owner: made class}: work, sums, then `others` ({implementation: class})."""
    cap = host.capacity
    made = {
        WORK: device.made(host, composition, defines(host)),
        SUMS: sums.made(host.held, cap.slices, cap.slice_records, session=session),
    }
    return made | dict(others)


def merged(made, session):
    """The one program of the made classes."""
    return km.merge(*made.values(), session=session)


def ports(program, session):
    """Every core's X280 port on the frame's cluster, its four cores about as many
    each, so a core's index at its port is its rank."""
    across, down = session.grid
    cores = across * down
    program.ports({core: (FRAMES, core * X280_CORES // cores) for core in range(cores)})


def frame_layout(assembled, host, jobs):
    """The frame thread's layout: the dispatcher's unit, each implementation's unit
    in order, the job thread's unit when `jobs`."""
    units = [dispatch.entry(host.capacity)]
    for implementation in assembled.pipeline.implementations:
        if implementation.thread is not None:
            name = implementation.name
            units.append((name, implementation.thread, assembled.hosts[name]))
    if jobs:
        units.append((jobs_frame.OWNER, jobs_frame.FRAME_UNIT, None))
    writes = {i.name: i.writes for i in assembled.pipeline.implementations}
    return Layout(units, writes, FRAMES, core_step=False)


def threads(assembled, host, tile_thread, jobs):
    """The frame's thread declared on the assembled program (its layout returned) and,
    for `jobs` [(owner, Job, host)], the job thread (its JobLayout, else None)."""
    layout = frame_layout(assembled, host, bool(jobs))
    dispatch.declare(assembled, layout, tile_thread, WORK, SUMS)
    job_layout = None
    if jobs:
        name = director.program_name(assembled.program)
        job_layout = jobs_thread.declare(assembled.program, jobs, name)
    return layout, job_layout
