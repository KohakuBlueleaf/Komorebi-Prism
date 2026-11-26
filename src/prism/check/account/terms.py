"""One command of one frame accounted: each core's CPUs from its profile, its take and
done from the trace, the spread, the standing still and the closure's terms."""

import numpy as np

from prism.check.account.commands import cores_of
from prism.check.account.profiles import (
    FILL_CPUS,
    LIGHT_CPUS,
    PASS_HANDLER,
    SHADE_CPUS,
    SHOW_CPUS,
    decoded,
    pass_profile,
)


def cpus_of(command, sample):
    """The command's CPUs from a frame's profile pages (profiles.decoded), None when
    its kernels keep no profile."""
    name, layer = command.name, command.layer_name
    if name in PASS_HANDLER:
        return pass_profile(sample["passes"][layer], name)
    pages = {
        "fill": (sample["fill"].get(layer), FILL_CPUS),
        "shade": (sample["shade"].get(layer), SHADE_CPUS),
        "light": (sample["light"].get(name), LIGHT_CPUS),
        "light_glass": (sample["light"].get(name), LIGHT_CPUS),
        "show": (sample["show"], SHOW_CPUS),
    }
    words, cpus = pages.get(name, (None, None))
    return None if words is None else decoded(words, cpus)


def span_cpu(cpus):
    """Each core's busy and waiting cycles of its CPU with the longest total (a total
    without steps counted busy): (busy, waiting, total) arrays a core."""
    totals = np.stack([cpu["total"] for cpu in cpus.values()])
    busy = np.stack(
        [
            sum(cpu["busy"].values()) if cpu["busy"] else cpu["total"]
            for cpu in cpus.values()
        ]
    )
    waits = np.stack(
        [
            sum(cpu["wait"].values()) if cpu["wait"] else np.zeros_like(cpu["total"])
            for cpu in cpus.values()
        ]
    )
    pick = totals.argmax(axis=0)
    cores = np.arange(totals.shape[1])
    return busy[pick, cores], waits[pick, cores], totals[pick, cores]


def accounted(command_us, cpus, rows, index, mhz):
    """The closure's terms of one command in ms (busy, waiting, standing still, take,
    the CPU's other, untimed, push, outside: their sum is the command's time), its
    ratio and the spread, from the trace rows at sequence index `index`."""
    used, take, done, sent = cores_of(rows, index)
    ms = 1e-3 / mhz
    command_ms = command_us * 1e-3
    if not len(used):
        return None
    if cpus is None:
        busy, waiting = done - take, np.zeros(len(used))
        total, source = busy, "trace"
    else:
        busy, waiting, total = (one[used] for one in span_cpu(cpus))
        source = "profile"
    most = done.max()
    terms = {
        "busy": busy.mean() * ms,
        "waiting": waiting.mean() * ms,
        "standing_still": (most - done).mean() * ms,
        "take": take.mean() * ms,
        "cpu_other": (total - busy - waiting).mean() * ms,
        "untimed": ((done - take) - total).mean() * ms,
        "push": (sent - most) * ms,
        "outside": command_ms - sent * ms,
    }
    spread = {
        "done_least": done.min() * ms,
        "done_median": float(np.median(done)) * ms,
        "done_most": most * ms,
        "standing_still": terms["standing_still"],
        "last_take": take.max() * ms,
        "leader_sent": sent * ms,
        "cores": len(used),
    }
    accounted_ms = terms["busy"] + terms["waiting"] + terms["standing_still"]
    return {
        "busy_from": source,
        "terms": {name: float(value) for name, value in terms.items()},
        "ratio": float(accounted_ms / command_ms) if command_ms else None,
        "spread": {name: float(value) for name, value in spread.items()},
    }
