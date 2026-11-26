"""An assembled program loaded on a session: its handlers called by implementation; with
threads, their regions, numbers and layers written by name (on the cluster of the unit
that owns the name), its FRAME command, thread commands waited for or submitted beside
the frames, the frame thread's times."""

import komorebi as km
import numpy as np
from komorebi.program import thread as km_thread

from prism.core.implementation import hosted
from prism.core.resources import DIRECTOR, FRAME_COMMAND, TIMES_ROWS
from prism.program.director.thread import CLUSTER

TIMEOUT = 60.0  # seconds a call waits for its event
MICROSECONDS = 1e6 / km_thread.TIMER_HZ  # a timer tick's


def words_of(value):
    """A number or an array as uint32 words (a float array as its float32 bits)."""
    array = np.atleast_1d(np.asarray(value))
    if array.dtype.kind == "f":
        array = array.astype(np.float32).view(np.uint32)
    return array.astype(np.uint32).reshape(-1)


class Loaded:
    """A run of an assembled program: `call` submits a handler and waits for it; with a
    thread, `frame` its FRAME command; `threads` and `layouts` by work cluster."""

    def __init__(self, assembled, session, run):
        self.assembled = assembled
        self.session = session
        self.run = run
        self.layout = assembled.layout
        self.layouts = dict(assembled.layouts)
        self.threads = {}
        self.rows = None
        self.served = 0
        self.result = None
        if self.layout is not None:
            self.threads = {cluster: run.threads[cluster] for cluster in self.layouts}
            self.thread = self.threads[CLUSTER]
            self.rows = np.zeros(
                (self.layout.regions["layers"][3] // 4 // self.layout.layer_words,)
                + (self.layout.layer_words,),
                dtype=np.uint32,
            )
            cores = assembled.options.get("cores") or session.ranks
            for cluster, layout in self.layouts.items():
                bank, _ = self.threads[cluster].regions.address("numbers")
                numbers = {"cores": cores, "workers": cores, "bank": bank}
                numbers["layers"] = layout.layers
                self.numbers(numbers, cluster)

    @property
    def hosts(self):
        return self.assembled.hosts

    @property
    def options(self):
        return self.assembled.options

    def call(self, implementation, handler, group, args):
        """`handler` of `implementation` on the cores `group` (first, count) with the
        command words `args`: its event, once done."""
        submitted = self.assembled.handler(implementation, handler)
        event = self.run.wait(
            self.run.submit(submitted, group, args=args), timeout=TIMEOUT
        )
        if event.kind != "done":
            raise km.KomorebiError(f"{implementation}.{handler}: {event}")
        return event

    def cluster_of(self, table, name, cluster=None):
        """The work cluster whose layout's `table` (regions, numbers, commands) holds
        `name`: `cluster` when given, else the one where a unit owns it, else the
        frame's."""
        if cluster is not None:
            return cluster
        for one, layout in self.layouts.items():
            entry = getattr(layout, table).get(name)
            if entry is None:
                continue
            owner = entry.owner if table == "numbers" else entry[0]
            if owner != DIRECTOR:
                return one
        return CLUSTER

    def write(self, name, data, at=0, cluster=None):
        """`data`'s words into the thread region `name` from byte `at` (a shared
        region's from its place in the numbers region)."""
        cluster = self.cluster_of("regions", name, cluster)
        owner, _, offset, bytes_, _ = self.layouts[cluster].regions[name]
        words = words_of(data)
        if at + 4 * len(words) > bytes_:
            raise ValueError(
                f"{owner}'s region {name!r}: {4 * len(words)} bytes at {at} pass its "
                f"{bytes_}"
            )
        region = "numbers" if offset else name
        self.threads[cluster].write(region, words, offset + at)

    def number(self, name, value, cluster=None):
        """The number `name` (its words: a camera's 16) set to `value`."""
        cluster = self.cluster_of("numbers", name, cluster)
        place = self.layouts[cluster].numbers[name]
        words = words_of(value)
        if len(words) != place.words:
            raise ValueError(
                f"{place.owner}'s number {name!r} takes {place.words} words, given "
                f"{len(words)}"
            )
        self.threads[cluster].write("numbers", words, 4 * place.word)

    def numbers(self, values, cluster=None):
        """Each number of the dict `values` set."""
        for name, value in values.items():
            self.number(name, value, cluster)

    def layer(self, index, view=None, **columns):
        """Layer `index`'s row of the view `view` (None: of every view): each column
        given set, the others as they were."""
        views = range(self.layout.views) if view is None else [view]
        for one in views:
            number = one * self.layout.layers + index
            row = self.rows[number]
            for name, value in columns.items():
                row[self.layout.columns[name].word] = int(value) & 0xFFFFFFFF
            self.thread.write("layers", row, 4 * number * self.layout.layer_words)

    def frame(self):
        """The thread's FRAME command, waited for: its result code."""
        handle = self.run.submit(FRAME_COMMAND, cluster=CLUSTER, result=True)
        event = self.run.wait(handle, timeout=TIMEOUT)
        if event.kind != "done":
            raise km.KomorebiError(f"{FRAME_COMMAND}: {event}")
        self.served += 1
        return int(event.result)

    def serve(self, command, args=(), row=False):
        """The thread command `command` (a unit's) with the words `args`, waited for:
        its result code; `row`: it writes a times row (it runs views), counted as one.
        """
        event = self.run.wait(self.submit(command, args), timeout=TIMEOUT)
        if event.kind != "done":
            raise km.KomorebiError(f"{command}: {event}")
        self.served += bool(row)
        return int(event.result)

    def submit(self, command, args=()):
        """The thread command `command` (a unit's) with the words `args` submitted to
        its unit's cluster, not waited for: its handle."""
        cluster = self.cluster_of("commands", command)
        return self.run.submit(command, cluster=cluster, args=list(args), result=True)

    def arrived(self, handle):
        """The result code of the submitted thread command `handle` once its event has
        come (never waits), else None; KomorebiError for an event that is not done."""
        self.run.store()
        event = self.run.event(handle)
        if event is None:
            return None
        self.run.forget([handle])
        if event.kind != "done":
            raise km.KomorebiError(f"thread command {handle}: {event}")
        return int(event.result)

    def answer(self, handle):
        """The result code of the submitted thread command `handle`, waited for."""
        event = self.run.wait(handle, timeout=TIMEOUT)
        if event.kind != "done":
            raise km.KomorebiError(f"thread command {handle}: {event}")
        return int(event.result)

    def region(self, name, cluster=None):
        """The thread region `name`'s bytes (a shared one's part of the numbers
        region), read after the stop."""
        cluster = self.cluster_of("regions", name, cluster)
        _, _, at, bytes_, region = self.layouts[cluster].regions[name]
        shared = region is not None and not region.own
        raw = self.threads[cluster].read("numbers" if shared else name)
        raw = np.frombuffer(raw, np.uint8)
        return raw[at : at + bytes_].copy() if shared else raw[:bytes_].copy()

    def steps(self, cluster):
        """The core steps cluster `cluster`'s units had the director run, read after
        the stop (the last TIMES_ROWS): each its round trip and the director's time in
        microseconds, its code, in order."""
        layout = self.layouts[cluster]
        words = layout.times_words
        raw = np.frombuffer(self.threads[cluster].read("times"), dtype=np.uint32)
        rows = raw[: TIMES_ROWS * words].reshape(TIMES_ROWS, words)
        taken = [row for row in rows if row[layout.times["frame"].word]]
        taken.sort(key=lambda row: int(row[layout.results["number"].word]))
        return [
            {
                "round_us": float(row[layout.times["frame"].word]) * MICROSECONDS,
                "director_us": float(row[layout.times["core_step"].word])
                * MICROSECONDS,
                "code": int(row[layout.results["code"].word]),
            }
            for row in taken
        ]

    def times(self):
        """The times rows of the frames served (the last TIMES_ROWS), in order, read
        after the stop: dicts by name, times in microseconds, results as counted; a
        layer unit's a list by layer."""
        words = self.layout.times_words
        raw = np.frombuffer(self.thread.read("times"), dtype=np.uint32)
        rows = raw[: TIMES_ROWS * words].reshape(TIMES_ROWS, words)
        kept = min(self.served, TIMES_ROWS)
        out = []
        for number in range(self.served - kept, self.served):
            row = rows[number % TIMES_ROWS]
            entry = {
                n: self.by_layer(p, [float(row[w]) * MICROSECONDS for w in words])
                for n, p, words in self.places(self.layout.times)
            }
            entry |= {
                n: self.by_layer(p, [int(row[w]) for w in words])
                for n, p, words in self.places(self.layout.results)
            }
            out.append(entry)
        return out

    def places(self, table):
        """(name, place, its words of a times row) of each place of `table`."""
        return [(n, p, self.layout.row_words(p)) for n, p in table.items()]

    @staticmethod
    def by_layer(place, values):
        """A layer unit's values as a list by layer, another's as its one value."""
        return values if place.layered else values[0]

    def stop(self):
        """The run stopped (once): its result."""
        if self.result is None:
            self.run.stop()
            self.result = self.run.result()
        return self.result


def load(assembled, session):
    """`assembled`'s program loaded on `session` (the option `trace`: Komorebi's trace
    of that many commands a core, 0 none), each host bound to it in order."""
    trace = int(assembled.options.get("trace") or 0)
    loaded = Loaded(assembled, session, session.load(assembled.program, trace=trace))
    for host in assembled.hosts.values():
        hosted(host, "bind")(loaded)
    return loaded
