"""The commands of a frame in the director's order, read from its times row, and each
command's place in Komorebi's trace: the cores' take and done, a frame's segment."""

from dataclasses import dataclass

import numpy as np

# a layer's raster passes in the unit's order; the middle pass is the thread's own
RASTER = ("count", "sum", "hist", "hsum", "middle", "place", "setup", "fill")
FRAME_ONCE = ("light", "light_glass", "show", "push")  # after every layer's SHADE
THREAD = ("middle",)  # parts with no command on the cores
WRAP = 1 << 32


@dataclass(frozen=True)
class Command:
    """A command of the frame: its times column, its layer's index and name (None: the
    frame's once), whether the cores run it."""

    name: str
    layer: int | None = None
    layer_name: str | None = None

    @property
    def cores(self):
        return self.name not in THREAD

    @property
    def key(self):
        """Its name in the record: `<name>.<layer name>` for a layer's."""
        return self.name if self.layer is None else f"{self.name}.{self.layer_name}"


def value(row, name, layer):
    """A times row's column `name` (a layer unit's at `layer`), 0 when absent."""
    got = row.get(name, 0)
    if isinstance(got, list):
        return got[layer] if layer is not None and layer < len(got) else 0
    return got


def frame_commands(row, layers):
    """The commands that ran in a times row, in the frame's order: each layer's raster
    passes, each layer's SHADE, then LIGHT, its glass form, SHOW and the PUSH."""
    out = []
    for index, layer in enumerate(layers):
        out += [Command(n, index, layer) for n in RASTER if value(row, n, index) > 0]
    out += [
        Command("shade", index, layer)
        for index, layer in enumerate(layers)
        if value(row, "shade", index) > 0
    ]
    return out + [Command(n) for n in FRAME_ONCE if value(row, n, None) > 0]


def traced(rows):
    """Whether each sequence number (from 1) of the trace rows [cores, cap, 4] was taken
    by a core."""
    return np.asarray(rows)[:, :, 0].any(axis=0)


def segments(rows, counts, set_up=False):
    """The trace's sequence indices of the last len(`counts`) frames' core commands, a
    list a frame (`counts[i]` commands each; None where a frame's segment does not
    hold them): each frame's commands follow its FRAME command, which no core takes;
    `set_up`: the first frame is the load's first, the units' set-up before it."""
    taken = traced(rows)
    if not taken.any():
        return [None] * len(counts)
    last = int(np.nonzero(taken)[0][-1])
    gaps = [s for s in range(last + 1) if not taken[s]]
    best = [None] * len(counts)
    for end in range(len(gaps), len(counts) - 1, -1):  # the runtime's own after them
        window = gaps[end - len(counts) : end]
        found = placed(window, gaps[end:], counts, last, set_up)
        if sum(one is not None for one in found) > sum(o is not None for o in best):
            best = found
    return best


def placed(gaps, after, counts, last, set_up):
    """Each frame's sequence indices when its FRAME command is at `gaps[i]` (`after`
    the untraced sequences after the last), None where they do not fit; commands of
    other sources (the host's reads) may follow a frame's."""
    out = []
    for number, (gap, count) in enumerate(zip(gaps, counts, strict=True)):
        begin = gap + 1 + int(set_up and number == 0)
        later = gaps[number + 1 :] + after
        end = later[0] if later else last + 1
        out.append(list(range(begin, begin + count)) if end - begin >= count else None)
    return out


def cores_of(rows, index):
    """One command's trace on the cores that took it: (cores, take, done, sent) in
    cycles after the first take, the leader's sent at the group's first core."""
    words = np.asarray(rows)[:, index, :].astype(np.int64)
    used = np.nonzero(words[:, 0] != 0)[0]
    if not len(used):
        return used, used, used, 0
    origin = words[used[0], 0]
    take, done, sent = (
        (words[used, k] - origin + WRAP // 2) % WRAP - WRAP // 2 for k in range(3)
    )
    first = take.min()
    return used, take - first, done - first, int(sent[0] - first)
