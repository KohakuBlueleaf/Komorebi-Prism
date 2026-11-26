"""A threads' preset assembled into one program for one scene on a session: every host
prepared and connected, then the classes made at the frame host's capacity and merged,
the X280 ports, the frame's thread and the job thread; loaded, a view, its target."""

from dataclasses import dataclass, field

from prism.core.implementation import hosted
from prism.program import loaded as loaded_program
from prism.program.assemble import Assembled, connected, held_slots
from prism.program.frame import device
from prism.program.threads import program
from prism.program.threads.implementations import JOBS
from prism_common.build import located

TILE_THREAD = "tile_thread"  # the option naming the tile thread: a dotted path
DEADLINE = "deadline"  # the option: seconds a command may take (else Komorebi's)
WAIT_ABOVE = 1.0  # seconds the kernels' wait limit is above the deadline
RECOVER = "recover"  # the option: false keeps a core that gave up as it stood


@dataclass
class Threaded(Assembled):
    """An assembled program of the threads' form: the stage-wise Assembled, its tile
    thread and composition, the frame's host, the dispatcher's capacity, the job
    thread's layout (None without one)."""

    tile_thread: object = None
    composition: object = None
    frame: object = None
    capacity: object = None
    jobs: object = None
    job_hosts: list = field(default_factory=list)


def frame_host(hosts):
    """The host of the threads' form (its `threads` true); ValueError without one."""
    for host in hosts.values():
        if getattr(host, "threads", False):
            return host
    raise ValueError(f"no frame host of the threads' form among {sorted(hosts)}")


def assembled(pipeline, session, scene, options):
    """`pipeline` (a threads' preset's) for `scene` on `session`: each host made and
    prepared, the slots held and each connected; the classes (work and sums at the
    frame's capacity, then each implementation's own) merged, the ports, the threads.
    The option TILE_THREAD names the tile thread."""
    if TILE_THREAD not in options:
        raise ValueError(f"pipeline {pipeline.name!r}: no option {TILE_THREAD!r}")
    tile_thread = located(options[TILE_THREAD])
    hosts = {}
    for implementation in pipeline.implementations:
        host = implementation.host(session, scene, options)
        hosted(host, "prepare")()
        hosts[implementation.name] = host
    out = Threaded(pipeline, None, hosts, {}, dict(options), tile_thread=tile_thread)
    out.slots = held_slots(pipeline, hosts)
    connected(out)
    out.frame = frame_host(hosts)
    out.capacity = out.frame.capacity
    out.composition = program.composed(out.frame, tile_thread)
    others = {
        i.name: i.device(hosts[i.name])
        for i in pipeline.implementations
        if i.device is not None
    }
    out.made = program.classes(out.frame, out.composition, others, session)
    out.program = program.merged(out.made, session)
    device.streams_checked(out.program, out.composition)
    program.ports(out.program, session)
    out.job_hosts = [
        (i.name, JOBS[i.name], hosts[i.name])
        for i in pipeline.implementations
        if i.name in JOBS
    ]
    out.layout, out.jobs = program.threads(out, out.frame, tile_thread, out.job_hosts)
    out.layouts = {out.layout.cluster: out.layout}
    return out


def load(threaded, session):
    """The assembled program loaded on `session`, each host bound (Loaded); the option
    DEADLINE: the seconds a command may take, the kernels' wait limit above it; the
    option RECOVER false: a core that gives up is not reset (its gave-up words kept)."""
    options = threaded.options
    seconds = options.get(DEADLINE)
    recover = options.get(RECOVER)
    recover = True if recover is None else bool(recover)
    if seconds is None and recover:
        return loaded_program.load(threaded, session)
    given = {"recover": recover}
    if seconds is not None:
        given |= {"deadline": float(seconds), "wait": float(seconds) + WAIT_ABOVE}
    run = session.load(threaded.program, trace=int(options.get("trace") or 0), **given)
    loaded = loaded_program.Loaded(threaded, session, run)
    for host in threaded.hosts.values():
        hosted(host, "bind")(loaded)
    return loaded


def view(threaded, loaded, camera, size):
    """What a frame of `camera` at `size` needs, from every host in order."""
    for host in threaded.hosts.values():
        hosted(host, "view")(loaded, camera, size)


def frame(loaded):
    """The FRAME command (the eye's view as the dispatcher's pulls), waited for: its
    code."""
    return loaded.frame()


def target(threaded, loaded):
    """The display read back: (H, W, 4) uint8 of the frame's size."""
    return threaded.hosts["post.show"].display(loaded)
