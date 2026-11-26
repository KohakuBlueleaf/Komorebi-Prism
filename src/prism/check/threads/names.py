"""What the checks of the threads' form name in the assembly: the threads' host, its
tensors and numbers, the dispatcher's numbers, regions, times and results, the phases
of a view."""

from prism.core.headers import defined
from prism.program.dispatch import thread as dispatch

P = dispatch.P  # the dispatcher's prefix of its numbers, regions, times and results
POLICY = P + "policy"
PHASES = dispatch.PHASES  # the view's phases (a bit mask; 0: every phase)
SLICES = P + "slices"  # the slices' words, TS_WORDS a slice
LOG = P + "log"  # the count pull's log (KMX_PULL_LOG_BYTES of the view's ranges)
TIMES, RESULTS = dispatch.TIMES, dispatch.RESULTS
POLICIES = dispatch.POLICIES  # {name: value}: prefer, order, kept
# the phases' bits (dispatch.h DP_PHASE_*), these values unless the header gives them
PHASE_DEFAULTS = {"count": 1, "sums": 2, "place": 4, "tile": 8}
# the threads' host's tensors: one each, and one a layer (in the frame page's order)
ONE = ("records", "display")
LAYERED = ("lists", "counts", "rows", "positions")


def phases():
    """{phase: bit} of a view: dispatch.h's DP_PHASE_* when it defines them."""
    given = defined(dispatch.RUNTIME / "dispatch.h")
    return {
        name: given.get(f"DP_PHASE_{name.upper()}", bit)
        for name, bit in PHASE_DEFAULTS.items()
    }


def mask(*names):
    """The phases' mask of `names`."""
    bits = phases()
    unknown = set(names) - set(bits)
    if unknown:
        raise ValueError(f"no phase {sorted(unknown)}; the phases: {sorted(bits)}")
    return sum(bits[name] for name in names)


def threads_host(loaded):
    """The loaded run's host of the threads' form (its attribute `threads` true);
    ValueError naming the hosts when none."""
    for name, host in loaded.hosts.items():
        if getattr(host, "threads", False):
            return name, host
    raise ValueError(
        f"no host of the threads' form (threads = True) among {sorted(loaded.hosts)}"
    )


def tensors(host):
    """The threads' host's tensors checked: {name: tensor} of ONE, {name: [tensor a
    layer]} of LAYERED; ValueError naming the missing."""
    given = getattr(host, "tensors", {})
    missing = [name for name in (*ONE, *LAYERED) if name not in given]
    if missing:
        raise ValueError(f"the threads' host gives no tensors {missing}")
    out = {name: given[name] for name in ONE}
    out |= {name: list(given[name]) for name in LAYERED}
    return out


def capacity(host):
    """The dispatcher's capacity the threads' host built for (dispatch.Capacity)."""
    held = getattr(host, "capacity", None)
    if not isinstance(held, dispatch.Capacity):
        raise TypeError(f"the threads' host's capacity is {held!r}, not a Capacity")
    return held


def numbers(host):
    """{heavy, range_blocks, policy, near} as the threads' host wrote them."""
    out = {}
    for name in ("heavy", "range_blocks", "policy", "near"):
        if not hasattr(host, name):
            raise ValueError(f"the threads' host gives no number {name!r}")
        out[name] = getattr(host, name)
    return out
