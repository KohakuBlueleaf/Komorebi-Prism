"""The account of a load: seconds of each part of one `open`, measured by wrapping the
calls it makes (hosts, session, assembly, load) for the command's time, then restored.
"""

import os
import resource
import time
from contextlib import contextmanager
from dataclasses import replace
from functools import wraps
from pathlib import Path

import numpy as np

from prism.loop import loop as loop_module

HOST_CALLS = {"prepare": "model", "connect": "model", "bind": "bind"}
KIB = 1024


class Account:
    """Seconds by part, tensor bytes and seconds by stage, the program's builds; each
    part's seconds exclusive of the tensor writes made inside it."""

    def __init__(self):
        self.started = time.perf_counter()
        self.seconds = {}
        self.tensors = {}
        self.builds = []
        self.stage = None
        self.inside = 0.0  # tensor seconds so far, subtracted from the enclosing part
        self.writing = False
        self.undo = []
        self.convert_peak = None  # the peak resident memory after a conversion, MiB
        self.first_picture = None  # seconds since the start and since the process's

    def add(self, name, seconds):
        """`seconds` added to the part `name`."""
        self.seconds[name] = self.seconds.get(name, 0.0) + seconds

    @staticmethod
    def peak_mib():
        """The process's peak resident memory so far, MiB."""
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / KIB, 1)

    def since_start(self):
        """Seconds since the command's start."""
        return round(time.perf_counter() - self.started, 3)

    @staticmethod
    def since_process():
        """Seconds since the process started (Linux's /proc); None elsewhere."""
        try:
            fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
            uptime = float(Path("/proc/uptime").read_text().split()[0])
        except OSError:
            return None
        return round(uptime - int(fields[19]) / os.sysconf("SC_CLK_TCK"), 3)

    @contextmanager
    def part(self, name):
        """The block's seconds, less the tensor writes inside it, added to `name`."""
        began, inside = time.perf_counter(), self.inside
        try:
            yield
        finally:
            spent = time.perf_counter() - began - (self.inside - inside)
            self.add(name, spent)

    def patch(self, owner, attribute, make):
        """`owner.attribute` replaced by make(the original) until restore()."""
        own = attribute in vars(owner)
        original = getattr(owner, attribute)
        self.undo.append((owner, attribute, own, vars(owner).get(attribute)))
        setattr(owner, attribute, make(original))

    def restore(self):
        """Every patch undone, the last first."""
        for owner, attribute, own, value in reversed(self.undo):
            if own:
                setattr(owner, attribute, value)
            else:
                delattr(owner, attribute)
        self.undo.clear()

    def timed(self, name):
        """A wrapper maker timing each call into the part `name`."""

        def make(original):
            @wraps(original)
            def call(*args, **kwargs):
                with self.part(name):
                    return original(*args, **kwargs)

            return call

        return make

    def hosts(self, pipeline):
        """Each host's prepare, connect and bind timed by stage, its tensors its own."""
        for implementation in pipeline.implementations:
            for method, kind in HOST_CALLS.items():
                if hasattr(implementation.host, method):
                    self.patch(
                        implementation.host,
                        method,
                        self.staged(f"{kind}.{implementation.name}", implementation),
                    )

    def staged(self, name, implementation):
        """A wrapper maker timing a host's call into `name`, its stage set meanwhile."""

        def make(original):
            @wraps(original)
            def call(host, *args, **kwargs):
                stage, self.stage = self.stage, implementation.name
                try:
                    with self.part(name):
                        return original(host, *args, **kwargs)
                finally:
                    self.stage = stage

            return call

        return make

    def written(self, method):
        """A wrapper maker counting a session call's bytes and seconds by stage."""

        def make(original):
            @wraps(original)
            def call(tensor_or_data, *args, **kwargs):
                if self.writing:  # a write inside a counted one
                    return original(tensor_or_data, *args, **kwargs)
                began, self.writing = time.perf_counter(), True
                try:
                    out = original(tensor_or_data, *args, **kwargs)
                finally:
                    self.writing = False
                spent = time.perf_counter() - began
                self.inside += spent
                data = tensor_or_data if method == "tensor" else args[0]
                row = self.tensors.setdefault(self.stage or "load", [0, 0.0, 0])
                row[0] += int(np.asarray(data).nbytes)
                row[1] += spent
                row[2] += 1
                return out

            return call

        return make

    def built(self, original):
        """`_build_levels` timed: seconds and whether it compiled (else found)."""

        @wraps(original)
        def call(*args, **kwargs):
            began = time.perf_counter()
            out = original(*args, **kwargs)
            self.builds.append(
                {"seconds": time.perf_counter() - began, "compiled": bool(out[2][-1])}
            )
            return out

        return call

    def session(self, session):
        """The session's tensor writes and program builds counted."""
        self.patch(session, "tensor", self.written("tensor"))
        self.patch(session, "write", self.written("write"))
        self.patch(session, "_build_levels", self.built)

    def loop(self):
        """The loop's assembly and load (its form's: prism.program.form) timed as
        wholes."""
        self.patch(loop_module, "form_of", self.timed_form)

    def timed_form(self, original):
        """`form_of` whose Form's assembly and load are timed."""

        @wraps(original)
        def call(pipeline):
            form = original(pipeline)
            return replace(
                form,
                assemble=self.timed("assemble")(form.assemble),
                load=self.timed("load")(form.load),
            )

        return call

    def record(self):
        """The parts in seconds (the program's made: the assembly less its hosts; its
        launch: the load less the builds and binds), the tensors, the peak memory."""
        out = dict(self.seconds)
        hosts = sum(v for k, v in out.items() if k.startswith("model."))
        binds = sum(v for k, v in out.items() if k.startswith("bind."))
        build = sum(b["seconds"] for b in self.builds)
        if "assemble" in out:
            out["program.made"] = out.pop("assemble") - hosts
        if "load" in out:
            out["program.launch"] = out.pop("load") - build - binds
            out["program.build"] = build
        own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        return {
            "seconds": {k: round(v, 3) for k, v in out.items()},
            "tensors": {
                stage: {"bytes": b, "seconds": round(s, 3), "calls": n}
                for stage, (b, s, n) in self.tensors.items()
            },
            "builds": [
                {"seconds": round(b["seconds"], 3), "compiled": b["compiled"]}
                for b in self.builds
            ],
            "peak_rss_mib": round(own / KIB, 1),
            "peak_rss_convert_mib": self.convert_peak,
            "peak_rss_children_mib": round(children / KIB, 1),
        }
